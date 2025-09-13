# cogs/combat_cog.py
from __future__ import annotations

import asyncio
import json
import random
from typing import Dict, Tuple, List, Optional

import discord
from discord.ext import commands, tasks
from discord import app_commands

# ── Backends combat/éco/inventaire/effets
from stats_db import deal_damage, heal_user, get_hp, is_dead, revive_full
from effects_db import (
    add_or_refresh_effect,
    remove_effect,
    has_effect,
    effects_loop,
    set_broadcaster,
    transfer_virus_on_attack,
    get_outgoing_damage_penalty,
)
from economy_db import add_balance, get_balance
from inventory_db import get_item_qty, remove_item, add_item

# ─────────────────────────────────────────────────────────────
# Configuration de base de quelques durées/valeurs de tests
# (Tu remplaceras par tes vraies valeurs / items.)
# ─────────────────────────────────────────────────────────────
DURATIONS = {
    "poison": 60 * 10,     # 10 min
    "virus":  60 * 10,     # 10 min
    "infection": 60 * 10,  # 10 min
    "brulure": 60 * 5,     # 5 min
    "regen": 60 * 5,       # 5 min
}
TICKS = {
    "poison":   {"interval": 60, "value": 2},  # 2 dmg / min
    "virus":    {"interval": 60, "value": 0},  # 0 dmg / min, géré par transfert sur attaque + piqûres 5/5
    "infection":{"interval": 60, "value": 2},  # 2 dmg / min (tes règles s’appliquent côté effects_db/stats_db)
    "brulure":  {"interval": 60, "value": 1},  # 1 dmg / min
    "regen":    {"interval": 60, "value": 2},  # +2 PV / min
}

# ─────────────────────────────────────────────────────────────
# MAPPING des salons de ticks : user_id -> (guild_id, channel_id)
# On le met dans le cog, et le broadcaster l’utilise pour router.
# ─────────────────────────────────────────────────────────────
_tick_channels: Dict[int, Tuple[int, int]] = {}

def remember_tick_channel(user_id: int, guild_id: int, channel_id: int) -> None:
    _tick_channels[int(user_id)] = (int(guild_id), int(channel_id))

def get_all_tick_targets() -> List[Tuple[int, int]]:
    """
    Fournit une liste unique (guild_id, channel_id) à la boucle effects_loop.
    Même si plusieurs joueurs partagent le même salon, on ne le renverra qu'une fois.
    """
    seen: set[Tuple[int, int]] = set()
    for pair in _tick_channels.values():
        seen.add(pair)
    return list(seen)

# ─────────────────────────────────────────────────────────────
# Broadcaster des ticks (appelé par effects_db)
# payload: {"title": str, "lines": List[str], "color": int, "user_id": Optional[int]}
# On tente d’utiliser le salon mémorisé pour user_id, sinon on tombe sur (guild_id, channel_id) fourni.
# ─────────────────────────────────────────────────────────────
async def _effects_broadcaster(bot: commands.Bot, guild_id: int, channel_id: int, payload: Dict):
    # Essaye de router par joueur si fourni
    target_gid = guild_id
    target_cid = channel_id
    uid = payload.get("user_id")
    if uid is not None and int(uid) in _tick_channels:
        target_gid, target_cid = _tick_channels[int(uid)]

    channel = bot.get_channel(int(target_cid))
    if not channel or not isinstance(channel, (discord.TextChannel, discord.Thread)):
        # fallback : on essaie quand même avec ce que effects_loop a fourni
        channel = bot.get_channel(int(channel_id))
        if not channel:
            return

    embed = discord.Embed(title=str(payload.get("title", "GotValis")), color=payload.get("color", 0x2ecc71))
    lines = payload.get("lines") or []
    if lines:
        embed.description = "\n".join(lines)
    await channel.send(embed=embed)

# ─────────────────────────────────────────────────────────────
# Le COG
# ─────────────────────────────────────────────────────────────
class CombatCog(commands.Cog):
    """Système de combat — version test/minimale avec application d’effets et dégâts directs."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # branche le broadcaster des ticks
        set_broadcaster(lambda gid, cid, pld: asyncio.create_task(_effects_broadcaster(self.bot, gid, cid, pld)))
        # lance la boucle de scan des effets si pas déjà en cours
        # (on lui donne un getter qui renvoie les salons à scanner)
        self._effects_task: Optional[asyncio.Task] = None
        self._start_effects_loop_once()

    # ── Lancement unique de la boucle des effets
    def _start_effects_loop_once(self):
        if getattr(self.bot, "_effects_loop_started", False):
            return
        self.bot._effects_loop_started = True
        async def runner():
            await effects_loop(get_targets=get_all_tick_targets, interval=30)
        self._effects_task = asyncio.create_task(runner())

    # ─────────────────────────────────────────────────────────
    # Commandes de test (tu pourras les remplacer par /fight, /heal, /use)
    # ─────────────────────────────────────────────────────────

    @app_commands.command(name="hit", description="(test) Inflige des dégâts directs à une cible.")
    @app_commands.describe(target="Cible", amount="Dégâts directs (appliquent réduc/bouclier/PV)")
    async def hit(self, inter: discord.Interaction, target: discord.Member, amount: int):
        if amount <= 0:
            return await inter.response.send_message("Le montant doit être > 0.", ephemeral=True)

        await inter.response.defer(thinking=True)
        # malus d’attaque si l’attaquant est empoisonné (−1)
        penalty = await get_outgoing_damage_penalty(inter.user.id)
        final_dmg = max(0, amount - penalty)

        # application des éventuels transferts de virus AVANT les dégâts directs
        # (si l’attaquant porte le virus)
        await transfer_virus_on_attack(inter.user.id, target.id)

        res = await deal_damage(inter.user.id, target.id, final_dmg)

        # KO → règle 14
        if await is_dead(target.id):
            await revive_full(target.id)
            # clear des statuts à la mort géré côté effects_db (ou fais-le ici si nécessaire)

        # feedback
        hp, _ = await get_hp(target.id)
        embed = discord.Embed(
            title="GotValis : impact confirmé",
            description=f"{inter.user.mention} inflige **{final_dmg}** à {target.mention}.\n"
                        f"🛡 Absorbé: {res.get('absorbed', 0)} | ❤️ PV restants: **{hp}**",
            color=discord.Color.red()
        )
        await inter.response.followup.send(embed=embed)

    @app_commands.command(name="poison", description="(test) Applique un poison à une cible.")
    @app_commands.describe(target="Cible")
    async def cmd_poison(self, inter: discord.Interaction, target: discord.Member):
        await inter.response.defer(thinking=True)
        remember_tick_channel(target.id, inter.guild.id, inter.channel.id)
        cfg = TICKS["poison"]
        await add_or_refresh_effect(
            user_id=target.id,
            eff_type="poison",
            value=cfg["value"],
            duration=DURATIONS["poison"],
            interval=cfg["interval"],
            source_id=inter.user.id,
            meta_json=json.dumps({"applied_in": inter.channel.id})
        )
        await inter.followup.send(f"🧪 {target.mention} est **empoisonné**.")

    @app_commands.command(name="virus", description="(test) Applique un virus à une cible (transfert sur attaque).")
    @app_commands.describe(target="Cible")
    async def cmd_virus(self, inter: discord.Interaction, target: discord.Member):
        await inter.response.defer(thinking=True)
        remember_tick_channel(target.id, inter.guild.id, inter.channel.id)
        cfg = TICKS["virus"]
        await add_or_refresh_effect(
            user_id=target.id,
            eff_type="virus",
            value=cfg["value"],
            duration=DURATIONS["virus"],
            interval=cfg["interval"],
            source_id=inter.user.id,
            meta_json=json.dumps({"applied_in": inter.channel.id})
        )
        await inter.followup.send(f"🦠 {target.mention} est **infecté par un virus** (transfert sur attaque).")

    @app_commands.command(name="infection", description="(test) Applique une infection (DOT).")
    @app_commands.describe(target="Cible")
    async def cmd_infection(self, inter: discord.Interaction, target: discord.Member):
        await inter.response.defer(thinking=True)
        remember_tick_channel(target.id, inter.guild.id, inter.channel.id)
        cfg = TICKS["infection"]
        await add_or_refresh_effect(
            user_id=target.id,
            eff_type="infection",
            value=cfg["value"],
            duration=DURATIONS["infection"],
            interval=cfg["interval"],
            source_id=inter.user.id,
            meta_json=json.dumps({"applied_in": inter.channel.id})
        )
        await inter.followup.send(f"🧟 {target.mention} est **infecté**.")

    @app_commands.command(name="brulure", description="(test) Applique une brûlure (DOT).")
    @app_commands.describe(target="Cible")
    async def cmd_brulure(self, inter: discord.Interaction, target: discord.Member):
        await inter.response.defer(thinking=True)
        remember_tick_channel(target.id, inter.guild.id, inter.channel.id)
        cfg = TICKS["brulure"]
        await add_or_refresh_effect(
            user_id=target.id,
            eff_type="brulure",
            value=cfg["value"],
            duration=DURATIONS["brulure"],
            interval=cfg["interval"],
            source_id=inter.user.id,
            meta_json=json.dumps({"applied_in": inter.channel.id})
        )
        await inter.followup.send(f"🔥 {target.mention} est **brûlé**.")

    @app_commands.command(name="regen", description="(test) Applique une régénération (HoT).")
    @app_commands.describe(target="Cible")
    async def cmd_regen(self, inter: discord.Interaction, target: discord.Member):
        await inter.response.defer(thinking=True)
        remember_tick_channel(target.id, inter.guild.id, inter.channel.id)
        cfg = TICKS["regen"]
        await add_or_refresh_effect(
            user_id=target.id,
            eff_type="regen",
            value=cfg["value"],
            duration=DURATIONS["regen"],
            interval=cfg["interval"],
            source_id=inter.user.id,
            meta_json=json.dumps({"applied_in": inter.channel.id})
        )
        await inter.followup.send(f"💕 {target.mention} bénéficie d’une **régénération**.")

    # ─────────────────────────────────────────────────────────
    # Petit utilitaire : afficher PV
    # ─────────────────────────────────────────────────────────
    @app_commands.command(name="hp", description="(test) Affiche tes PV / PV de la cible.")
    @app_commands.describe(target="Cible (optionnel)")
    async def hp(self, inter: discord.Interaction, target: Optional[discord.Member] = None):
        target = target or inter.user
        hp, mx = await get_hp(target.id)
        await inter.response.send_message(f"❤️ {target.mention}: **{hp}/{mx}** PV")

async def setup(bot: commands.Bot):
    await bot.add_cog(CombatCog(bot))

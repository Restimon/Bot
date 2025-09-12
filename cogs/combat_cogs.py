# cogs/combat_cog.py
from __future__ import annotations

import time
from typing import Optional, List

import discord
from discord import app_commands
from discord.ext import commands

import combat
from ravitaillement import OBJETS


ATTACK_COOLDOWN_SECONDS = 5


# ─────────────────────────────────────────────────────────────
# Helpers d'autocomplétion
# ─────────────────────────────────────────────────────────────

def _objects_by_types(types: set[str]) -> List[str]:
    """Retourne la liste des emojis correspondant à un ensemble de types."""
    out = []
    for k, v in OBJETS.items():
        if v.get("type") in types:
            out.append(k)
    # Garder un ordre stable: par clé (emoji)
    return sorted(out, key=lambda x: x)


async def _ac_attack(interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
    # Types d'attaque (directes & DOT)
    allowed = {"attaque", "attaque_chaine", "poison", "virus", "infection", "brulure"}
    emojis = _objects_by_types(allowed)
    cur = (current or "").strip()
    if cur:
        emojis = [e for e in emojis if cur in e]
    return [app_commands.Choice(name=e, value=e) for e in emojis[:20]]


async def _ac_heal(interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
    allowed = {"soin", "regen"}
    emojis = _objects_by_types(allowed)
    cur = (current or "").strip()
    if cur:
        emojis = [e for e in emojis if cur in e]
    return [app_commands.Choice(name=e, value=e) for e in emojis[:20]]


async def _ac_use(interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
    allowed = {"bouclier", "vaccin", "vol", "immunite", "esquive+", "reduction", "mysterybox"}
    emojis = _objects_by_types(allowed)
    cur = (current or "").strip()
    if cur:
        emojis = [e for e in emojis if cur in e]
    return [app_commands.Choice(name=e, value=e) for e in emojis[:20]]


# ─────────────────────────────────────────────────────────────
# Cog
# ─────────────────────────────────────────────────────────────

class CombatCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # petit stockage local pour CD d'attaque
        self._atk_cd: dict[int, float] = {}

    # --------------- /fight ---------------
    @app_commands.command(name="fight", description="Attaque une cible avec un objet d'attaque.")
    @app_commands.describe(
        cible="Membre à attaquer",
        objet="Emoji de l'objet d'attaque (auto-complétion)"
    )
    @app_commands.autocomplete(objet=_ac_attack)
    async def fight(self, interaction: discord.Interaction, cible: discord.Member, objet: str):
        await interaction.response.defer()
        if not cible or cible.bot:
            await interaction.followup.send("❌ Cible invalide.", ephemeral=True)
            return

        it = OBJETS.get(objet)
        if not it or it.get("type") not in {"attaque", "attaque_chaine", "poison", "virus", "infection", "brulure"}:
            await interaction.followup.send("❌ Objet d'attaque invalide.", ephemeral=True)
            return

        # Cooldown 5s par attaquant
        now = time.time()
        next_ok = self._atk_cd.get(interaction.user.id, 0.0)
        if now < next_ok:
            reste = int(next_ok - now)
            await interaction.followup.send(f"⏳ Attends encore **{reste}s** avant de réattaquer.", ephemeral=True)
            return
        self._atk_cd[interaction.user.id] = now + ATTACK_COOLDOWN_SECONDS

        # Appel moteur
        res = await combat.fight(
            attacker_id=interaction.user.id,
            target_id=cible.id,
            item_key=objet,
            guild_id=interaction.guild_id or 0,
            channel_id=interaction.channel_id
        )

        emb = discord.Embed(
            title=res.get("title", "Attaque"),
            description="\n".join(res.get("lines", [])),
            color=res.get("color", 0xED4245)
        )
        if gif := res.get("gif"):
            emb.set_image(url=gif)
        await interaction.followup.send(embed=emb)

    # --------------- /heal ---------------
    @app_commands.command(name="heal", description="Soigne une cible avec un objet de soin.")
    @app_commands.describe(
        cible="Membre à soigner",
        objet="Emoji de l'objet de soin (auto-complétion)"
    )
    @app_commands.autocomplete(objet=_ac_heal)
    async def heal(self, interaction: discord.Interaction, cible: discord.Member, objet: str):
        await interaction.response.defer()
        if not cible or cible.bot:
            await interaction.followup.send("❌ Cible invalide.", ephemeral=True)
            return

        it = OBJETS.get(objet)
        if not it or it.get("type") not in {"soin", "regen"}:
            await interaction.followup.send("❌ Objet de soin invalide.", ephemeral=True)
            return

        res = await combat.heal(
            healer_id=interaction.user.id,
            target_id=cible.id,
            item_key=objet,
            guild_id=interaction.guild_id or 0,
            channel_id=interaction.channel_id
        )

        emb = discord.Embed(
            title=res.get("title", "Soin"),
            description="\n".join(res.get("lines", [])),
            color=res.get("color", 0x57F287)
        )
        if gif := res.get("gif"):
            emb.set_image(url=gif)
        await interaction.followup.send(embed=emb)

    # --------------- /use ---------------
    @app_commands.command(name="use", description="Utilise un objet utilitaire (bouclier, vaccin, vol, etc.).")
    @app_commands.describe(
        objet="Emoji de l'objet (auto-complétion)",
        cible="Optionnel: cible pour l'effet (par défaut: toi)"
    )
    @app_commands.autocomplete(objet=_ac_use)
    async def use(self, interaction: discord.Interaction, objet: str, cible: Optional[discord.Member] = None):
        await interaction.response.defer()
        target = cible or interaction.user
        if target.bot:
            await interaction.followup.send("❌ Cible invalide.", ephemeral=True)
            return

        it = OBJETS.get(objet)
        if not it or it.get("type") not in {"bouclier", "vaccin", "vol", "immunite", "esquive+", "reduction", "mysterybox"}:
            await interaction.followup.send("❌ Objet invalide pour /use.", ephemeral=True)
            return

        res = await combat.use_item(
            user_id=interaction.user.id,
            target_id=target.id,
            item_key=objet,
            guild_id=interaction.guild_id or 0,
            channel_id=interaction.channel_id
        )

        emb = discord.Embed(
            title=res.get("title", "Utilisation"),
            description="\n".join(res.get("lines", [])),
            color=res.get("color", 0xFEE75C)
        )
        if gif := res.get("gif"):
            emb.set_image(url=gif)
        await interaction.followup.send(embed=emb)


async def setup(bot: commands.Bot):
    await bot.add_cog(CombatCog(bot))

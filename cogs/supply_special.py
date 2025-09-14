# cogs/supply_special.py
from __future__ import annotations

import asyncio
import random
import time
from typing import Dict, List, Tuple

import discord
from discord.ext import commands

# ---- Dépendances projet (avec fallback sûrs) ----
from utils import get_random_item, OBJETS  # raretés/objets

# économie (GoldValis)
try:
    from economy_db import add_balance  # type: ignore
    _HAVE_ECO = True
except Exception:
    _HAVE_ECO = False
    async def add_balance(user_id: int, delta: int, reason: str = "") -> int:  # type: ignore
        return 0

# inventaire (tickets + objets)
try:
    from inventory_db import add_item  # type: ignore
    _HAVE_INV = True
except Exception:
    _HAVE_INV = False
    async def add_item(user_id: int, item_key: str, qty: int = 1) -> None:  # type: ignore
        return

# dégâts (piège)
try:
    from stats_db import deal_damage, get_hp  # type: ignore
    _HAVE_STATS = True
except Exception:
    _HAVE_STATS = False
    async def deal_damage(attacker_id: int, user_id: int, amount: int) -> Dict[str, int]:
        return {"lost": amount, "absorbed": 0}
    async def get_hp(user_id: int) -> Tuple[int, int]:
        return (100, 100)

# ------------------------------------------------------------
# Réglages
# ------------------------------------------------------------
BOX_EMOJI = "📦"
TICKET_EMOJI = "🎟️"

WINDOW_SECONDS = 5 * 60         # 5 minutes
MAX_CLAIMERS = 5                # max 5 personnes

# Probabilités (tu peux ajuster)
TRAP_CHANCE   = 0.15   # 15% piège
HEAL_CHANCE   = 0.15   # 15% item soin/regen
GOLD_CHANCE   = 0.20   # 20% gold 100-150
TICKET_CHANCE = 0.10   # 10% tickets 🎟️ (1-2)
# le reste → loot normal via utils.get_random_item (40%)

TRAP_DMG_RANGE = (6, 12)        # dégâts du piège si déclenché
GOLD_RANGE     = (100, 150)
TICKET_RANGE   = (1, 2)

# ------------------------------------------------------------
class SpecialSupply(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._active_by_channel: Dict[int, bool] = {}

    @commands.has_permissions(manage_guild=True)
    @commands.hybrid_command(
        name="supply_special",
        description="(Admin) Lancer un ravitaillement spécial (5 min, max 5 personnes).",
    )
    async def supply_special_cmd(self, ctx: commands.Context):
        if not ctx.guild or not isinstance(ctx.channel, (discord.TextChannel, discord.Thread)):
            return await ctx.reply("❌ Utilise cette commande dans un salon texte du serveur.")
        await self._launch_event(ctx.channel)

    async def _launch_event(self, channel: discord.abc.Messageable):
        ch_id = getattr(channel, "id", None)
        if ch_id and self._active_by_channel.get(ch_id):
            await channel.send("⏳ Un ravitaillement spécial est déjà en cours ici.")
            return
        if ch_id:
            self._active_by_channel[ch_id] = True

        # Annonce
        embed = discord.Embed(
            title="📦 Ravitaillement spécial GotValis",
            description="Réagissez avec 📦 pour récupérer une récompense surprise !\n"
                        "⌛ Disponible pendant **5 minutes**, **maximum 5 personnes**.",
            color=discord.Color.orange()
        )
        msg = await channel.send(embed=embed)
        try:
            await msg.add_reaction(BOX_EMOJI)
        except Exception:
            if ch_id:
                self._active_by_channel[ch_id] = False
            return

        # Collecte des participants
        claimers: List[int] = []
        claimed_set: set[int] = set()

        def _is_valid_reaction(reaction: discord.Reaction, user: discord.User) -> bool:
            return reaction.message.id == msg.id and str(reaction.emoji) == BOX_EMOJI and not user.bot

        end_at = time.time() + WINDOW_SECONDS
        while time.time() < end_at and len(claimers) < MAX_CLAIMERS:
            timeout = max(0.0, end_at - time.time())
            try:
                reaction, user = await self.bot.wait_for("reaction_add", timeout=timeout, check=_is_valid_reaction)
            except asyncio.TimeoutError:
                break
            if user.id not in claimed_set:
                claimed_set.add(user.id)
                claimers.append(user.id)

        # Attribution des récompenses (après la fenêtre)
        results: List[str] = []
        guild = msg.guild

        for uid in claimers:
            member = guild.get_member(uid) if guild else None
            mention = member.mention if member else f"<@{uid}>"
            roll = random.random()

            # 1) Piège
            if roll < TRAP_CHANCE:
                dmg = random.randint(*TRAP_DMG_RANGE)
                lost = dmg
                pv_after = None
                try:
                    if _HAVE_STATS and member:
                        _res = await deal_damage(0, member.id, dmg)
                        lost = int(_res.get("lost", dmg))
                        hp_now, _ = await get_hp(member.id)
                        pv_after = hp_now
                except Exception:
                    pass
                pv_after = pv_after if pv_after is not None else max(0, 100 - lost)
                results.append(f"💥 {mention} a subi **{lost} dégâts** (PV: **{pv_after}**).")
                continue

            # 2) Soin / régénération (item de soin)
            if roll < TRAP_CHANCE + HEAL_CHANCE:
                heals = [e for e, d in OBJETS.items() if d.get("type") in ("soin", "regen")]
                item = random.choice(heals) if heals else (get_random_item() or "💰")
                meta = OBJETS.get(item, {})
                # On donne l'objet au joueur (si inventaire dispo)
                if _HAVE_INV and member:
                    await add_item(member.id, item, 1)
                val = meta.get("soin", meta.get("valeur", "?"))
                results.append(f"🎁 {mention} a obtenu **{item}** — 💚 Restaure {val} PV.")
                continue

            # 3) GoldValis
            if roll < TRAP_CHANCE + HEAL_CHANCE + GOLD_CHANCE:
                amount = random.randint(*GOLD_RANGE)
                if _HAVE_ECO and member:
                    await add_balance(member.id, amount, reason="Ravitaillement spécial")
                results.append(f"💰 {mention} a reçu **{amount} GoldValis**.")
                continue

            # 4) Tickets
            if roll < TRAP_CHANCE + HEAL_CHANCE + GOLD_CHANCE + TICKET_CHANCE:
                qty = random.randint(*TICKET_RANGE)
                if _HAVE_INV and member:
                    await add_item(member.id, TICKET_EMOJI, qty)
                results.append(f"🎟️ {mention} a reçu **{qty} ticket(s)**.")
                continue

            # 5) Loot normal (rareté via utils.get_random_item)
            item = get_random_item() or "💰"
            meta = OBJETS.get(item, {})
            if _HAVE_INV and member:
                await add_item(member.id, item, 1)
            if meta.get("type") == "attaque":
                val = meta.get("degats", 0)
                results.append(f"🎁 {mention} a obtenu **{item}** — ⚔️ Dégâts {val}.")
            elif meta.get("type") in ("poison", "virus", "infection", "regen"):
                results.append(f"🎁 {mention} a obtenu **{item}** — effet spécial.")
            else:
                results.append(f"🎁 {mention} a obtenu **{item}** !")

        # Récapitulatif (succès/échec)
        if results:
            recap = discord.Embed(
                title="📦 Récapitulatif du ravitaillement spécial",
                color=discord.Color.green()
            )
            recap.add_field(name="\u200b", value="\n".join(results), inline=False)
        else:
            recap = discord.Embed(
                title="📦 Ravitaillement spécial détruit",
                color=discord.Color.red()
            )
            recap.add_field(name="\u200b", value="Personne n’a réagi à temps.", inline=False)

        await channel.send(embed=recap)

        if ch_id:
            self._active_by_channel[ch_id] = False


async def setup(bot: commands.Bot):
    await bot.add_cog(SpecialSupply(bot))

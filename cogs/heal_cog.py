# cogs/heal_cog.py
from __future__ import annotations

from typing import List, Optional, Tuple, Dict

import discord
from discord import app_commands
from discord.ext import commands

from utils import OBJETS
from inventory_db import get_all_items, get_item_qty, remove_item
from stats_db import heal_user, get_hp
from effects_db import add_or_refresh_effect

# ---------- autocomplete (soin/regen uniquement) ----------
def _is_heal_item(emoji: str) -> bool:
    return (OBJETS.get(emoji, {}).get("type") in ("soin", "regen"))

async def _ac_heal(inter: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
    inv = await get_all_items(inter.user.id)
    cur = (current or "").strip().lower()
    out: List[app_commands.Choice[str]] = []
    for emoji, qty in inv:
        if _is_heal_item(emoji) and int(qty or 0) > 0:
            meta = OBJETS.get(emoji, {})
            label = meta.get("nom") or meta.get("label") or meta.get("type") or "Objet"
            name = f"{emoji} — {label} (x{qty})"
            if not cur or cur in name.lower():
                out.append(app_commands.Choice(name=name[:100], value=emoji))
                if len(out) >= 20: break
    return out

# ---------- cog ----------
class HealCog(commands.Cog):
    """Commande /heal : soigne (soin direct ou régén)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="heal", description="Soigner un joueur avec un objet de soin.")
    @app_commands.describe(objet="Emoji d'un objet de soin", cible="Cible (par défaut: toi)")
    @app_commands.autocomplete(objet=_ac_heal)
    async def heal_cmd(self, inter: discord.Interaction, objet: str, cible: Optional[discord.Member] = None):
        meta = OBJETS.get(objet, {})
        typ = meta.get("type")
        if typ not in ("soin", "regen"):
            return await inter.response.send_message("❌ Choisis un **objet de soin**.", ephemeral=True)

        if int(await get_item_qty(inter.user.id, objet) or 0) <= 0:
            return await inter.response.send_message(f"❌ Tu n’as pas **{objet}**.", ephemeral=True)

        # Consomme d’abord
        if not await remove_item(inter.user.id, objet, 1):
            return await inter.response.send_message("❌ Impossible d'utiliser l'objet.", ephemeral=True)

        await inter.response.defer(thinking=True)
        target = cible or inter.user

        if typ == "soin":
            amount = int(meta.get("soin", meta.get("heal", 10)) or 10)
            healed = await heal_user(inter.user.id, target.id, amount)
            hp_after, mx = await get_hp(target.id)
            e = discord.Embed(
                title="💊 Soin",
                description=f"{inter.user.mention} rend **{healed} PV** à {target.mention}.\n"
                            f"❤️ **{hp_after}/{mx}** PV",
                color=discord.Color.green()
            )
        else:
            val = int(meta.get("valeur", 2) or 2)
            interval = int(meta.get("intervalle", meta.get("interval", 60)) or 60)
            duration = int(meta.get("duree", meta.get("duration", 300)) or 300)
            await add_or_refresh_effect(
                user_id=target.id, eff_type="regen", value=float(val),
                duration=duration, interval=interval, source_id=inter.user.id,
                meta_json=None
            )
            e = discord.Embed(
                title="💕 Régénération",
                description=f"{inter.user.mention} applique une régénération sur {target.mention} "
                            f"(+{val} PV / {interval}s pendant {duration}s).",
                color=discord.Color.teal()
            )

        await inter.followup.send(embed=e)

async def setup(bot: commands.Bot):
    await bot.add_cog(HealCog(bot))

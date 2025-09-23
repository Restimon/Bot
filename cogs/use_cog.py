from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands
from typing import List, Optional

from inventory_db import get_all_items
from utils import OBJETS

try:
    from cogs.leaderboard_live import schedule_lb_update
except Exception:
    def schedule_lb_update(bot, guild_id, reason=""):  # type: ignore
        return

USE_KEYS = {"📦", "🔍", "💉", "👟", "🪖", "⭐️"}

def _item_label(emoji: str) -> str:
    data = OBJETS.get(emoji, {})
    typ = str(data.get("type", "item"))
    if emoji == "📦":
        return "📦 • Mystery Box (3 récompenses)"
    if emoji == "🔍":
        return "🔍 • Vol (vole 1 objet à la cible)"
    if emoji == "💉":
        return "💉 • Vaccin (retire les debuffs)"
    if emoji == "👟":
        return f"👟 • Esquive+ (+{int(data.get('valeur',0)*100)}% / {int(data.get('duree',0))//3600}h)"
    if emoji == "🪖":
        return f"🪖 • Réduction ({int(data.get('valeur',0)*100)}% / {int(data.get('duree',0))//3600}h)"
    if emoji == "⭐️":
        return f"⭐️ • Immunité ({int(data.get('duree',0))//3600}h)"
    return f"{emoji} • {typ}"

async def ac_use_items(inter: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
    if not inter.user:
        return []
    inv = await get_all_items(inter.user.id)
    cur = (current or "").strip().lower()
    out: List[app_commands.Choice[str]] = []
    for emoji, qty in inv:
        if emoji not in USE_KEYS or qty <= 0:
            continue
        label = _item_label(emoji)
        if not cur or cur in label.lower():
            out.append(app_commands.Choice(name=f"{label} ×{qty}", value=emoji))
            if len(out) >= 20:
                break
    return out

class UseCog(commands.Cog):
    """Commande /use : objets utilitaires (📦 🔍 💉 👟 🪖 ⭐️)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="use", description="Utiliser un objet utilitaire (📦 🔍 💉 👟 🪖 ⭐️).")
    @app_commands.describe(
        objet="Emoji de l'objet à utiliser",
        cible="Cible (requis pour 🔍 Vol ; ignoré pour les autres)."
    )
    @app_commands.autocomplete(objet=ac_use_items)
    async def use_cmd(self, inter: discord.Interaction, objet: str, cible: Optional[discord.Member] = None):
        if not inter.guild:
            return await inter.response.send_message("❌ À utiliser dans un serveur.", ephemeral=True)

        if objet not in USE_KEYS:
            return await inter.response.send_message("❌ Cet objet n’est pas utilisable avec /use.", ephemeral=True)

        # déléguée à logic/use.py
        try:
            from logic.use import select_and_apply
            embed, _meta = await select_and_apply(inter, objet, cible)
        except Exception as e:
            return await inter.response.send_message(f"❌ Erreur: {e}", ephemeral=True)

        await inter.response.send_message(embed=embed)

        try:
            schedule_lb_update(self.bot, inter.guild.id, reason=f"use:{objet}")
        except Exception:
            pass

async def setup(bot: commands.Bot):
    await bot.add_cog(UseCog(bot))

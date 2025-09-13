# cogs/inventory_cog.py
from __future__ import annotations

from typing import List, Tuple, Optional

import discord
from discord.ext import commands
from discord import app_commands

from inventory_db import get_all_items, get_item_qty
from economy_db import get_balance

TICKET_EMOJI = "🎟️"

def _format_items(items: List[Tuple[str, int]]) -> str:
    if not items:
        return "*(aucun objet)*"
    # tri par emoji (déjà trié côté DB normalement)
    parts = [f"{emoji} × **{qty}**" for emoji, qty in items]
    # regroupe sur 2–3 lignes pour lisibilité
    lines = []
    line = []
    for i, p in enumerate(parts, 1):
        line.append(p)
        if i % 6 == 0:  # 6 par ligne
            lines.append(" • ".join(line))
            line = []
    if line:
        lines.append(" • ".join(line))
    return "\n".join(lines)

class InventoryCog(commands.Cog):
    """Inventaire & résumé joueur."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ─────────────────────────────────────────────────────────
    # /inv [@membre]
    # ─────────────────────────────────────────────────────────
    @app_commands.command(name="inv", description="Affiche ton inventaire (ou celui d’un membre).")
    @app_commands.describe(user="(optionnel) Membre à inspecter")
    async def inv(self, inter: discord.Interaction, user: Optional[discord.Member] = None):
        await inter.response.defer(thinking=True)
        target = user or inter.user

        # objets
        items = await get_all_items(target.id)
        # solde
        gold = await get_balance(target.id)
        # tickets (compte à part pour lisibilité)
        tickets = await get_item_qty(target.id, TICKET_EMOJI)

        # daily cooldown (si un /daily_cog expose un getter facultatif)
        daily_cd_txt = None
        try:
            # on tente d’importer dynamiquement une fonction facultative
            from cogs.daily_cog import get_daily_cooldown_string  # type: ignore
            # si elle existe, on lui passe l’ID
            daily_cd_txt = await get_daily_cooldown_string(target.id)  # doit renvoyer une str prête à afficher
        except Exception:
            pass

        embed = discord.Embed(
            title=f"Inventaire — {target.display_name}",
            color=discord.Color.teal()
        )
        embed.set_thumbnail(url=target.display_avatar.url if target.display_avatar else discord.Embed.Empty)
        embed.add_field(name="Objets", value=_format_items(items), inline=False)
        embed.add_field(name="🎟️ Tickets", value=str(tickets), inline=True)
        embed.add_field(name="💰 GoldValis", value=str(gold), inline=True)

        if daily_cd_txt:
            embed.add_field(name="📆 Daily", value=daily_cd_txt, inline=False)
        else:
            embed.add_field(name="📆 Daily", value="Utilise `/daily` pour récupérer ton ticket journalier.", inline=False)

        await inter.followup.send(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(InventoryCog(bot))

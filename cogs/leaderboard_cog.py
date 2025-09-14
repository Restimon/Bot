# cogs/leaderboard_cog.py
from __future__ import annotations
import discord
from discord import app_commands
from discord.ext import commands

try:
    from data import storage
except Exception:
    storage = None

class LeaderboardCog(commands.Cog):
    """Classement simple (points / kills / deaths), basé sur data.storage.leaderboard."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="leaderboard", description="Affiche le classement GotValis du serveur.")
    @app_commands.describe(critere="points | kills | deaths", limite="Combien afficher (1-25)")
    async def leaderboard(
        self,
        inter: discord.Interaction,
        critere: str = "points",
        limite: int = 10
    ):
        await inter.response.defer(thinking=True)

        if storage is None:
            return await inter.followup.send("Classement indisponible (storage non initialisé).")

        gid = str(inter.guild_id)
        data = storage.leaderboard.get(gid, {})
        if not data:
            return await inter.followup.send("Aucun classement pour l’instant.")

        critere = critere.lower()
        key = {"points": "points", "kills": "kills", "deaths": "deaths"}.get(critere, "points")

        limite = max(1, min(25, int(limite)))
        items = sorted(
            data.items(),
            key=lambda kv: int(kv[1].get(key, 0)),
            reverse=True
        )[:limite]

        lines = []
        for rank, (uid, stats) in enumerate(items, start=1):
            p = int(stats.get("points", 0))
            k = int(stats.get("kills", 0))
            d = int(stats.get("deaths", 0))
            lines.append(f"**#{rank}** <@{uid}> — **{p}** pts | 🗡 {k} | ☠️ {d}")

        embed = discord.Embed(
            title=f"🏆 Leaderboard — {inter.guild.name}",
            description="\n".join(lines),
            color=discord.Color.gold()
        )
        embed.set_footer(text=f"Critère: {key} • Top {limite}")
        await inter.followup.send(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(LeaderboardCog(bot))

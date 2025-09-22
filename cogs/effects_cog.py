# cogs/effects_cog.py
from __future__ import annotations

import asyncio
import discord
from discord.ext import commands
from effects_db import effects_loop, set_broadcaster

class EffectsCog(commands.Cog):
    """
    Branche un broadcaster d'effets (ticks DoT/HoT).
    ⚠️ Ne démarre PAS une deuxième boucle si le combat_cog l’a déjà lancée.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Broadcaster simple : envoie un embed dans le salon demandé par effects_db
        set_broadcaster(self._broadcast)

    async def _broadcast(self, guild_id: int, channel_id: int, payload: dict):
        guild = self.bot.get_guild(int(guild_id))
        if not guild:
            return
        ch = guild.get_channel(int(channel_id))
        if not isinstance(ch, (discord.TextChannel, discord.Thread, discord.ForumChannel)):
            return

        title = str(payload.get("title") or "GotValis")
        lines = payload.get("lines") or []
        color = int(payload.get("color") or discord.Color.blurple().value)

        embed = discord.Embed(title=title, description="\n".join(map(str, lines)), color=color)
        await ch.send(embed=embed)

    @commands.Cog.listener()
    async def on_ready(self):
        # Démarre la boucle des effets UNIQUEMENT si aucune autre boucle ne tourne
        if getattr(self.bot, "_effects_loop_started", False):
            return

        async def providers():
            # Pas de canaux par défaut ici (combat_cog enregistre déjà les cibles).
            # On renvoie une liste vide => les ticks sont calculés, mais pas de broadcast
            # si aucun autre cog n'a fourni de cibles (OK par défaut).
            return []

        self.bot._effects_loop_started = True
        asyncio.create_task(effects_loop(get_targets=providers, interval=60))

async def setup(bot: commands.Bot):
    await bot.add_cog(EffectsCog(bot))

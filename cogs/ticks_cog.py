# cogs/ticks_cog.py
from __future__ import annotations
import asyncio, time
import discord
from discord.ext import commands
from passifs import trigger

class TicksCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot=bot
        self._task = asyncio.create_task(self._loop())
    def cog_unload(self): self._task.cancel()

    async def _loop(self):
        await self.bot.wait_until_ready()
        prev_hour = prev_half = 0
        while not self.bot.is_closed():
            now = int(time.time())
            # toutes les 60 min
            if now - prev_hour >= 3600:
                prev_hour = now
                for g in self.bot.guilds:
                    for m in g.members:
                        if m.bot: continue
                        try:
                            await trigger("on_hourly_tick", user_id=m.id)
                        except Exception: pass
            # toutes les 30 min
            if now - prev_half >= 1800:
                prev_half = now
                for g in self.bot.guilds:
                    for m in g.members:
                        if m.bot: continue
                        try:
                            await trigger("on_half_hour_tick", user_id=m.id)
                        except Exception: pass
            await asyncio.sleep(10)

async def setup(bot): await bot.add_cog(TicksCog(bot))

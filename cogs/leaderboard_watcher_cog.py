# cogs/leaderboard_watcher_cog.py
from __future__ import annotations

import asyncio
from typing import Set

import discord
from discord.ext import commands

from leaderboard import init_leaderboard_db, ensure_and_update_message

# files externes peuvent appeler ceci pour rafraîchir "à la volée"
_DIRTY_GUILDS: Set[int] = set()

def mark_leaderboard_dirty(guild_id: int) -> None:
    _DIRTY_GUILDS.add(int(guild_id))

class LeaderboardWatcher(commands.Cog):
    def __init__(self, bot: commands.Bot, interval: int = 60):
        self.bot = bot
        self.interval = interval
        self._task: asyncio.Task | None = None

    async def cog_load(self):
        await init_leaderboard_db()
        self._task = asyncio.create_task(self._loop())

    async def cog_unload(self):
        if self._task:
            self._task.cancel()

    async def _loop(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            try:
                # 1) guilds marqués "dirty" -> update immédiat
                dirty = list(_DIRTY_GUILDS)
                _DIRTY_GUILDS.clear()
                for gid in dirty:
                    guild = self.bot.get_guild(gid)
                    if guild:
                        await ensure_and_update_message(guild)

                # 2) scan périodique
                for guild in self.bot.guilds:
                    await ensure_and_update_message(guild)
            except Exception:
                pass
            await asyncio.sleep(self.interval)

async def setup(bot: commands.Bot):
    await bot.add_cog(LeaderboardWatcher(bot))

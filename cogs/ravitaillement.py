# cogs/ravitaillement.py
from __future__ import annotations

import asyncio
import random
from typing import Dict

import discord
from discord.ext import commands, tasks

from inventory_db import add_item
from economy_db import add_balance

BOX_EMOJI = "📦"   # sert aussi pour claim
CLAIM_EMOJI = BOX_EMOJI

BASIC_ITEMS = ["🍀", "❄️", "🧪", "🩹", "💊"]  # petit pool simple

class RavitaillementCog(commands.Cog):
    """
    Mini ravitaillement basique déclenché par activité:
      • Surveille l’activité des salons et poste un petit drop de temps en temps.
      • Les 3 premiers à réagir avec ✅ gagnent une petite récompense (item x1-2 ou 10-30 coins).
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._last_channel: Dict[int, int] = {}  # guild_id -> channel_id
        self._ticker.start()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return
        self._last_channel[message.guild.id] = message.channel.id

    @tasks.loop(minutes=15)
    async def _ticker(self):
        for guild in self.bot.guilds:
            chan_id = self._last_channel.get(guild.id)
            if not chan_id:
                continue
            ch = guild.get_channel(chan_id)
            if not ch:
                continue
            # 1 chance sur 4 toutes les 15 min si le salon a eu de l'activité
            if random.random() < 0.25:
                await self._post_box(ch)

    @_ticker.before_loop
    async def _before(self):
        await self.bot.wait_until_ready()

    async def _post_box(self, ch: discord.TextChannel):
        embed = discord.Embed(
            title=f"{BOX_EMOJI} Ravitaillement léger",
            description=f"Réagis avec {CLAIM_EMOJI} pour tenter ta chance ! (3 gagnants maxi)",
            color=discord.Color.blurple(),
        )
        msg = await ch.send(embed=embed)
        try:
            await msg.add_reaction(CLAIM_EMOJI)
        except Exception:
            pass

        winners = set()

        def check(payload: discord.RawReactionActionEvent):
            return payload.message_id == msg.id and str(payload.emoji) == CLAIM_EMOJI and payload.user_id != self.bot.user.id

        try:
            while len(winners) < 3:
                payload = await self.bot.wait_for("raw_reaction_add", check=check, timeout=120)
                winners.add(payload.user_id)
                # récompense soft
                if random.random() < 0.6:
                    emoji = random.choice(BASIC_ITEMS)
                    await add_item(payload.user_id, emoji, random.randint(1, 2))
                else:
                    await add_balance(payload.user_id, random.randint(10, 30), reason="ravitaillement")
        except asyncio.TimeoutError:
            pass

async def setup(bot: commands.Bot):
    await bot.add_cog(RavitaillementCog(bot))

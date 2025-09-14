# cogs/ravitaillement.py
from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass
from typing import Dict, Optional, Set, List, Tuple

import discord
from discord.ext import commands

BOX_EMOJI = "📦"
DROP_AFTER_MIN = 12
DROP_AFTER_MAX = 30
CLAIM_SECONDS = 30

try:
    from data import storage
except Exception:
    storage = None

try:
    from utils import get_random_item, OBJETS
except Exception:
    def get_random_item(debug: bool = False):
        return random.choice(["🍀", "❄️", "🧪", "🩹", "💊"])
    OBJETS = {}

@dataclass
class PendingDrop:
    message_id: int
    channel_id: int
    guild_id: int
    expires_at: float
    claimers: Set[int]

class Ravitaillement(commands.Cog):
    """
    Auto-drop toutes les 12 à 30 interactions 'éligibles' (messages dans les salons où le bot
    peut réagir). Un seul drop actif à la fois par serveur.
    À la fin : on attribue les objets et on poste un récap. Si personne : 'Ravitaillement détruit'.
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._armed_after: Dict[int, int] = {}   # guild_id -> compteur cible (12..30)
        self._count: Dict[int, int] = {}         # guild_id -> compte courant
        self._active: Dict[int, PendingDrop] = {}  # guild_id -> drop actif

    def _roll_next_threshold(self, guild_id: int):
        self._armed_after[guild_id] = random.randint(DROP_AFTER_MIN, DROP_AFTER_MAX)
        self._count[guild_id] = 0

    def _stack_quantity_for_item(self, emoji: str) -> int:
        """Quantité selon rareté (OBJETS[emoji]['rarete'])."""
        info = OBJETS.get(emoji, {})
        rarete = int(info.get("rarete", 25))
        if rarete <= 3:
            return random.randint(3, 4)
        elif rarete <= 6:
            return random.randint(2, 3)
        elif rarete <= 10:
            return random.randint(1, 2)
        elif rarete <= 16:
            return 1
        elif rarete <= 20:
            return 1
        else:
            return 1

    async def _spawn_drop(self, channel: discord.TextChannel):
        embed = discord.Embed(
            title="📦 Ravitaillement GotValis",
            color=discord.Color.blurple(),
        )
        msg = await channel.send(embed=embed)
        try:
            await msg.add_reaction(BOX_EMOJI)
        except Exception:
            pass

        expires_at = self.bot.loop.time() + CLAIM_SECONDS
        self._active[channel.guild.id] = PendingDrop(
            message_id=msg.id,
            channel_id=channel.id,
            guild_id=channel.guild.id,
            expires_at=expires_at,
            claimers=set()
        )

        # timer de fin
        async def _end():
            await asyncio.sleep(CLAIM_SECONDS)
            await self._finalize_drop(channel.guild.id)

        self.bot.loop.create_task(_end())

    async def _finalize_drop(self, guild_id: int):
        pend = self._active.get(guild_id)
        if not pend:
            return

        guild = self.bot.get_guild(guild_id)
        channel = guild.get_channel(pend.channel_id) if guild else None
        if not isinstance(channel, discord.TextChannel):
            self._active.pop(guild_id, None)
            self._roll_next_threshold(guild_id)
            return

        if not pend.claimers:
            # personne n’a réagi
            embed = discord.Embed(
                title="🗑️ Ravitaillement détruit",
                color=discord.Color.dark_grey()
            )
            await channel.send(embed=embed)
            self._active.pop(guild_id, None)
            self._roll_next_threshold(guild_id)
            return

        # distribue maintenant (quantité selon rareté)
        recaps: List[str] = []
        for uid in pend.claimers:
            emoji = get_random_item(debug=False)
            qty = self._stack_quantity_for_item(emoji)
            if storage is not None:
                inv, _, _ = storage.get_user_data(str(guild_id), str(uid))
                for _ in range(max(1, qty)):
                    inv.append(emoji)
            suffix = f" ×{qty}" if qty > 1 else ""
            recaps.append(f"• <@{uid}> — {emoji}{suffix}")

        if storage is not None:
            storage.save_data()

        # envoi récapitulatif
        embed = discord.Embed(
            title="✅ Ravitaillement récupéré",
            color=discord.Color.green()
        )
        text = "\n".join(recaps)
        if len(text) <= 1000:
            embed.add_field(name="Récapitulatif", value=text, inline=False)
        else:
            # découpe si très long
            lines = recaps
            chunk, buf, size = [], [], 0
            for line in lines:
                if size + len(line) + 1 > 1000:
                    chunk.append("\n".join(buf)); buf, size = [line], len(line) + 1
                else:
                    buf.append(line); size += len(line) + 1
            if buf:
                chunk.append("\n".join(buf))
            for i, part in enumerate(chunk, 1):
                embed.add_field(name=f"Récap (p.{i})", value=part, inline=False)

        await channel.send(embed=embed)

        # reset état pour un prochain drop (nouveau tirage 12–30)
        self._active.pop(guild_id, None)
        self._roll_next_threshold(guild_id)

    # ─────────────────────────────────────────────────────────
    # Listeners
    # ─────────────────────────────────────────────────────────
    @commands.Cog.listener()
    async def on_ready(self):
        # init seuils pour tous les serveurs
        for g in self.bot.guilds:
            self._roll_next_threshold(g.id)

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        self._roll_next_threshold(guild.id)

    @commands.Cog.listener()
    async def on_message(self, msg: discord.Message):
        if msg.author.bot or not msg.guild:
            return
        perms = msg.channel.permissions_for(msg.guild.me)
        if not (perms.send_messages and perms.add_reactions):
            return

        gid = msg.guild.id
        # pas de double drop
        if gid in self._active:
            return

        if gid not in self._armed_after:
            self._roll_next_threshold(gid)

        self._count[gid] = self._count.get(gid, 0) + 1
        target = self._armed_after.get(gid, random.randint(DROP_AFTER_MIN, DROP_AFTER_MAX))

        if self._count[gid] >= target:
            # spawn sous CE message (même salon)
            if isinstance(msg.channel, discord.TextChannel):
                await self._spawn_drop(msg.channel)
            else:
                # fallback : rien
                pass

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if str(payload.emoji) != BOX_EMOJI:
            return
        if payload.user_id == self.bot.user.id:
            return
        guild_id = payload.guild_id
        pend = self._active.get(guild_id)
        if not pend or pend.message_id != payload.message_id:
            return
        # encore dans le temps ?
        if self.bot.loop.time() > pend.expires_at:
            return
        pend.claimers.add(payload.user_id)

async def setup(bot: commands.Bot):
    await bot.add_cog(Ravitaillement(bot))

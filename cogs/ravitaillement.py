# cogs/ravitaillement.py
from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass
from typing import Dict, Optional, Set, List

import discord
from discord.ext import commands

BOX_EMOJI = "📦"
DROP_AFTER_MIN = 12
DROP_AFTER_MAX = 30
CLAIM_SECONDS = 30

# Storage (inventaire persistant)
try:
    from data import storage
except Exception:
    storage = None

# Tirage d’objet par rareté (depuis utils)
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
    Auto-drop toutes les 12 à 30 interactions éligibles (messages dans salons où le bot
    peut envoyer des messages et ajouter des réactions). Un seul drop actif par serveur.
    À la fin : on attribue 1 objet par participant et on poste un récap. Si personne : 'Ravitaillement détruit'.
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._armed_after: Dict[int, int] = {}      # guild_id -> seuil (12..30)
        self._count: Dict[int, int] = {}            # guild_id -> compteur courant
        self._active: Dict[int, PendingDrop] = {}   # guild_id -> drop actif

    # ────────────────────────────────────────────────────────
    # Seuil aléatoire par serveur
    # ────────────────────────────────────────────────────────
    def _roll_next_threshold(self, guild_id: int):
        self._armed_after[guild_id] = random.randint(DROP_AFTER_MIN, DROP_AFTER_MAX)
        self._count[guild_id] = 0

    # ────────────────────────────────────────────────────────
    # Création du drop
    # ────────────────────────────────────────────────────────
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

        async def _end():
            await asyncio.sleep(CLAIM_SECONDS)
            await self._finalize_drop(channel.guild.id)

        self.bot.loop.create_task(_end())

    # ────────────────────────────────────────────────────────
    # Finalisation (distribution + récap)
    # ────────────────────────────────────────────────────────
    async def _finalize_drop(self, guild_id: int):
        pend = self._active.get(guild_id)
        if not pend:
            return

        guild = self.bot.get_guild(guild_id)
        channel = guild.get_channel(pend.channel_id) if guild else None
        if not isinstance(channel, discord.TextChannel):
            # canal introuvable → reset
            self._active.pop(guild_id, None)
            self._roll_next_threshold(guild_id)
            return

        # Personne n’a cliqué
        if not pend.claimers:
            embed = discord.Embed(
                title="🗑️ Ravitaillement détruit",
                color=discord.Color.dark_grey()
            )
            await channel.send(embed=embed)
            self._active.pop(guild_id, None)
            self._roll_next_threshold(guild_id)
            return

        # Distribuer 1 objet par participant
        recaps: List[str] = []
        for uid in pend.claimers:
            emoji = get_random_item(debug=False)  # 1 seul item
            if storage is not None:
                inv, _, _ = storage.get_user_data(str(guild_id), str(uid))
                inv.append(emoji)
            recaps.append(f"• <@{uid}> — {emoji}")

        if storage is not None:
            storage.save_data()

        # Récapitulatif
        embed = discord.Embed(
            title="✅ Ravitaillement récupéré",
            color=discord.Color.green()
        )

        text = "\n".join(recaps)
        if len(text) <= 1000:
            embed.add_field(name="Récapitulatif", value=text, inline=False)
        else:
            # Découpage si très long
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

        # Reset pour le prochain drop
        self._active.pop(guild_id, None)
        self._roll_next_threshold(guild_id)

    # ────────────────────────────────────────────────────────
    # Listeners
    # ────────────────────────────────────────────────────────
    @commands.Cog.listener()
    async def on_ready(self):
        # Init des seuils pour tous les serveurs joints
        for g in self.bot.guilds:
            self._roll_next_threshold(g.id)

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        self._roll_next_threshold(guild.id)

    @commands.Cog.listener()
    async def on_message(self, msg: discord.Message):
        # On compte uniquement dans les salons où le bot peut réagir
        if msg.author.bot or not msg.guild:
            return
        perms = msg.channel.permissions_for(msg.guild.me)
        if not (perms.send_messages and perms.add_reactions):
            return

        gid = msg.guild.id
        # Un seul drop actif à la fois
        if gid in self._active:
            return

        if gid not in self._armed_after:
            self._roll_next_threshold(gid)

        self._count[gid] = self._count.get(gid, 0) + 1
        target = self._armed_after.get(gid, random.randint(DROP_AFTER_MIN, DROP_AFTER_MAX))

        if self._count[gid] >= target:
            if isinstance(msg.channel, discord.TextChannel):
                await self._spawn_drop(msg.channel)

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
        # Encore dans la fenêtre de claim ?
        if self.bot.loop.time() > pend.expires_at:
            return
        pend.claimers.add(payload.user_id)

async def setup(bot: commands.Bot):
    await bot.add_cog(Ravitaillement(bot))

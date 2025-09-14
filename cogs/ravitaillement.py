# cogs/ravitaillement.py
from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass
from typing import Dict, Optional, Set, List

import discord
from discord.ext import commands

# Réglages
BOX_EMOJI = "📦"
DROP_AFTER_MIN = 12          # messages minimum avant un drop
DROP_AFTER_MAX = 30          # messages maximum avant un drop
CLAIM_SECONDS = 30           # temps pour cliquer sur 📦
CLAIM_LIMIT = 5              # max de joueurs récompensés (premiers arrivés)

# Storage persistant (inventaires en JSON via data/storage.py)
try:
    from data import storage
except Exception:
    storage = None

# Tirage d'objet cohérent avec la rareté (défini dans utils.py)
try:
    from utils import get_random_item
except Exception:
    # fallback simple si utils indispo
    def get_random_item(debug: bool = False):
        return random.choice(["🍀", "❄️", "🧪", "🩹", "💊"])

@dataclass
class PendingDrop:
    message_id: int
    channel_id: int
    guild_id: int
    expires_at: float
    claimers: Set[int]

class Ravitaillement(commands.Cog):
    """
    Auto-drop toutes les 12 à 30 interactions 'éligibles' (messages dans salons où le bot
    peut envoyer des messages ET ajouter des réactions). Un seul drop actif à la fois par serveur.
    À la fin (30s) : on attribue 1 objet à chacun des **5 premiers** ayant cliqué 📦.
    Si personne n’a cliqué : 'Ravitaillement détruit'.
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._armed_after: Dict[int, int] = {}      # guild_id -> seuil courant (12..30)
        self._count: Dict[int, int] = {}            # guild_id -> compteur de messages
        self._active: Dict[int, PendingDrop] = {}   # guild_id -> drop actif (si présent)

    # ─────────────────────────────────────────────
    # internes
    # ─────────────────────────────────────────────
    def _roll_next_threshold(self, guild_id: int) -> None:
        """Tire un nouveau seuil 12..30 et remet le compteur à 0."""
        self._armed_after[guild_id] = random.randint(DROP_AFTER_MIN, DROP_AFTER_MAX)
        self._count[guild_id] = 0

    async def _spawn_drop(self, channel: discord.TextChannel) -> None:
        """Poste le message de drop + ajoute 📦 + arme le timer de fin."""
        embed = discord.Embed(
            title="📦 Ravitaillement GotValis",
            color=discord.Color.blurple(),
        )
        msg = await channel.send(embed=embed)
        try:
            await msg.add_reaction(BOX_EMOJI)
        except Exception:
            # si on ne peut pas ajouter la réaction, annule le drop
            return

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

    async def _finalize_drop(self, guild_id: int) -> None:
        """Distribue les récompenses (1 item / joueur) ou détruit si personne."""
        pend = self._active.get(guild_id)
        if not pend:
            return

        guild = self.bot.get_guild(guild_id)
        channel = guild.get_channel(pend.channel_id) if guild else None
        if not isinstance(channel, discord.TextChannel):
            # impossible de poster le récap → reset
            self._active.pop(guild_id, None)
            self._roll_next_threshold(guild_id)
            return

        if not pend.claimers:
            # personne n’a cliqué
            embed = discord.Embed(
                title="🗑️ Ravitaillement détruit",
                color=discord.Color.dark_grey()
            )
            await channel.send(embed=embed)
            self._active.pop(guild_id, None)
            self._roll_next_threshold(guild_id)
            return

        # On fige l'ordre des claimers (pas garanti par set) :
        # on relit les réactions pour trier par timestamp — mais simple & robuste :
        # on garde l'ordre arbitraire du set et on coupe à CLAIM_LIMIT (déjà limité à l'ajout).
        winners = list(pend.claimers)[:CLAIM_LIMIT]

        # Attribuer **1 item** par joueur
        recaps: List[str] = []
        for uid in winners:
            emoji = get_random_item(debug=False)
            # Sauvegarde dans data/storage.py
            if storage is not None:
                inv, _, _ = storage.get_user_data(str(guild_id), str(uid))
                inv.append(emoji)
            recaps.append(f"• <@{uid}> — {emoji}")

        if storage is not None:
            try:
                storage.save_data()
            except Exception:
                pass

        # Récap (sans description, titre “récupéré”)
        embed = discord.Embed(
            title="✅ Ravitaillement récupéré",
            color=discord.Color.green()
        )
        text = "\n".join(recaps) if recaps else "Personne."
        # Discord limite ~1024 chars par field value → on découpe si besoin
        if len(text) <= 1000:
            embed.add_field(name="Récapitulatif", value=text, inline=False)
        else:
            lines = recaps
            chunk, buf, size = [], [], 0
            for line in lines:
                if size + len(line) + 1 > 1000:
                    chunk.append("\n".join(buf))
                    buf, size = [line], len(line) + 1
                else:
                    buf.append(line)
                    size += len(line) + 1
            if buf:
                chunk.append("\n".join(buf))
            for i, part in enumerate(chunk, 1):
                embed.add_field(name=f"Récap (p.{i})", value=part, inline=False)

        await channel.send(embed=embed)

        # reset état → prêt pour un prochain drop
        self._active.pop(guild_id, None)
        self._roll_next_threshold(guild_id)

    # ─────────────────────────────────────────────
    # listeners
    # ─────────────────────────────────────────────
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
        """
        Compte uniquement les messages dans les salons où le bot peut
        envoyer des messages ET ajouter des réactions.
        """
        if msg.author.bot or not msg.guild:
            return

        perms = msg.channel.permissions_for(msg.guild.me)
        if not (perms.send_messages and perms.add_reactions):
            return

        gid = msg.guild.id

        # pas de nouveau drop si un est déjà actif
        if gid in self._active:
            return

        if gid not in self._armed_after:
            self._roll_next_threshold(gid)

        # Incrémente le compteur
        self._count[gid] = self._count.get(gid, 0) + 1
        target = self._armed_after.get(gid, random.randint(DROP_AFTER_MIN, DROP_AFTER_MAX))

        if self._count[gid] >= target:
            # spawn sous CE message (même salon)
            if isinstance(msg.channel, discord.TextChannel):
                await self._spawn_drop(msg.channel)

    @commands.Cog.listener())
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        """Enregistre les claimers (limite de 5 premiers)."""
        if str(payload.emoji) != BOX_EMOJI:
            return
        if payload.user_id == getattr(self.bot.user, "id", None):
            return

        guild_id = payload.guild_id
        pend = self._active.get(guild_id)
        if not pend or pend.message_id != payload.message_id:
            return

        # encore dans la fenêtre de claim ?
        if self.bot.loop.time() > pend.expires_at:
            return

        # ✅ Limite aux 5 premiers
        if len(pend.claimers) >= CLAIM_LIMIT:
            return

        pend.claimers.add(payload.user_id)

# Hook d’extension
async def setup(bot: commands.Bot):
    await bot.add_cog(Ravitaillement(bot))

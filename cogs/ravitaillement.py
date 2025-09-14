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
MAX_CLAIMERS = 5

# stockage JSON optionnel (inventaire)
try:
    from data import storage
except Exception:
    storage = None

# tirage d’objet pondéré par rareté
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
    deadline: float
    claimers: Set[int]

class Ravitaillement(commands.Cog):
    """
    Auto-drop toutes les 12–30 interactions éligibles (messages dans salons
    où le bot peut **ajouter une réaction**). Un seul drop actif par serveur.
    On ajoute 📦 au message utilisateur, on collecte jusqu’à 5 joueurs,
    et on poste un récap 30 s plus tard.
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._armed_after: Dict[int, int] = {}    # guild_id -> seuil actuel
        self._count: Dict[int, int] = {}          # guild_id -> compteur
        self._active: Dict[int, PendingDrop] = {} # guild_id -> drop actif
        self._timers: Dict[int, asyncio.Task] = {}# guild_id -> task de fin

    # ── utilitaires internes ─────────────────────────────────
    def _roll_next_threshold(self, guild_id: int):
        self._armed_after[guild_id] = random.randint(DROP_AFTER_MIN, DROP_AFTER_MAX)
        self._count[guild_id] = 0

    def _stack_quantity_for_item(self, emoji: str) -> int:
        """Quantité par rareté (plus rare → qty = 1)."""
        info = OBJETS.get(emoji, {})
        r = int(info.get("rarete", 25))
        if r <= 3:
            return random.randint(3, 4)
        if r <= 6:
            return random.randint(2, 3)
        if r <= 10:
            return random.randint(1, 2)
        return 1

    def _start_timer(self, guild_id: int):
        # annule un timer résiduel si besoin
        old = self._timers.pop(guild_id, None)
        if old and not old.done():
            old.cancel()

        async def _end():
            try:
                await asyncio.sleep(CLAIM_SECONDS)
                await self._finalize_drop(guild_id)
            except asyncio.CancelledError:
                pass

        self._timers[guild_id] = self.bot.loop.create_task(_end())

    async def _add_box_reaction(self, msg: discord.Message) -> None:
        try:
            await msg.add_reaction(BOX_EMOJI)
        except Exception:
            pass

    # ── logique de fin & récap ───────────────────────────────
    async def _finalize_drop(self, guild_id: int):
        pend = self._active.get(guild_id)
        self._timers.pop(guild_id, None)  # plus de timer actif pour ce serveur

        if not pend:
            return

        guild = self.bot.get_guild(guild_id)
        channel = guild.get_channel(pend.channel_id) if guild else None
        if not isinstance(channel, discord.TextChannel):
            self._active.pop(guild_id, None)
            self._roll_next_threshold(guild_id)
            return

        # Fallback: si on a perdu des events de réaction, relire le message
        try:
            msg = await channel.fetch_message(pend.message_id)
            for reaction in msg.reactions:
                try:
                    if str(reaction.emoji) != BOX_EMOJI:
                        continue
                    users = [u async for u in reaction.users(limit=50)]
                    for u in users:
                        if u.bot:
                            continue
                        if len(pend.claimers) >= MAX_CLAIMERS:
                            break
                        pend.claimers.add(u.id)
                except Exception:
                    continue
        except Exception:
            pass

        # Personne ?
        if not pend.claimers:
            try:
                await channel.send(
                    embed=discord.Embed(
                        title="🗑️ Ravitaillement détruit",
                        color=discord.Color.dark_grey(),
                    )
                )
            finally:
                self._active.pop(guild_id, None)
                self._roll_next_threshold(guild_id)
            return

        # Distribuer maintenant (inventaire JSON si dispo)
        lines: List[str] = []
        for uid in list(pend.claimers)[:MAX_CLAIMERS]:
            emoji = get_random_item(debug=False)
            qty = self._stack_quantity_for_item(emoji)

            if storage is not None:
                inv, _, _ = storage.get_user_data(str(guild_id), str(uid))
                for _ in range(qty):
                    inv.append(emoji)

            suffix = f" ×{qty}" if qty > 1 else ""
            lines.append(f"✅ <@{uid}> a récupéré : {emoji}{suffix}")

        if storage is not None:
            storage.save_data()

        embed = discord.Embed(
            title="📦 Ravitaillement récupéré",
            color=discord.Color.green(),
        )
        embed.description = "\n".join(lines)
        try:
            await channel.send(embed=embed)
        finally:
            self._active.pop(guild_id, None)
            self._roll_next_threshold(guild_id)

    # ── listeners ────────────────────────────────────────────
    @commands.Cog.listener()
    async def on_ready(self):
        # init seuils pour les serveurs déjà présents
        for g in self.bot.guilds:
            self._roll_next_threshold(g.id)

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        self._roll_next_threshold(guild.id)

    @commands.Cog.listener()
    async def on_message(self, msg: discord.Message):
        if msg.author.bot or not msg.guild:
            return

        # on ne “compte” que si le bot peut au moins ajouter une réaction
        perms = msg.channel.permissions_for(msg.guild.me)
        if not perms.add_reactions:
            return

        gid = msg.guild.id

        # pas de double drop
        if gid in self._active:
            return

        if gid not in self._armed_after:
            self._roll_next_threshold(gid)

        # incrémenter et comparer au seuil
        self._count[gid] = self._count.get(gid, 0) + 1
        target = self._armed_after[gid]

        if self._count[gid] >= target:
            # armer un drop sur CE message
            await self._add_box_reaction(msg)
            pend = PendingDrop(
                message_id=msg.id,
                channel_id=msg.channel.id,
                guild_id=gid,
                deadline=self.bot.loop.time() + CLAIM_SECONDS,
                claimers=set(),
            )
            self._active[gid] = pend
            self._start_timer(gid)  # ← lance le timer de fin

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if str(payload.emoji) != BOX_EMOJI:
            return
        if payload.user_id == getattr(self.bot.user, "id", None):
            return
        gid = payload.guild_id
        pend = self._active.get(gid)
        if not pend or pend.message_id != payload.message_id:
            return
        # encore dans la fenêtre ?
        if self.bot.loop.time() > pend.deadline:
            return
        if len(pend.claimers) >= MAX_CLAIMERS:
            return
        pend.claimers.add(payload.user_id)

async def setup(bot: commands.Bot):
    await bot.add_cog(Ravitaillement(bot))

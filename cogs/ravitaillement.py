# cogs/ravitaillement.py
from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass
from typing import Dict, Set, List

import discord
from discord.ext import commands

# Fenêtre & limites
DROP_AFTER_MIN = 5
DROP_AFTER_MAX = 22
CLAIM_SECONDS = 30
MAX_CLAIMERS = 5

# Tirage d’objet pondéré par rareté (utils.py)
try:
    from utils import get_random_item, OBJETS  # get_random_item() -> str (emoji), OBJETS[emoji] -> meta
except Exception:
    def get_random_item(debug: bool = False):
        return random.choice(["🍀", "❄️", "🧪", "🩹", "💊"])
    OBJETS = {}

# Inventaire (SQLite)
try:
    from inventory_db import add_item
except Exception:
    add_item = None  # type: ignore


@dataclass
class PendingDrop:
    message_id: int
    channel_id: int
    guild_id: int
    deadline: float
    claimers: Set[int]
    item_emoji: str  # <- l'objet à récupérer (emoji)


class Ravitaillement(commands.Cog):
    """
    Auto-drop toutes les 5–22 interactions éligibles (messages dans salons
    où le bot peut **ajouter une réaction**). Un seul drop actif par serveur.

    Lors du drop, le bot ajoute **l'emoji de l'objet** au message utilisateur.
    Les membres réagissent avec **ce même emoji** pour le récupérer pendant 30s,
    jusqu'à MAX_CLAIMERS gagnants. À la fin, un récap est posté, les gagnants
    reçoivent l'objet (quantité selon la rareté), et le compteur est réarmé.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._armed_after: Dict[int, int] = {}    # guild_id -> seuil actuel
        self._count: Dict[int, int] = {}          # guild_id -> compteur courant
        self._active: Dict[int, PendingDrop] = {} # guild_id -> drop actif
        self._timers: Dict[int, asyncio.Task] = {}# guild_id -> task de fin

    # ── utilitaires internes ─────────────────────────────────
    def _roll_next_threshold(self, guild_id: int):
        self._armed_after[guild_id] = random.randint(DROP_AFTER_MIN, DROP_AFTER_MAX)
        self._count[guild_id] = 0

    def _stack_quantity_for_item(self, emoji: str) -> int:
        """Quantité accordée en fonction de la rareté (plus rare → moins d'unités)."""
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

    async def _add_item_reaction(self, msg: discord.Message, emoji: str) -> None:
        try:
            await msg.add_reaction(emoji)
        except Exception:
            pass

    # ── logique de fin & récap ───────────────────────────────
    async def _finalize_drop(self, guild_id: int):
        pend = self._active.get(guild_id)
        self._timers.pop(guild_id, None)

        if not pend:
            return

        guild = self.bot.get_guild(guild_id)
        channel = guild.get_channel(pend.channel_id) if guild else None
        if not isinstance(channel, discord.TextChannel):
            self._active.pop(guild_id, None)
            self._roll_next_threshold(guild_id)
            return

        # Fallback: relire le message pour récupérer les réactions si des events manquent
        try:
            msg = await channel.fetch_message(pend.message_id)
            for reaction in msg.reactions:
                try:
                    if str(reaction.emoji) != pend.item_emoji:
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

        if not pend.claimers:
            try:
                await channel.send(
                    embed=discord.Embed(
                        title="🗑️ Ravitaillement expiré",
                        description=f"Aucun joueur n'a récupéré l'objet {pend.item_emoji}.",
                        color=discord.Color.dark_grey(),
                    )
                )
            finally:
                self._active.pop(guild_id, None)
                self._roll_next_threshold(guild_id)
            return

        # Distribuer maintenant (inventaire SQL si dispo)
        lines: List[str] = []
        for uid in list(pend.claimers)[:MAX_CLAIMERS]:
            qty = self._stack_quantity_for_item(pend.item_emoji)

            if add_item is not None:
                try:
                    await add_item(uid, pend.item_emoji, qty)
                except Exception:
                    pass

            suffix = f" ×{qty}" if qty > 1 else ""
            lines.append(f"✅ <@{uid}> a récupéré : {pend.item_emoji}{suffix}")

        embed = discord.Embed(
            title="🎯 Ravitaillement récupéré",
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
        if not perms.add_reactions:
            return

        gid = msg.guild.id

        if gid in self._active:
            return

        if gid not in self._armed_after:
            self._roll_next_threshold(gid)

        self._count[gid] = self._count.get(gid, 0) + 1
        target = self._armed_after[gid]   # ✅ pas d'espace

        if self._count[gid] >= target:
            item_emoji = get_random_item(debug=False)
            await self._add_item_reaction(msg, item_emoji)

            pend = PendingDrop(
                message_id=msg.id,
                channel_id=msg.channel.id,
                guild_id=gid,
                deadline=self.bot.loop.time() + CLAIM_SECONDS,
                claimers=set(),
                item_emoji=item_emoji,
            )
            self._active[gid] = pend
            self._start_timer(gid)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        gid = payload.guild_id
        pend = self._active.get(gid)
        if not pend or pend.message_id != payload.message_id:
            return

        if str(payload.emoji) != pend.item_emoji:
            return

        if payload.user_id == getattr(self.bot.user, "id", None):
            return

        if self.bot.loop.time() > pend.deadline:
            return

        if len(pend.claimers) >= MAX_CLAIMERS:
            return

        pend.claimers.add(payload.user_id)


async def setup(bot: commands.Bot):
    """
    Charge le cog en écrasant proprement une version déjà chargée (hot-reload,
    collision de nom avec un autre module, etc.).
    """
    # Méthode moderne (si supportée par ta version de discord.py)
    try:
        await bot.add_cog(Ravitaillement(bot), override=True)  # type: ignore[call-arg]
        return
    except TypeError:
        # Anciennes versions: pas d'argument override -> on retire puis on rajoute
        pass

    # Fallback universel
    if bot.get_cog("Ravitaillement") is not None:
        bot.remove_cog("Ravitaillement")
    await bot.add_cog(Ravitaillement(bot))

# cogs/ravitaillement.py
from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass
from typing import Dict, Optional, Set, List

import discord
from discord.ext import commands

BOX_EMOJI = "📦"
DROP_AFTER_MIN = 10
DROP_AFTER_MAX = 25
CLAIM_SECONDS = 30
COIN_CHANCE = 0.10  # "faible taux" pour l'or
COIN_MIN = 15
COIN_MAX = 50
MAX_CLAIMERS = 5

# ─────────── imports souples ───────────
try:
    # stockage JSON (inventaire côté /data/storage.py)
    from data import storage
except Exception:
    storage = None  # on tournera sans persistance si absent

# Items pondérés par rareté + helper de tirage
try:
    from utils import get_random_item, OBJETS, REWARD_EMOJIS
except Exception:
    def get_random_item(debug: bool = False):
        # fallback simple si utils absent
        return random.choice(["🍀", "❄️", "🧪", "🩹", "💊"])
    OBJETS = {}
    REWARD_EMOJIS = []

# Crédit d'or (sqlite) si dispo
try:
    from economy_db import add_balance as add_gold
except Exception:
    async def add_gold(user_id: int, delta: int, reason: str = "") -> int:
        return 0  # no-op fallback


def _item_without_coins() -> str:
    """
    Tire un item via utils.get_random_item mais en excluant les 'reward emojis' (ex: 💰).
    Si utils indisponible, tombe sur un choix simple.
    """
    for _ in range(10):
        e = get_random_item(debug=False)
        if e not in REWARD_EMOJIS:
            return e
    # secours: n'importe quelle clé connue d'OBJETS, sinon un pool trivial
    pool = [k for k in OBJETS.keys() if k not in REWARD_EMOJIS]
    if pool:
        return random.choice(pool)
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
    Ravitaillement automatique :
      • Déclenchement après 12–30 messages (aléatoire) dans un salon où le bot peut réagir.
      • Le bot ajoute 📦 sur le message déclencheur (pas de post séparé).
      • 5 premiers cliquent → enregistrés. 30 s plus tard : embed récap.
      • 1 récompense / personne : (10% or 15–50) sinon 1 item pondéré par rareté.
      • Si 0 participant → “Ravitaillement détruit”.
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._armed_after: Dict[int, int] = {}      # guild_id -> seuil (12..30)
        self._count: Dict[int, int] = {}            # guild_id -> compteur
        self._active: Dict[int, PendingDrop] = {}   # guild_id -> drop actif

    # ─────────── helpers internes ───────────
    def _roll_next_threshold(self, guild_id: int):
        self._armed_after[guild_id] = random.randint(DROP_AFTER_MIN, DROP_AFTER_MAX)
        self._count[guild_id] = 0

    async def _spawn_on_message(self, msg: discord.Message):
        """Pose 📦 sur le message et arme un drop actif pour 30 s."""
        try:
            await msg.add_reaction(BOX_EMOJI)
        except Exception:
            return  # pas les perms pour réagir, abandon

        pend = PendingDrop(
            message_id=msg.id,
            channel_id=msg.channel.id,
            guild_id=msg.guild.id,
            expires_at=self.bot.loop.time() + CLAIM_SECONDS,
            claimers=set(),
        )
        self._active[msg.guild.id] = pend

        async def _end():
            await asyncio.sleep(CLAIM_SECONDS)
            await self._finalize_drop(msg.guild.id)

        self.bot.loop.create_task(_end())

    async def _finalize_drop(self, guild_id: int):
        pend = self._active.get(guild_id)
        if not pend:
            return

        guild = self.bot.get_guild(guild_id)
        channel = guild.get_channel(pend.channel_id) if guild else None
        if not isinstance(channel, discord.TextChannel):
            # reset silencieux si le salon n'existe plus
            self._active.pop(guild_id, None)
            self._roll_next_threshold(guild_id)
            return

        # Personne ?
        if not pend.claimers:
            embed = discord.Embed(
                title="🗑️ Ravitaillement détruit",
                color=discord.Color.dark_grey(),
            )
            await channel.send(embed=embed)
            self._active.pop(guild_id, None)
            self._roll_next_threshold(guild_id)
            return

        # Récompenses (1 par personne)
        lines: List[str] = []
        for uid in list(pend.claimers)[:MAX_CLAIMERS]:
            # or (faible) sinon item
            if random.random() < COIN_CHANCE:
                amount = random.randint(COIN_MIN, COIN_MAX)
                try:
                    await add_gold(uid, amount, reason="Ravitaillement")
                except Exception:
                    pass  # on ne casse pas le récap si l'économie n'est pas dispo
                lines.append(f"✅ <@{uid}> a récupéré : **💰 {amount} GoldValis**")
            else:
                item = _item_without_coins()
                if storage is not None:
                    inv, _, _ = storage.get_user_data(str(guild_id), str(uid))
                    inv.append(item)
                lines.append(f"✅ <@{uid}> a récupéré : **{item}**")

        if storage is not None:
            storage.save_data()

        # Embed final (comme ton screenshot)
        embed = discord.Embed(
            title="📦 Ravitaillement récupéré",
            color=discord.Color.green(),
        )
        embed.description = "\n".join(lines)
        await channel.send(embed=embed)

        # reset pour un prochain drop
        self._active.pop(guild_id, None)
        self._roll_next_threshold(guild_id)

    # ─────────── listeners ───────────
    @commands.Cog.listener()
    async def on_ready(self):
        for g in self.bot.guilds:
            self._roll_next_threshold(g.id)

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        self._roll_next_threshold(guild.id)

    @commands.Cog.listener()
    async def on_message(self, msg: discord.Message):
        # on ne compte que les messages "humains" dans les text channels
        if msg.author.bot or not msg.guild or not isinstance(msg.channel, discord.TextChannel):
            return
        perms = msg.channel.permissions_for(msg.guild.me)
        if not (perms.add_reactions and perms.send_messages):
            return

        gid = msg.guild.id

        # Si un drop est déjà actif dans ce serveur → on ne re-déclenche pas
        if gid in self._active:
            return

        if gid not in self._armed_after:
            self._roll_next_threshold(gid)

        # Incrémente, compare au seuil, spawn si atteint
        self._count[gid] = self._count.get(gid, 0) + 1
        target = self._armed_after.get(gid, random.randint(DROP_AFTER_MIN, DROP_AFTER_MAX))
        if self._count[gid] >= target:
            await self._spawn_on_message(msg)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        # on prend uniquement 📦, pas soi-même
        if str(payload.emoji) != BOX_EMOJI:
            return
        if payload.user_id == getattr(self.bot.user, "id", None):
            return
        gid = payload.guild_id
        pend = self._active.get(gid)
        if not pend or payload.message_id != pend.message_id:
            return
        # encore dans le temps ?
        if self.bot.loop.time() > pend.expires_at:
            return
        # limite à 5 premiers
        if len(pend.claimers) >= MAX_CLAIMERS:
            return
        pend.claimers.add(payload.user_id)


async def setup(bot: commands.Bot):
    await bot.add_cog(Ravitaillement(bot))

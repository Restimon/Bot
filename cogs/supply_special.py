# cogs/supply_special.py
from __future__ import annotations

import asyncio
import random
import datetime as dt
from dataclasses import dataclass
from typing import Dict, Optional, Set, List, Tuple

import discord
from discord.ext import commands

BOX_EMOJI = "📦"
CLAIM_SECONDS = 5 * 60          # 5 minutes
MAX_CLAIMERS = 5

# Fenêtres horaires (heures locales du process)
WINDOWS: List[Tuple[int, int]] = [(8, 12), (14, 17), (19, 23)]
MSG_THRESHOLD = 30              # messages éligibles pour activer les chances
BASE_MINUTE_CHANCE = 0.005      # 0.5 % au début
INCREMENT_PER_MIN = 0.005       # +0.5 % / min
MAX_MINUTE_CHANCE = 0.05        # 5 % cap

TICKET_EMOJI = "🎟️"

# ── dépendances souples ─────────────────────────────────────
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

# économie (si dispo, on crédite en base ; sinon on ignore proprement)
try:
    from economy_db import add_balance
except Exception:
    add_balance = None


@dataclass
class PendingDrop:
    message_id: int
    channel_id: int
    guild_id: int
    deadline: float
    claimers: Set[int]


class SpecialSupply(commands.Cog):
    """
    Ravitaillement spécial, déclenché automatiquement dans des créneaux horaires.
    Réagit avec 📦 sur le dernier message 'éligible' (où le bot peut add_reactions).
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot

        # état par serveur
        self._active: Dict[int, PendingDrop] = {}            # drop en cours
        self._timer: Dict[int, asyncio.Task] = {}            # task de fin
        self._last_eligible_msg: Dict[int, Tuple[int, int]] = {}  # guild_id -> (channel_id, message_id)

        # suivi de fenêtre
        self._window_start: Dict[int, dt.datetime] = {}      # début courant de fenêtre
        self._messages_in_window: Dict[int, int] = {}        # nb messages éligibles
        self._armed: Dict[int, bool] = {}                    # True après 30 msgs
        self._dropped_this_window: Dict[int, bool] = {}      # pour éviter doubles drops

        # boucle minute
        self._ticker_task: Optional[asyncio.Task] = None

    # ── utils horaires ───────────────────────────────────────
    def _now(self) -> dt.datetime:
        return dt.datetime.now()

    def _in_window(self, when: Optional[dt.datetime] = None) -> Optional[Tuple[dt.datetime, dt.datetime]]:
        """
        Retourne (start,end) de la fenêtre en cours si on est dedans, sinon None.
        """
        t = when or self._now()
        for start_h, end_h in WINDOWS:
            start = t.replace(hour=start_h, minute=0, second=0, microsecond=0)
            end = t.replace(hour=end_h, minute=0, second=0, microsecond=0)
            if start <= t < end:
                return start, end
        return None

    def _minute_chance(self, start: dt.datetime, now: dt.datetime) -> float:
        mins = int((now - start).total_seconds() // 60)
        return min(MAX_MINUTE_CHANCE, BASE_MINUTE_CHANCE + INCREMENT_PER_MIN * max(0, mins))

    def _reset_window_state(self, guild_id: int, start: Optional[dt.datetime] = None):
        self._window_start[guild_id] = start or self._now()
        self._messages_in_window[guild_id] = 0
        self._armed[guild_id] = False
        self._dropped_this_window[guild_id] = False

    def _ensure_window_state(self, guild_id: int):
        if guild_id not in self._window_start:
            self._reset_window_state(guild_id)

    # ── récompenses ──────────────────────────────────────────
    def _stack_quantity_for_item(self, emoji: str) -> int:
        info = OBJETS.get(emoji, {})
        r = int(info.get("rarete", 25))
        if r <= 3:
            return random.randint(3, 4)
        if r <= 6:
            return random.randint(2, 3)
        if r <= 10:
            return random.randint(1, 2)
        return 1

    async def _grant_reward(self, guild_id: int, user_id: int) -> str:
        """
        15% Gold (100–150), 15% Tickets (1–2), sinon item via get_random_item().
        Retourne une ligne de récap formatée.
        """
        roll = random.random()
        if roll < 0.15:
            amount = random.randint(100, 150)
            if add_balance:
                try:
                    await add_balance(user_id, amount, reason="Supply spécial")
                except Exception:
                    pass
            # (optionnel) si pas de DB & storage dispo, on peut ignorer/ajouter un pseudo-field
            return f"✅ <@{user_id}> a obtenu : 💰 **{amount} GoldValis**"
        elif roll < 0.30:
            qty = random.randint(1, 2)
            if storage is not None:
                inv, _, _ = storage.get_user_data(str(guild_id), str(user_id))
                for _ in range(qty):
                    inv.append(TICKET_EMOJI)
            return f"✅ <@{user_id}> a obtenu : {TICKET_EMOJI} ×{qty}"
        else:
            emoji = get_random_item(debug=False)
            qty = self._stack_quantity_for_item(emoji)
            if storage is not None:
                inv, _, _ = storage.get_user_data(str(guild_id), str(user_id))
                for _ in range(qty):
                    inv.append(emoji)
            suffix = f" ×{qty}" if qty > 1 else ""
            return f"✅ <@{user_id}> a obtenu : {emoji}{suffix}"

    # ── spawn / timer / recap ────────────────────────────────
    async def _spawn_on_last_message(self, guild_id: int) -> bool:
        """
        Pose 📦 sur le dernier message éligible enregistré pour le serveur.
        """
        if guild_id in self._active:
            return False

        last = self._last_eligible_msg.get(guild_id)
        if not last:
            return False
        channel_id, message_id = last

        guild = self.bot.get_guild(guild_id)
        channel = guild.get_channel(channel_id) if guild else None
        if not isinstance(channel, discord.TextChannel):
            return False
        try:
            msg = await channel.fetch_message(message_id)
        except Exception:
            return False

        # ajoute 📦
        try:
            await msg.add_reaction(BOX_EMOJI)
        except Exception:
            return False

        pend = PendingDrop(
            message_id=message_id,
            channel_id=channel_id,
            guild_id=guild_id,
            deadline=self.bot.loop.time() + CLAIM_SECONDS,
            claimers=set(),
        )
        self._active[guild_id] = pend

        # timer
        old = self._timer.pop(guild_id, None)
        if old and not old.done():
            old.cancel()

        async def _end():
            try:
                await asyncio.sleep(CLAIM_SECONDS)
                await self._finalize_drop(guild_id)
            except asyncio.CancelledError:
                pass

        self._timer[guild_id] = self.bot.loop.create_task(_end())
        self._dropped_this_window[guild_id] = True
        return True

    async def _finalize_drop(self, guild_id: int):
        pend = self._active.get(guild_id)
        self._timer.pop(guild_id, None)

        if not pend:
            return

        guild = self.bot.get_guild(guild_id)
        channel = guild.get_channel(pend.channel_id) if guild else None
        if not isinstance(channel, discord.TextChannel):
            self._active.pop(guild_id, None)
            return

        # Fallback : relire les réactions
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

        if not pend.claimers:
            # personne
            try:
                await channel.send(
                    embed=discord.Embed(
                        title="🗑️ Ravitaillement spécial détruit",
                        color=discord.Color.dark_grey(),
                    )
                )
            finally:
                self._active.pop(guild_id, None)
            return

        # Récompenses (une par personne)
        lines: List[str] = []
        for uid in list(pend.claimers)[:MAX_CLAIMERS]:
            line = await self._grant_reward(guild_id, uid)
            lines.append(line)

        if storage is not None:
            storage.save_data()

        embed = discord.Embed(
            title="📦 Ravitaillement spécial récupéré",
            color=discord.Color.gold(),
        )
        embed.description = "\n".join(lines)
        await channel.send(embed=embed)

        self._active.pop(guild_id, None)

    # ── boucle minute : gère les fenêtres & chances ─────────
    async def _ticker(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            now = self._now()

            for g in list(self._last_eligible_msg.keys() | set(x.id for x in self.bot.guilds)):
                win = self._in_window(now)
                if not win:
                    # hors fenêtre → reset pour prochaine
                    self._reset_window_state(g)
                    continue

                start, end = win
                # Si nouvelle fenêtre (changement de tranche)
                if self._window_start.get(g) != start:
                    self._reset_window_state(g, start)

                # Si drop déjà tombé pendant la fenêtre, on ne refait rien
                if self._dropped_this_window.get(g):
                    continue

                # Faut au moins 30 messages pour “armer” la fenêtre
                self._armed[g] = self._messages_in_window.get(g, 0) >= MSG_THRESHOLD
                if not self._armed[g]:
                    continue

                # Dernière minute de la fenêtre → drop garanti
                if (end - now).total_seconds() <= 60:
                    await self._spawn_on_last_message(g)
                    continue

                # Chance croissante minute par minute
                p = self._minute_chance(start, now)
                if random.random() < p:
                    await self._spawn_on_last_message(g)

            # tick toute les 60s
            try:
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                break

    # ── listeners ───────────────────────────────────────────
    @commands.Cog.listener()
    async def on_ready(self):
        # init tracé fenêtres & démarrage boucle
        for g in self.bot.guilds:
            self._reset_window_state(g.id)
        if not self._ticker_task or self._ticker_task.done():
            self._ticker_task = self.bot.loop.create_task(self._ticker())

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        self._reset_window_state(guild.id)

    @commands.Cog.listener()
    async def on_message(self, msg: discord.Message):
        if msg.author.bot or not msg.guild:
            return
        # on ne retient que les messages où le bot peut ajouter des réactions
        perms = msg.channel.permissions_for(msg.guild.me)
        if not perms.add_reactions:
            return

        gid = msg.guild.id
        # mémorise “dernier message éligible”
        self._last_eligible_msg[gid] = (msg.channel.id, msg.id)

        # si on est dans une fenêtre en cours, incrémente le compteur
        win = self._in_window()
        if win:
            start, _ = win
            if self._window_start.get(gid) != start:
                self._reset_window_state(gid, start)
            self._messages_in_window[gid] = self._messages_in_window.get(gid, 0) + 1

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
        if self.bot.loop.time() > pend.deadline:
            return
        if len(pend.claimers) >= MAX_CLAIMERS:
            return
        pend.claimers.add(payload.user_id)


async def setup(bot: commands.Bot):
    await bot.add_cog(SpecialSupply(bot))

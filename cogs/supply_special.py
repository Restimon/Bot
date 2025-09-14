# cogs/supply_special.py
from __future__ import annotations

import asyncio
import random
import datetime as dt
from dataclasses import dataclass
from typing import Dict, Optional, Set, List, Tuple

import discord
from discord.ext import commands, tasks

# Réglages
SPECIAL_EMOJI = "🎖"
CLAIM_WINDOW_SECONDS = 5 * 60
CLAIM_LIMIT = 10
QUALIFY_MESSAGES = 30
CHECK_PERIOD_SECONDS = 60  # boucle par minute

# Chances par minute après qualification
BASE_CHANCE = 0.005          # 0.5%
INCREMENT_PER_MIN = 0.005    # +0.5 pp / min
MAX_CHANCE = 0.08            # cap 8%

# Fenêtres locales (heure serveur)
WINDOWS: List[Tuple[int, int]] = [
    (8, 12),
    (14, 17),
    (19, 23),
]

# storage + économie
try:
    from data import storage
except Exception:
    storage = None

_add_balance = None
try:
    from economy_db import add_balance as _add_balance
except Exception:
    pass

# tirage cohérent par rareté
try:
    from utils import get_random_item, OBJETS
except Exception:
    def get_random_item(debug: bool = False):
        return random.choice(["🍀", "❄️", "🧪", "🩹", "💊"])
    OBJETS = {}

@dataclass
class PendingSpecial:
    message_id: int
    channel_id: int
    guild_id: int
    expires_monotonic: float
    claimers: Set[int]

class SupplySpecial(commands.Cog):
    """
    Supply spécial :
      • Il faut d’abord QUALIFY_MESSAGES durant une fenêtre (8–12 / 14–17 / 19–23).
      • Ensuite, tirage par minute avec prob. croissante ; si toujours rien → drop forcé dernière minute.
      • Spawn UNIQUEMENT dans le dernier salon éligible (où un message a été compté).
      • Claim 5 min via 🎖. Les CLAIM_LIMIT premiers gagnent.
      • Récompenses (par gagnant) :
          - 15% Piège (rien)
          - 15% Soins (1–3 items de soin)
          - 20% GoldValis (100–150)  [via economy_db si dispo, sinon 💰 en inv]
          - 15% Tickets (🎟️ ×1–2)
          - 35% Loot pondéré par rareté (qty selon rareté)
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._window_state: Dict[int, Dict[str, object]] = {}
        # {
        #   gid: {
        #       "qualified": bool,
        #       "qualified_since": datetime,
        #       "minutes_since_qual": int,
        #       "dropped_this_window": bool,
        #       "msg_count": int,
        #       "last_chan_id": Optional[int],
        #   }
        # }
        self._active: Dict[int, PendingSpecial] = {}
        self._tick_loop.start()

    # ---------- Fenêtres ----------
    def _now(self) -> dt.datetime:
        return dt.datetime.now()

    def _in_window(self, now: Optional[dt.datetime] = None) -> Tuple[bool, Optional[Tuple[int, int]]]:
        if now is None:
            now = self._now()
        h = now.hour
        for (a, b) in WINDOWS:
            if a <= h < b:
                return True, (a, b)
        return False, None

    def _is_last_minute(self, now: Optional[dt.datetime] = None) -> bool:
        if now is None:
            now = self._now()
        ok, win = self._in_window(now)
        if not ok or win is None:
            return False
        end_h = win[1]
        return now.hour == end_h - 1 and now.minute == 59

    def _get_state(self, guild_id: int) -> Dict[str, object]:
        st = self._window_state.get(guild_id)
        if not st:
            st = {
                "qualified": False,
                "qualified_since": None,
                "minutes_since_qual": 0,
                "dropped_this_window": False,
                "msg_count": 0,
                "last_chan_id": None,
            }
            self._window_state[guild_id] = st
        return st

    def _reset_window_state(self, guild_id: int) -> None:
        st = self._get_state(guild_id)
        st["qualified"] = False
        st["qualified_since"] = None
        st["minutes_since_qual"] = 0
        st["dropped_this_window"] = False
        st["msg_count"] = 0
        st["last_chan_id"] = None

    # ---------- Récompenses ----------
    def _stack_qty_by_rarete(self, emoji: str) -> int:
        info = OBJETS.get(emoji, {})
        rarete = int(info.get("rarete", 25))
        if rarete <= 3:
            return random.randint(3, 4)
        elif rarete <= 6:
            return random.randint(2, 3)
        elif rarete <= 10:
            return random.randint(1, 2)
        else:
            return 1

    def _pick_heal_item(self) -> str:
        cands = [e for e, d in OBJETS.items() if d.get("type") == "soin"] or ["🍀", "🩸", "🩹", "💊"]
        return random.choice(cands)

    def _grant_inventory(self, guild_id: int, user_id: int, emoji: str, qty: int = 1):
        if storage is None:
            return
        inv, _, _ = storage.get_user_data(str(guild_id), str(user_id))
        for _ in range(max(1, qty)):
            inv.append(emoji)

    def _grant_gold(self, guild_id: int, user_id: int, amount: int) -> bool:
        if _add_balance is not None:
            try:
                asyncio.create_task(_add_balance(user_id, amount, reason="Supply spécial"))
                return True
            except Exception:
                pass
        # fallback en inv
        self._grant_inventory(guild_id, user_id, "💰", qty=max(1, amount // 50))
        return False

    def _grant_tickets(self, guild_id: int, user_id: int, count: int):
        self._grant_inventory(guild_id, user_id, "🎟️", qty=count)

    # ---------- Drop / finalize ----------
    async def _spawn_drop(self, guild: discord.Guild, channel_id_hint: Optional[int]) -> bool:
        """
        Spawn uniquement dans le dernier salon éligible (channel_id_hint).
        S’il n’est pas utilisable → on annule ce tick.
        """
        if guild.id in self._active:
            return False
        if not channel_id_hint:
            return False

        ch = guild.get_channel(channel_id_hint)
        if not isinstance(ch, discord.TextChannel):
            return False

        perms = ch.permissions_for(guild.me)
        if not (perms.send_messages and perms.add_reactions):
            return False

        embed = discord.Embed(
            title="🎖 Supply spécial GotValis",
            color=discord.Color.gold(),
        )
        msg = await ch.send(embed=embed)
        try:
            await msg.add_reaction(SPECIAL_EMOJI)
        except Exception:
            return False

        pend = PendingSpecial(
            message_id=msg.id,
            channel_id=ch.id,
            guild_id=guild.id,
            expires_monotonic=self.bot.loop.time() + CLAIM_WINDOW_SECONDS,
            claimers=set(),
        )
        self._active[guild.id] = pend

        async def _end():
            await asyncio.sleep(CLAIM_WINDOW_SECONDS)
            await self._finalize(guild.id)

        self.bot.loop.create_task(_end())
        return True

    async def _finalize(self, guild_id: int):
        pend = self._active.get(guild_id)
        if not pend:
            return

        guild = self.bot.get_guild(guild_id)
        channel = guild.get_channel(pend.channel_id) if guild else None
        if not isinstance(channel, discord.TextChannel):
            self._active.pop(guild_id, None)
            return

        if not pend.claimers:
            embed = discord.Embed(
                title="🗑️ Supply spécial détruit",
                color=discord.Color.dark_grey(),
            )
            await channel.send(embed=embed)
            self._active.pop(guild_id, None)
            return

        winners = list(pend.claimers)[:CLAIM_LIMIT]
        recaps: List[str] = []

        for uid in winners:
            r = random.random()
            if r < 0.15:
                recaps.append(f"• <@{uid}> — **Piégé** (rien)")
            elif r < 0.30:
                heal_qty = random.randint(1, 3)
                for _ in range(heal_qty):
                    self._grant_inventory(guild_id, uid, self._pick_heal_item(), 1)
                recaps.append(f"• <@{uid}> — soins ×{heal_qty}")
            elif r < 0.50:
                amount = random.randint(100, 150)
                ok = self._grant_gold(guild_id, uid, amount)
                label = f"{amount} GoldValis" if ok else f"💰 ×{max(1, amount // 50)}"
                recaps.append(f"• <@{uid}> — {label}")
            elif r < 0.65:
                n = random.randint(1, 2)
                self._grant_tickets(guild_id, uid, n)
                recaps.append(f"• <@{uid}> — 🎟️ ×{n}")
            else:
                item = get_random_item(debug=False)
                qty = self._stack_qty_by_rarete(item)
                self._grant_inventory(guild_id, uid, item, qty)
                recaps.append(f"• <@{uid}> — {item}" + (f" ×{qty}" if qty > 1 else ""))

        if storage is not None:
            try:
                storage.save_data()
            except Exception:
                pass

        embed = discord.Embed(
            title="✅ Supply spécial récupéré",
            color=discord.Color.green(),
        )
        text = "\n".join(recaps) if recaps else "Personne."
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
        self._active.pop(guild_id, None)

    # ---------- Listeners ----------
    @commands.Cog.listener()
    async def on_ready(self):
        for g in self.bot.guilds:
            self._reset_window_state(g.id)

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        self._reset_window_state(guild.id)

    @commands.Cog.listener()
    async def on_message(self, msg: discord.Message):
        """Compte les messages uniquement si dans une fenêtre + salon éligible."""
        if msg.author.bot or not msg.guild:
            return
        perms = msg.channel.permissions_for(msg.guild.me)
        if not (perms.send_messages and perms.add_reactions):
            return

        in_win, _ = self._in_window()
        if not in_win:
            return

        st = self._get_state(msg.guild.id)
        if st.get("dropped_this_window"):
            return

        st["msg_count"] = int(st.get("msg_count", 0)) + 1
        st["last_chan_id"] = msg.channel.id  # ← dernier salon éligible

        if not st.get("qualified") and st["msg_count"] >= QUALIFY_MESSAGES:
            st["qualified"] = True
            st["qualified_since"] = self._now()
            st["minutes_since_qual"] = 0

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if str(payload.emoji) != SPECIAL_EMOJI:
            return
        if payload.user_id == getattr(self.bot.user, "id", None):
            return
        pend = self._active.get(payload.guild_id)
        if not pend or pend.message_id != payload.message_id:
            return
        if self.bot.loop.time() > pend.expires_monotonic:
            return
        if len(pend.claimers) >= CLAIM_LIMIT:
            return
        pend.claimers.add(payload.user_id)

    # ---------- Boucle minute ----------
    @tasks.loop(seconds=CHECK_PERIOD_SECONDS)
    async def _tick_loop(self):
        now = self._now()
        in_win, win = self._in_window(now)

        for guild in self.bot.guilds:
            gid = guild.id
            st = self._get_state(gid)

            # si drop actif, on touche à rien
            if gid in self._active:
                continue

            if not in_win or win is None:
                # hors fenêtre → reset total
                self._reset_window_state(gid)
                continue

            if st.get("dropped_this_window"):
                continue

            if not st.get("qualified"):
                continue

            st["minutes_since_qual"] = int(st.get("minutes_since_qual", 0)) + 1
            chance = min(MAX_CHANCE, BASE_CHANCE + INCREMENT_PER_MIN * st["minutes_since_qual"])

            # dernière minute : drop forcé
            if self._is_last_minute(now):
                ok = await self._spawn_drop(guild, st.get("last_chan_id"))
                if ok:
                    st["dropped_this_window"] = True
                continue

            # tirage aléatoire
            if random.random() < chance:
                ok = await self._spawn_drop(guild, st.get("last_chan_id"))
                if ok:
                    st["dropped_this_window"] = True

    @_tick_loop.before_loop
    async def _before_tick(self):
        await self.bot.wait_until_ready()

async def setup(bot: commands.Bot):
    await bot.add_cog(SupplySpecial(bot))

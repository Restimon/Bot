# cogs/daily_cog.py
from __future__ import annotations

import time
import random
from typing import Dict, Tuple, Optional, List

import discord
from discord import app_commands
from discord.ext import commands

# ─────────────────────────────────────────────
# Imports souples vers data.storage & utils
# ─────────────────────────────────────────────
_storage = None
_get_user_data = None
_save_data = None

try:
    from data import storage as _storage  # type: ignore
except Exception:
    _storage = None

try:
    from data.storage import get_user_data as _get_user_data  # type: ignore
except Exception:
    _get_user_data = None

try:
    from data.storage import save_data as _save_data  # type: ignore
except Exception:
    _save_data = None

# loot via utils (pondéré par rareté)
try:
    from utils import get_random_item
except Exception:
    def get_random_item(debug: bool = False):
        return random.choice(["🍀", "❄️", "🧪", "🩹", "💊"])

DAILY_COOLDOWN = 24 * 3600  # 24h
TICKET_EMOJI = "🎟️"

# coins de base
BASE_COINS_RANGE = (20, 40)
# bonus de streak : +3 par jour consécutif, plafonné à +25
STREAK_BONUS_PER_DAY = 3
STREAK_BONUS_MAX = 25


def _ensure_stats_root():
    if _storage is None:
        return
    if not hasattr(_storage, "stats") or not isinstance(_storage.stats, dict):
        _storage.stats = {}
    _storage.stats.setdefault("daily", {})


def _get_daily_entry(gid: int, uid: int) -> Dict:
    _ensure_stats_root()
    if _storage is None:
        if not hasattr(_get_daily_entry, "_mem"):
            _get_daily_entry._mem = {}
        mem = _get_daily_entry._mem  # type: ignore
        mem.setdefault(str(gid), {}).setdefault(str(uid), {"last": 0.0, "streak": 0})
        return mem[str(gid)][str(uid)]

    daily = _storage.stats["daily"]
    daily.setdefault(str(gid), {}).setdefault(str(uid), {"last": 0.0, "streak": 0})
    return daily[str(gid)][str(uid)]


def _set_daily_entry(gid: int, uid: int, last_ts: float, streak: int):
    entry = _get_daily_entry(gid, uid)
    entry["last"] = float(last_ts)
    entry["streak"] = int(streak)


def _cooldown_left(last_ts: float) -> float:
    if last_ts <= 0:
        return 0.0
    passed = time.time() - float(last_ts)
    left = DAILY_COOLDOWN - passed
    return max(0.0, left)


def _format_timedelta(seconds: float) -> str:
    seconds = int(seconds)
    h, r = divmod(seconds, 3600)
    m, s = divmod(r, 60)
    parts: List[str] = []
    if h: parts.append(f"{h}h")
    if m: parts.append(f"{m}m")
    if s or not parts: parts.append(f"{s}s")
    return " ".join(parts)


def _get_user_data_safe(gid: int, uid: int) -> Tuple[List, int, Optional[Dict]]:
    if callable(_get_user_data):
        try:
            inv, coins, perso = _get_user_data(str(gid), str(uid))  # type: ignore
            return inv or [], int(coins or 0), perso
        except Exception:
            pass
    return [], 0, None


def _save_safe():
    if callable(_save_data):
        try:
            _save_data()  # type: ignore
        except Exception:
            pass


class DailyCog(commands.Cog):
    """Récompenses quotidiennes : 2 objets + 1 ticket + coins (streak cap 25)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="daily", description="Récupère ta récompense quotidienne.")
    async def daily(self, interaction: discord.Interaction):
        if not interaction.guild:
            return await interaction.response.send_message("Commande serveur uniquement.")

        # pas éphémère → visible pour tout le monde
        await interaction.response.defer()

        gid = interaction.guild.id
        uid = interaction.user.id

        entry = _get_daily_entry(gid, uid)
        last = float(entry.get("last", 0.0))
        streak = int(entry.get("streak", 0))

        left = _cooldown_left(last)
        if left > 0:
            return await interaction.followup.send(
                f"⏳ Tu as déjà pris ton daily. Reviens dans **{_format_timedelta(left)}**."
            )

        now = time.time()
        if last > 0 and now - last <= (DAILY_COOLDOWN + 60):
            streak += 1
        else:
            streak = 1

        base_coins = random.randint(*BASE_COINS_RANGE)
        bonus = min(STREAK_BONUS_MAX, streak * STREAK_BONUS_PER_DAY)
        total_coins = base_coins + bonus

        inv, coins_before, _ = _get_user_data_safe(gid, uid)
        coins_after = coins_before + total_coins

        # 2 objets
        item1 = get_random_item()
        item2 = get_random_item()
        inv.append(item1)
        inv.append(item2)

        # ticket
        inv.append(TICKET_EMOJI)

        if _storage is not None:
            try:
                data_root = getattr(_storage, "data", None)
                if isinstance(data_root, dict):
                    data_root.setdefault(str(gid), {}).setdefault(str(uid), {})
                    data_root[str(gid)][str(uid)]["coins"] = coins_after
            except Exception:
                pass

        _set_daily_entry(gid, uid, now, streak)
        _save_safe()

        e = discord.Embed(
            title="🎁 Récompense quotidienne",
            color=discord.Color.green()
        )
        e.add_field(name="GotCoins", value=f"+{total_coins} (base {base_coins} + bonus {bonus})", inline=False)
        e.add_field(name="Objets reçus", value=f"{item1}  {item2}", inline=True)
        e.add_field(name="Ticket", value=TICKET_EMOJI, inline=True)
        e.add_field(name="Solde", value=f"{coins_before} → **{coins_after}**", inline=False)

        await interaction.followup.send(embed=e)


async def setup(bot: commands.Bot):
    await bot.add_cog(DailyCog(bot))

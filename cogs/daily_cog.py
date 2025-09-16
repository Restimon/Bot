# cogs/daily_cog.py
import asyncio
import random
import time
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands

import aiosqlite

from economy_db import add_balance, get_balance
from inventory_db import add_item

try:
    from utils import get_random_items as _get_random_items
except Exception:
    _get_random_items = None

DAILY_COOLDOWN_H = 24
STREAK_WINDOW_H = 48
TICKET_ITEM_NAME = "🎟️ Ticket"

# ⚠️ Adapte ce chemin pour utiliser la même DB que tes autres modules
try:
    # Essayons de la récupérer depuis economy_db si dispo
    from economy_db import DB_PATH as DB_PATH  # type: ignore
except Exception:
    DB_PATH = "gotvalis.sqlite3"

def _now() -> float:
    return time.time()

def _pick_items(n: int) -> list[str]:
    if _get_random_items:
        try:
            items = _get_random_items(n)
            if isinstance(items, list) and items:
                return items[:n]
        except Exception:
            pass
    FALLBACK_POOL = [
        "Mystery Box", "Potion de soin", "Poison", "Virus", "Bouclier", "Casque",
        "Évasion +", "Immunité", "Régénération", "Vol à la tire"
    ]
    return random.sample(FALLBACK_POOL, k=min(n, len(FALLBACK_POOL)))

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS dailies (
    user_id    INTEGER PRIMARY KEY,
    last_ts    REAL NOT NULL,
    streak     INTEGER NOT NULL
);
"""

class Daily(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._ready = False

    async def _ensure_table(self):
        if self._ready:
            return
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(CREATE_TABLE_SQL)
            await db.commit()
        self._ready = True

    async def _get_daily_row(self, uid: int):
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute("SELECT last_ts, streak FROM dailies WHERE user_id = ?", (uid,))
            row = await cur.fetchone()
            await cur.close()
        return row  # (last_ts, streak) or None

    async def _set_daily_row(self, uid: int, last_ts: float, streak: int):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO dailies(user_id, last_ts, streak) VALUES(?,?,?) "
                "ON CONFLICT(user_id) DO UPDATE SET last_ts=excluded.last_ts, streak=excluded.streak",
                (uid, last_ts, streak)
            )
            await db.commit()

    @app_commands.command(name="daily", description="Récupère ta récompense quotidienne (persistant SQL).")
    async def daily(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False, thinking=False)
        await self._ensure_table()

        uid = interaction.user.id
        now = _now()

        row = await self._get_daily_row(uid)
        last_ts = row[0] if row else None
        prev_streak = row[1] if row else 0

        if last_ts is not None:
            elapsed_h = (now - last_ts) / 3600
            if elapsed_h < DAILY_COOLDOWN_H:
                remaining = DAILY_COOLDOWN_H - elapsed_h
                hours = int(remaining)
                minutes = int((remaining - hours) * 60)
                embed = discord.Embed(
                    title="⏳ Daily non disponible",
                    description=f"Reviens dans **{hours}h {minutes}m**.",
                    color=discord.Color.orange()
                )
                await interaction.followup.send(embed=embed)
                return

        # streak update dans fenêtre 48h
        if last_ts is None:
            streak = 1
        else:
            since_last_h = (now - last_ts) / 3600
            if since_last_h <= STREAK_WINDOW_H:
                streak = max(1, prev_streak) + 1
            else:
                streak = 1

        # Récompenses
        base_coins = 20
        streak_bonus = min(streak, 25)
        coins_gain = base_coins + streak_bonus
        items = _pick_items(2)

        # DB writes
        await add_balance(uid, coins_gain, reason="daily")
        coins_after = await get_balance(uid)
        await add_item(uid, TICKET_ITEM_NAME, 1)
        for it in items:
            await add_item(uid, it, 1)

        # Persist daily row
        await self._set_daily_row(uid, now, streak)

        # Embed
        embed = discord.Embed(
            title="🎁 Récompense quotidienne",
            description=f"Streak : **{streak}** (bonus +{streak_bonus})",
            color=discord.Color.green()
        )
        embed.add_field(name="GotCoins gagnés", value=f"+{coins_gain}", inline=True)
        embed.add_field(name="Ticket", value=f"+1 {TICKET_ITEM_NAME}", inline=True)
        embed.add_field(name="Objets", value=" + ".join([f"+1 {name}" for name in items]) or "—", inline=False)
        embed.add_field(name="Solde", value=f"{coins_after}", inline=True)

        if last_ts:
            dt = datetime.fromtimestamp(last_ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            embed.set_footer(text=f"Dernier daily: {dt}")
        await interaction.followup.send(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(Daily(bot))

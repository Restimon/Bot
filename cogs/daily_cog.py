# cogs/daily_cog.py
from __future__ import annotations

import asyncio
import time
import random
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

import aiosqlite

# ─────────────────────────────────────────────────────────────
# Réglages
# ─────────────────────────────────────────────────────────────
DB_PATH = "gotvalis.sqlite3"

DAILY_COOLDOWN = 24 * 3600  # 24h
# ⚠️ adapte ici les objets requis (2 items) et l’emoji ticket
REQUIRED_ITEMS = ["🍀", "❄️"]  # 2 objets obligatoires (1 de chaque)
TICKET_EMOJI = "🎟️"          # ticket obligatoire (1)

# Récompense
BASE_MIN, BASE_MAX = 45, 75        # plage de base en GoldValis
STREAK_BONUS_PER_DAY = 5            # +5 par jour consécutif
STREAK_BONUS_CAP = 50               # bonus max
STREAK_RESET_GRACE = 48 * 3600      # streak tolère un “retard” < 48h

# ─────────────────────────────────────────────────────────────
# Imports DB
# ─────────────────────────────────────────────────────────────
from economy_db import add_balance  # ajoute des GoldValis
from inventory_db import get_item_qty, remove_item, add_item  # inventaire par emoji

# ─────────────────────────────────────────────────────────────
# Init table pour /daily
# ─────────────────────────────────────────────────────────────
SCHEMA = """
CREATE TABLE IF NOT EXISTS daily_claims(
  user_id TEXT PRIMARY KEY,
  last_claim_ts INTEGER NOT NULL DEFAULT 0,
  streak INTEGER NOT NULL DEFAULT 0
);
"""

async def init_daily_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(SCHEMA)
        await db.commit()

async def get_daily_state(user_id: int) -> tuple[int, int]:
    """Retourne (last_ts, streak)."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT last_claim_ts, streak FROM daily_claims WHERE user_id=?",
            (str(user_id),),
        ) as cur:
            row = await cur.fetchone()
    if not row:
        return 0, 0
    return int(row[0] or 0), int(row[1] or 0)

async def set_daily_state(user_id: int, last_ts: int, streak: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO daily_claims(user_id, last_claim_ts, streak)
            VALUES(?,?,?)
            ON CONFLICT(user_id) DO UPDATE SET
              last_claim_ts=excluded.last_claim_ts,
              streak=excluded.streak
            """,
            (str(user_id), int(last_ts), int(streak)),
        )
        await db.commit()

# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────
def _fmt_duration(seconds: int) -> str:
    s = max(0, int(seconds))
    h, r = divmod(s, 3600)
    m, s = divmod(r, 60)
    parts = []
    if h: parts.append(f"{h}h")
    if m: parts.append(f"{m}m")
    if s or not parts: parts.append(f"{s}s")
    return " ".join(parts)

async def _check_requirements(user_id: int) -> tuple[bool, str]:
    """Vérifie présence des 2 objets + 1 ticket. Retourne (ok, err_msg)."""
    # 2 objets obligatoires
    for em in REQUIRED_ITEMS:
        if await get_item_qty(user_id, em) < 1:
            return False, f"Il te manque **{em}**."
    # 1 ticket
    if await get_item_qty(user_id, TICKET_EMOJI) < 1:
        return False, f"Il te manque un ticket **{TICKET_EMOJI}**."
    return True, ""

async def _consume_requirements(user_id: int) -> None:
    """Consomme 1x chaque objet requis + 1 ticket (silencieux si déjà vérifié)."""
    for em in REQUIRED_ITEMS:
        await remove_item(user_id, em, 1)
    await remove_item(user_id, TICKET_EMOJI, 1)

def _compute_reward(streak: int) -> int:
    base = random.randint(BASE_MIN, BASE_MAX)
    bonus = min(STREAK_BONUS_CAP, streak * STREAK_BONUS_PER_DAY)
    return max(0, base + bonus)

# ─────────────────────────────────────────────────────────────
# Cog
# ─────────────────────────────────────────────────────────────
class Daily(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="daily", description="Récupère ta récompense quotidienne (consomme 2 objets + 1 ticket).")
    async def daily(self, inter: discord.Interaction):
        await inter.response.defer(thinking=True, ephemeral=True)
        uid = inter.user.id
        now = int(time.time())

        # Cooldown & streak
        last_ts, streak = await get_daily_state(uid)
        if last_ts and now - last_ts < DAILY_COOLDOWN:
            remain = DAILY_COOLDOWN - (now - last_ts)
            embed = discord.Embed(
                title="⏳ Daily déjà récupéré",
                description=f"Reviens dans **{_fmt_duration(remain)}**.",
                color=discord.Color.orange(),
            )
            # petit rappel des prérequis
            reqs = " + ".join(REQUIRED_ITEMS) + f" + {TICKET_EMOJI}"
            embed.add_field(name="Pré-requis", value=reqs, inline=False)
            return await inter.followup.send(embed=embed, ephemeral=True)

        # Requirements
        ok, why = await _check_requirements(uid)
        if not ok:
            reqs = " + ".join(REQUIRED_ITEMS) + f" + {TICKET_EMOJI}"
            embed = discord.Embed(
                title="❌ Impossible de valider le daily",
                description=f"{why}\nPré-requis: **{reqs}**",
                color=discord.Color.red(),
            )
            return await inter.followup.send(embed=embed, ephemeral=True)

        # Streak logic (48h de tolérance)
        if last_ts == 0 or (now - last_ts) > STREAK_RESET_GRACE:
            streak = 1
        else:
            streak = streak + 1

        # Consomme les items
        await _consume_requirements(uid)

        # Récompense
        reward = _compute_reward(streak)
        new_balance = await add_balance(uid, reward, reason="daily")

        # Sauvegarde état
        await set_daily_state(uid, now, streak)

        # Embed de résultat
        reqs_str = ", ".join(REQUIRED_ITEMS + [TICKET_EMOJI])
        bonus_now = min(STREAK_BONUS_CAP, streak * STREAK_BONUS_PER_DAY)
        next_in = _fmt_duration(DAILY_COOLDOWN)

        embed = discord.Embed(
            title="🎁 Daily récupéré",
            color=discord.Color.green(),
        )
        embed.add_field(name="Récompense", value=f"**+{reward}** GoldValis (solde: **{new_balance}**)", inline=False)
        embed.add_field(name="Streak", value=f"Jour **{streak}** (bonus actuel: **+{bonus_now}**)", inline=True)
        embed.add_field(name="Consommé", value=reqs_str, inline=True)
        embed.set_footer(text=f"Prochain daily disponible dans {next_in}.")
        await inter.followup.send(embed=embed, ephemeral=True)

# ─────────────────────────────────────────────────────────────
# Setup
# ─────────────────────────────────────────────────────────────
async def setup(bot: commands.Bot):
    await init_daily_db()
    await bot.add_cog(Daily(bot))

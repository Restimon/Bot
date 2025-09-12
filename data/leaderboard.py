# leaderboard.py
from __future__ import annotations

import aiosqlite
import discord
from typing import List, Tuple, Optional

from economie import get_balance
from stats_db import get_hp

DB_PATH = "gotvalis.sqlite3"

SCHEMA = """
CREATE TABLE IF NOT EXISTS leaderboard_settings(
  guild_id   TEXT PRIMARY KEY,
  channel_id TEXT NOT NULL,
  message_id TEXT NOT NULL
);
"""

async def init_leaderboard_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(SCHEMA)
        await db.commit()

# ─────────────────────────────────────────────────────────────────────────────
# DB helpers
# ─────────────────────────────────────────────────────────────────────────────

async def set_leaderboard_message(guild_id: int, channel_id: int, message_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO leaderboard_settings(guild_id, channel_id, message_id)
            VALUES(?,?,?)
            ON CONFLICT(guild_id) DO UPDATE SET channel_id=excluded.channel_id, message_id=excluded.message_id
            """,
            (str(guild_id), str(channel_id), str(message_id)),
        )
        await db.commit()

async def get_leaderboard_message(guild_id: int) -> Optional[Tuple[int, int]]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT channel_id, message_id FROM leaderboard_settings WHERE guild_id=?",
            (str(guild_id),),
        ) as cur:
            row = await cur.fetchone()
    if not row:
        return None
    return (int(row[0]), int(row[1]))

async def clear_leaderboard_message(guild_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM leaderboard_settings WHERE guild_id=?", (str(guild_id),))
        await db.commit()

# ─────────────────────────────────────────────────────────────────────────────
# Rendu
# ─────────────────────────────────────────────────────────────────────────────

def _rank_emoji(idx: int) -> str:
    return {1: "🥇", 2: "🥈", 3: "🥉"}.get(idx, f"{idx}.")

async def _collect_ranking(guild: discord.Guild, limit: int = 10) -> List[Tuple[discord.Member, int, int, int]]:
    """Retourne [(member, balance, hp, hp_max)] trié par balance desc."""
    rows: List[Tuple[discord.Member, int, int, int]] = []
    for m in guild.members:
        if m.bot:
            continue
        bal = await get_balance(m.id)
        hp, hp_max = await get_hp(m.id)
        rows.append((m, bal, hp, hp_max))
    rows.sort(key=lambda r: (-r[1], r[0].id))
    return rows[:limit]

async def build_embed(guild: discord.Guild) -> discord.Embed:
    top = await _collect_ranking(guild, limit=10)

    emb = discord.Embed(
        title="🏆 CLASSEMENT GOTVALIS — ÉDITION SPÉCIALE 🏆",
        color=discord.Color.gold(),
        description="",
    )
    lines: List[str] = []
    for i, (m, bal, hp, hp_max) in enumerate(top, start=1):
        rank = _rank_emoji(i)
        lines.append(f"{rank} {m.mention} → 💰 **{bal}** GotCoins | ❤️ **{hp}** PV")
    if not lines:
        lines = ["*(Aucun joueur pour le moment)*"]

    emb.description = "\n".join(lines)
    emb.set_footer(text="💡 Les GotCoins représentent votre richesse accumulée.")
    return emb

# ─────────────────────────────────────────────────────────────────────────────
# Update util
# ─────────────────────────────────────────────────────────────────────────────

async def ensure_and_update_message(guild: discord.Guild) -> bool:
    """
    Met à jour l'embed existant. Retourne True si le message a été mis à jour.
    """
    pair = await get_leaderboard_message(guild.id)
    if not pair:
        return False
    ch_id, msg_id = pair
    channel = guild.get_channel(ch_id)
    if not isinstance(channel, (discord.TextChannel, discord.Thread, discord.VoiceChannel)):
        return False
    try:
        msg = await channel.fetch_message(msg_id)
    except Exception:
        return False

    emb = await build_embed(guild)
    try:
        await msg.edit(embed=emb)
        return True
    except Exception:
        return False

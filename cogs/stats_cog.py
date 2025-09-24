# cogs/stats_cog.py
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, List, Tuple, Any

import aiosqlite
import discord
from discord import app_commands
from discord.ext import commands

# ===== DB path (même DB que l’économie) ========================================
try:
    from economy_db import DB_PATH as DB_PATH  # type: ignore
except Exception:
    DB_PATH = "gotvalis.sqlite3"

# ===== Leaderboard mémoire (même source que le /fight & /info) =================
_storage = None
try:
    from data import storage as _storage  # type: ignore
except Exception:
    _storage = None

def _lb_get_leaderboard(gid: int) -> Dict[str, Dict[str, int]]:
    if _storage is not None:
        if not hasattr(_storage, "leaderboard") or not isinstance(getattr(_storage, "leaderboard"), dict):
            setattr(_storage, "leaderboard", {})
        lb = getattr(_storage, "leaderboard")
        lb.setdefault(str(gid), {})
        return lb[str(gid)]
    if not hasattr(_lb_get_leaderboard, "_mem"):
        _lb_get_leaderboard._mem: Dict[str, Dict[str, Dict[str, int]]] = {}
    mem = _lb_get_leaderboard._mem  # type: ignore
    mem.setdefault(str(gid), {})
    return mem[str(gid)]

def _lb_rank_sorted(gid: int) -> List[Tuple[int, Dict[str, int]]]:
    lb = _lb_get_leaderboard(gid)
    items: List[Tuple[int, Dict[str, int]]] = []
    for uid_str, stats in lb.items():
        try:
            uid = int(uid_str)
        except Exception:
            continue
        if not isinstance(stats, dict):
            continue
        pts = int(stats.get("points", 0) or 0)
        k = int(stats.get("kills", 0) or 0)
        d = int(stats.get("deaths", 0) or 0)
        items.append((uid, {"points": pts, "kills": k, "deaths": d}))
    items.sort(key=lambda x: (-x[1]["points"], -x[1]["kills"], x[1]["deaths"], x[0]))
    return items

def _lb_find_rank(sorted_list: List[Tuple[int, Dict[str, int]]], uid: int) -> Optional[int]:
    for i, (u, _) in enumerate(sorted_list, start=1):
        if u == uid:
            return i
    return None

# ===== Tables locales (messages & vocal) =======================================
CREATE_MSG_SQL = """
CREATE TABLE IF NOT EXISTS message_stats (
  user_id   INTEGER NOT NULL,
  guild_id  INTEGER NOT NULL,
  day       TEXT    NOT NULL,  -- YYYY-MM-DD (UTC)
  count     INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (user_id, guild_id, day)
);
"""
CREATE_VOICE_SQL = """
CREATE TABLE IF NOT EXISTS voice_stats (
  user_id   INTEGER NOT NULL,
  guild_id  INTEGER NOT NULL,
  day       TEXT    NOT NULL,  -- YYYY-MM-DD (UTC)
  seconds   INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (user_id, guild_id, day)
);
"""

async def _ensure_tables():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(CREATE_MSG_SQL)
        await db.execute(CREATE_VOICE_SQL)
        await db.commit()

def _utc_day(ts: float | None = None) -> str:
    dt = datetime.utcfromtimestamp(ts or time.time()).replace(tzinfo=timezone.utc)
    return dt.strftime("%Y-%m-%d")

def _fmt_duration_short(seconds: int) -> str:
    s = max(0, int(seconds))
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    d, h = divmod(h, 24)
    parts: List[str] = []
    if d: parts.append(f"{d} j")
    if h: parts.append(f"{h} h")
    if m: parts.append(f"{m} min")
    if not parts:
        parts.append(f"{s} s")
    return " ".join(parts)

# ===== Totaux vie depuis stats_db (fallback heuristique si absent) =============
async def _totals_lifetime(uid: int) -> Dict[str, int]:
    # Preferred: stats_db.players_stats
    try:
        from stats_db import get_profile as stats_get_profile  # type: ignore
        prof = await stats_get_profile(uid)
        return {
            "dmg": int(prof.get("dmg_dealt", 0)),
            "heal": int(prof.get("heal_done", 0)),
            "kills": int(prof.get("kills", 0)),
            "deaths": int(prof.get("deaths", 0)),
        }
    except Exception:
        pass

    # Fallback best-effort (scan schéma)
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [r[0] for r in await cur.fetchall()]
            await cur.close()

            out = {"dmg": 0, "heal": 0, "kills": 0, "deaths": 0}

            async def _sum(db: aiosqlite.Connection, table: str, val: str, who: str) -> Optional[int]:
                try:
                    c = await db.execute(f"SELECT COALESCE(SUM({val}),0) FROM {table} WHERE {who}=?", (uid,))
                    v = await c.fetchone()
                    await c.close()
                    return int(v[0]) if v and v[0] is not None else 0
                except Exception:
                    return None

            async def _count(db: aiosqlite.Connection, table: str, who: str) -> Optional[int]:
                try:
                    c = await db.execute(f"SELECT COUNT(1) FROM {table} WHERE {who}=?", (uid,))
                    v = await c.fetchone()
                    await c.close()
                    return int(v[0]) if v and v[0] is not None else 0
                except Exception:
                    return None

            preferred = [
                ("damage_log", "damage", "attacker_id", "dmg"),
                ("heal_log",   "heal",   "healer_id",   "heal"),
            ]
            for t, val, who, key in preferred:
                if t in tables:
                    v = await _sum(db, t, val, who)
                    if v is not None:
                        out[key] = max(out[key], v)

            if "kills" in tables:
                v = await _count(db, "kills", "killer_id")
                if v is not None:
                    out["kills"] = max(out["kills"], v)
            if "deaths" in tables:
                v = await _count(db, "deaths", "victim_id")
                if v is not None:
                    out["deaths"] = max(out["deaths"], v)

            # Large scan au cas où
            for t in tables:
                try:
                    c = await db.execute(f"PRAGMA table_info({t})")
                    cols = [r[1].lower() for r in await c.fetchall()]
                    await c.close()
                except Exception:
                    continue
                # dmg
                for who in ("attacker_id", "user_id", "author_id", "player_id"):
                    if who in cols:
                        for val in ("damage", "dmg"):
                            if val in cols:
                                v = await _sum(db, t, val, who)
                                if v is not None:
                                    out["dmg"] = max(out["dmg"], v)
                # heal
                for who in ("healer_id", "user_id", "author_id", "player_id"):
                    if who in cols:
                        for val in ("heal", "healed", "healing"):
                            if val in cols:
                                v = await _sum(db, t, val, who)
                                if v is not None:
                                    out["heal"] = max(out["heal"], v)
                # kills / deaths
                if "killer_id" in cols:
                    v = await _count(db, t, "killer_id")
                    if v is not None:
                        out["kills"] = max(out["kills"], v)
                if "victim_id" in cols:
                    v = await _count(db, t, "victim_id")
                    if v is not None:
                        out["deaths"] = max(out["deaths"], v)

            return out
    except Exception:
        return {"dmg": 0, "heal": 0, "kills": 0, "deaths": 0}

# ==============================================================================

VC_TICK_SECONDS = 60
VC_MIN_ACTIVE = 2  # il faut au moins 2 actifs dans un salon pour compter

class StatsCog(commands.Cog):
    """Stats: /stats + journal messages/vocal (7j) avec tick vocal en temps réel."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._voice_task: Optional[asyncio.Task] = None
        asyncio.create_task(_ensure_tables())

    async def cog_load(self):
        self._voice_task = asyncio.create_task(self._voice_loop())

    async def cog_unload(self):
        if self._voice_task:
            self._voice_task.cancel()

    # ---------- Event: messages (stats 7j) ----------
    @commands.Cog.listener()
    async def on_message(self, msg: discord.Message):
        if msg.author.bot or not msg.guild:
            return
        try:
            await _ensure_tables()
            day = _utc_day()
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute(
                    "INSERT INTO message_stats(user_id, guild_id, day, count) VALUES(?,?,?,1) "
                    "ON CONFLICT(user_id, guild_id, day) DO UPDATE SET count = count + 1",
                    (msg.author.id, msg.guild.id, day),
                )
                await db.commit()
        except Exception:
            pass

    # ---------- Boucle vocale (stats 7j en temps réel) ----------
    async def _voice_loop(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            try:
                await self._voice_tick()
            except Exception:
                pass
            await asyncio.sleep(VC_TICK_SECONDS)

    async def _voice_tick(self):
        await _ensure_tables()
        now_day = _utc_day()
        for guild in self.bot.guilds:
            if not guild.members:
                continue

            afk_id = guild.afk_channel.id if guild.afk_channel else None

            # Regrouper par canal
            channels: Dict[int, List[discord.Member]] = {}
            for m in guild.members:
                vs = m.voice
                if not vs or not vs.channel:
                    continue
                channels.setdefault(vs.channel.id, []).append(m)

            for cid, members in channels.items():
                # filtrer les ACTIFS
                active: List[discord.Member] = []
                for member in members:
                    vs = member.voice
                    if not vs or not vs.channel:
                        continue
                    if afk_id and vs.channel.id == afk_id:
                        continue
                    if member.bot:
                        continue
                    if isinstance(vs.channel, discord.StageChannel) and vs.suppress:
                        continue
                    if vs.self_deaf or vs.deaf:
                        continue
                    if vs.self_mute:
                        continue
                    active.append(member)

                if len(active) < VC_MIN_ACTIVE:
                    continue

                # Crédit 60 sec pour chaque ACTIF
                async with aiosqlite.connect(DB_PATH) as db:
                    for m in active:
                        await db.execute(
                            "INSERT INTO voice_stats(user_id, guild_id, day, seconds) VALUES(?,?,?,?) "
                            "ON CONFLICT(user_id, guild_id, day) DO UPDATE SET seconds = seconds + excluded.seconds",
                            (m.id, guild.id, now_day, VC_TICK_SECONDS),
                        )
                    await db.commit()

    # ---------- Helpers lecture 7j ----------
    async def _sum_7d_messages(self, uid: int, gid: int) -> int:
        await _ensure_tables()
        since = (datetime.utcnow() - timedelta(days=7)).strftime("%Y-%m-%d")
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute(
                "SELECT COALESCE(SUM(count),0) FROM message_stats WHERE user_id=? AND guild_id=? AND day>=?",
                (uid, gid, since),
            )
            v = await cur.fetchone()
            await cur.close()
        return int(v[0]) if v and v[0] is not None else 0

    async def _sum_7d_voice(self, uid: int, gid: int) -> int:
        await _ensure_tables()
        since = (datetime.utcnow() - timedelta(days=7)).strftime("%Y-%m-%d")
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute(
                "SELECT COALESCE(SUM(seconds),0) FROM voice_stats WHERE user_id=? AND guild_id=? AND day>=?",
                (uid, gid, since),
            )
            v = await cur.fetchone()
            await cur.close()
        return int(v[0]) if v and v[0] is not None else 0

    # ---------- /stats ----------
    @app_commands.command(name="stats", description="Stats des 7 derniers jours + totaux (vie) et rang Points.")
    @app_commands.describe(membre="Choisir un membre (par défaut: toi)")
    async def stats(self, inter: discord.Interaction, membre: Optional[discord.Member] = None):
        if not inter.guild:
            return await inter.response.send_message("❌ À utiliser dans un serveur.", ephemeral=True)
        await inter.response.defer(thinking=False)

        target: discord.Member = membre or inter.user  # type: ignore
        uid, gid = target.id, inter.guild.id

        msg7 = await self._sum_7d_messages(uid, gid)
        voice7 = await self._sum_7d_voice(uid, gid)

        rows = _lb_rank_sorted(gid)
        pos = _lb_find_rank(rows, uid)
        if pos:
            stats_row = next((s for (u, s) in rows if u == uid), {"points": 0, "kills": 0, "deaths": 0})
            rank_line = f"#{pos} — {stats_row.get('points',0)} pts • 🗡 {stats_row.get('kills',0)} / 💀 {stats_row.get('deaths',0)}"
        else:
            rank_line = "Non classé"

        joined = None
        if isinstance(target, discord.Member) and target.joined_at:
            try:
                joined = target.joined_at.astimezone(timezone.utc).strftime("%d %B %Y • %H:%M UTC")
            except Exception:
                joined = str(target.joined_at)

        totals = await _totals_lifetime(uid)
        dmg_total = totals["dmg"]
        heal_total = totals["heal"]
        kills_total = totals["kills"]
        deaths_total = totals["deaths"]

        e = discord.Embed(
            title=f"📊 Stats — {target.display_name if hasattr(target,'display_name') else target.name}",
            color=discord.Color.blurple(),
        )
        if target.display_avatar:
            e.set_thumbnail(url=target.display_avatar.url)

        e.add_field(name="📅 Sur le serveur depuis", value=joined or "—", inline=False)
        e.add_field(name="💬 Messages (7j)", value=str(msg7), inline=True)
        e.add_field(name="🎙️ Vocal (7j)", value=_fmt_duration_short(voice7), inline=True)
        e.add_field(name="🏅 Classement (Points)", value=rank_line, inline=False)
        e.add_field(name="🗡️ Dégâts totaux (vie)", value=str(dmg_total), inline=True)
        e.add_field(name="💚 Soins totaux (vie)", value=str(heal_total), inline=True)
        e.add_field(name="⚔️ Kills / 💀 Morts (vie)", value=f"{kills_total} / {deaths_total}", inline=True)

        await inter.followup.send(embed=e)

async def setup(bot: commands.Bot):
    await bot.add_cog(StatsCog(bot))

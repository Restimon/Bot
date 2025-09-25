from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, List, Tuple, Any

import aiosqlite
import discord
from discord import app_commands
from discord.ext import commands

# ===== DB path (réutilise economy_db) =========================================
try:
    from economy_db import DB_PATH as DB_PATH  # type: ignore
except Exception:
    DB_PATH = "gotvalis.sqlite3"

# ===== Leaderboard mémoire (comme avant) ======================================
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

# ===== Tables locales (messages / voice) ======================================
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

# ===== Totaux “vie” (inchangés) ===============================================
async def _sum_column_where(db: aiosqlite.Connection, table: str, col_sum: str, where_col: str, uid: int) -> Optional[int]:
    try:
        cur = await db.execute(f"SELECT COALESCE(SUM({col_sum}),0) FROM {table} WHERE {where_col} = ?", (uid,))
        v = await cur.fetchone()
        await cur.close()
        return int(v[0]) if v and v[0] is not None else 0
    except Exception:
        return None

async def _count_where(db: aiosqlite.Connection, table: str, where_col: str, uid: int) -> Optional[int]:
    try:
        cur = await db.execute(f"SELECT COUNT(1) FROM {table} WHERE {where_col} = ?", (uid,))
        v = await cur.fetchone()
        await cur.close()
        return int(v[0]) if v and v[0] is not None else 0
    except Exception:
        return None

async def _totals_from_schema(uid: int) -> Dict[str, int]:
    out = {"dmg": 0, "heal": 0, "kills": 0, "deaths": 0}
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [r[0] for r in await cur.fetchall()]
            await cur.close()

            preferred = [
                ("damage_log", "attacker_id", "damage"),
                ("heal_log",   "healer_id",   "heal"),
                ("kills",      "killer_id",   None),
                ("deaths",     "victim_id",   None),
            ]
            for t, who_col, val_col in preferred:
                if t in tables:
                    if val_col:
                        v = await _sum_column_where(db, t, val_col, who_col, uid)
                        if v is not None:
                            if "damage" in val_col: out["dmg"]   = max(out["dmg"], v)
                            if "heal"   in val_col: out["heal"]  = max(out["heal"], v)
                    else:
                        c = await _count_where(db, t, who_col, uid)
                        if c is not None:
                            if "killer" in who_col: out["kills"]  = max(out["kills"], c)
                            if "victim" in who_col: out["deaths"] = max(out["deaths"], c)

            for t in tables:
                try:
                    cur = await db.execute(f"PRAGMA table_info({t})")
                    cols = [r[1].lower() for r in await cur.fetchall()]
                    await cur.close()
                except Exception:
                    continue

                for who in ("attacker_id", "user_id", "author_id", "player_id"):
                    if who in cols:
                        for val in ("damage", "dmg"):
                            if val in cols:
                                v = await _sum_column_where(db, t, val, who, uid)
                                if v is not None:
                                    out["dmg"] = max(out["dmg"], v, out["dmg"])
                for who in ("healer_id", "user_id", "author_id", "player_id"):
                    if who in cols:
                        for val in ("heal", "healed", "healing"):
                            if val in cols:
                                v = await _sum_column_where(db, t, val, who, uid)
                                if v is not None:
                                    out["heal"] = max(out["heal"], v, out["heal"])
                for who in ("killer_id", "victim_id"):
                    if who in cols:
                        c = await _count_where(db, t, who, uid)
                        if c is not None:
                            if who == "killer_id": out["kills"]  = max(out["kills"], c)
                            else:                   out["deaths"] = max(out["deaths"], c)
    except Exception:
        pass
    return out

# ==============================================================================
class StatsCog(commands.Cog):
    """
    - Capte messages & voix et écrit dans message_stats / voice_stats
    - Expose schedule_stats_touch() pour que d'autres cogs “touchent” toutes les stats
      (flush vocal + LB) après leurs actions (/fight, /heal, etc.)
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._voice_joins: Dict[Tuple[int, int], float] = {}   # (gid, uid) -> start_ts
        self._lock = asyncio.Lock()
        asyncio.create_task(_ensure_tables())
        # flush périodique (pour voir “Vocal (7j)” avancer même sans quitter)
        self._voice_flush_task = asyncio.create_task(self._voice_flush_loop())

    # ---------- Écouteurs de base ----------
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
            # touche tout (flush + LB)
            await self._touch_everything(msg.guild.id, [msg.author.id])
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if member.bot or not member.guild:
            return
        gid = member.guild.id
        uid = member.id
        key = (gid, uid)
        now = time.time()

        # entrée / déplacement -> (re)start
        if after.channel and not before.channel:
            async with self._lock:
                self._voice_joins[key] = now

        # sortie -> flush total
        if before.channel and not after.channel:
            start = None
            async with self._lock:
                start = self._voice_joins.pop(key, None)
            if start:
                await self._add_voice_seconds(uid, gid, int(now - start))

        # quoi qu'il arrive, on “touche” (ça flush si besoin + LB)
        await self._touch_everything(gid, [uid])

    # ---------- API interne ----------
    async def _add_voice_seconds(self, uid: int, gid: int, seconds: int):
        try:
            await _ensure_tables()
            day = _utc_day()
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute(
                    "INSERT INTO voice_stats(user_id, guild_id, day, seconds) VALUES(?,?,?,?) "
                    "ON CONFLICT(user_id, guild_id, day) DO UPDATE SET seconds = seconds + excluded.seconds",
                    (uid, gid, day, int(max(0, seconds))),
                )
                await db.commit()
        except Exception:
            pass

    async def _voice_flush_loop(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            try:
                now = time.time()
                # flush par pas de 60 s pour chaque session en cours
                async with self._lock:
                    for (gid, uid), start_ts in list(self._voice_joins.items()):
                        while now - start_ts >= 60:
                            await self._add_voice_seconds(uid, gid, 60)
                            start_ts += 60
                            self._voice_joins[(gid, uid)] = start_ts
                            # touche pendant qu'on flush
                            await self._touch_everything(gid, [uid], skip_flush=True)
            except Exception:
                pass
            await asyncio.sleep(60)

    async def _touch_everything(self, guild_id: int, user_ids: List[int], *, skip_flush: bool = False):
        """
        - Flush vocal instantané si l’utilisateur est en cours de session (sauf skip_flush)
        - Déclenche le refresh du leaderboard live
        """
        now = time.time()
        if not skip_flush:
            async with self._lock:
                for uid in user_ids:
                    key = (guild_id, uid)
                    start = self._voice_joins.get(key)
                    if start and now - start >= 60:
                        # flush les minutes entières accumulées
                        while now - start >= 60:
                            await self._add_voice_seconds(uid, guild_id, 60)
                            start += 60
                        self._voice_joins[key] = start
        # ping leaderboard_live (s'il est chargé)
        try:
            from cogs.leaderboard_live import schedule_lb_update
            schedule_lb_update(self.bot, int(guild_id), "stats_touch")
        except Exception:
            pass

    # ---------- helpers lecture 7j ----------
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
    @app_commands.command(name="stats", description="Stats des 7 derniers jours + totaux (dégâts/soins/kills/morts).")
    @app_commands.describe(membre="Choisir un membre (par défaut: toi)")
    async def stats(self, inter: discord.Interaction, membre: Optional[discord.Member] = None):
        if not inter.guild:
            return await inter.response.send_message("❌ À utiliser dans un serveur.", ephemeral=True)
        await inter.response.defer(thinking=False)

        target: discord.Member = membre or inter.user  # type: ignore
        uid = target.id
        gid = inter.guild.id

        # petit flush opportuniste avant lecture
        await self._touch_everything(gid, [uid])

        msg7 = await self._sum_7d_messages(uid, gid)
        voice7 = await self._sum_7d_voice(uid, gid)

        rows = _lb_rank_sorted(gid)
        pos = _lb_find_rank(rows, uid)
        rank_line = "Non classé"
        if pos:
            stats = next((s for (u, s) in rows if u == uid), {"points": 0, "kills": 0, "deaths": 0})
            rank_line = f"#{pos} — {stats.get('points',0)} pts • 🗡 {stats.get('kills',0)} / 💀 {stats.get('deaths',0)}"

        joined = None
        if isinstance(target, discord.Member) and target.joined_at:
            try:
                joined = target.joined_at.astimezone(timezone.utc).strftime("%d %B %Y • %H:%M UTC")
            except Exception:
                joined = str(target.joined_at)

        totals = await _totals_from_schema(uid)
        dmg_total = int(totals.get("dmg", 0))
        heal_total = int(totals.get("heal", 0))
        kills_total = int(totals.get("kills", 0))
        deaths_total = int(totals.get("deaths", 0))

        e = discord.Embed(
            title=f"📊 Stats — {target.display_name if hasattr(target,'display_name') else target.name}",
            color=discord.Color.purple(),
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

# ===== Helper importable par les autres cogs (combat, heal, etc.) =============

def schedule_stats_touch(bot: commands.Bot, guild_id: int, *user_ids: int) -> None:
    """
    À appeler depuis un autre cog après une action (ex: /fight, /heal, /use…)
    pour flusher le vocal en cours + déclencher la MAJ LB.
    """
    try:
        cog: StatsCog = bot.get_cog("StatsCog")  # type: ignore
        if cog:
            asyncio.create_task(cog._touch_everything(int(guild_id), list(map(int, user_ids))))
    except Exception:
        pass

async def setup(bot: commands.Bot):
    await bot.add_cog(StatsCog(bot))

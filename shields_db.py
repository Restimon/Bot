# shields_db.py
import aiosqlite
from typing import Optional

try:
    from economy_db import DB_PATH as DB_PATH  # même DB que le reste
except Exception:
    DB_PATH = "gotvalis.sqlite3"

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS shields (
    user_id    INTEGER PRIMARY KEY,
    value      INTEGER NOT NULL DEFAULT 0,
    max_value  INTEGER NOT NULL DEFAULT 50
);
"""

async def init_shields_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(CREATE_SQL)
        await db.commit()

async def _ensure_row(db, uid: int):
    await db.execute(
        "INSERT INTO shields(user_id, value, max_value) "
        "SELECT ?, 0, 50 WHERE NOT EXISTS(SELECT 1 FROM shields WHERE user_id=?)",
        (uid, uid)
    )

async def get_shield(uid: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure_row(db, uid)
        cur = await db.execute("SELECT value FROM shields WHERE user_id=?", (uid,))
        row = await cur.fetchone(); await cur.close()
        return int(row[0]) if row else 0

async def get_max_shield(uid: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure_row(db, uid)
        cur = await db.execute("SELECT max_value FROM shields WHERE user_id=?", (uid,))
        row = await cur.fetchone(); await cur.close()
        return int(row[0]) if row else 50

async def set_shield(uid: int, value: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure_row(db, uid)
        await db.execute("UPDATE shields SET value=? WHERE user_id=?", (max(0, value), uid))
        await db.commit()

async def add_shield(uid: int, delta: int, cap_to_max: bool = True) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure_row(db, uid)
        cur = await db.execute("SELECT value, max_value FROM shields WHERE user_id=?", (uid,))
        row = await cur.fetchone(); await cur.close()
        val, mx = int(row[0]), int(row[1]) if row else (0, 50)
        val += int(delta)
        if cap_to_max:
            val = max(0, min(val, mx))
        await db.execute("UPDATE shields SET value=? WHERE user_id=?", (val, uid))
        await db.commit()
        return val

async def set_max_shield(uid: int, mx: int, keep_ratio: bool = False):
    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure_row(db, uid)
        if keep_ratio:
            cur = await db.execute("SELECT value, max_value FROM shields WHERE user_id=?", (uid,))
            row = await cur.fetchone(); await cur.close()
            old_v, old_m = int(row[0]), int(row[1]) if row else (0, 50)
            new_v = 0 if old_m == 0 else int(round(old_v * (mx / old_m)))
            await db.execute("UPDATE shields SET value=?, max_value=? WHERE user_id=?", (new_v, mx, uid))
        else:
            await db.execute("UPDATE shields SET max_value=? WHERE user_id=?", (mx, uid))
        await db.commit()

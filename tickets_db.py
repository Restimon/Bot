# tickets_db.py
from __future__ import annotations
import os, shutil
import aiosqlite

# ── Chemin DB persistant ───────────────────────────────────────────
try:
    from data.storage import get_sqlite_path
except Exception:
    def get_sqlite_path(name="gotvalis.sqlite3"):
        return os.getenv("GOTVALIS_DB") or "/persistent/gotvalis.sqlite3"

DB_PATH = get_sqlite_path("gotvalis.sqlite3")

def _maybe_migrate_local_db():
    old = "gotvalis.sqlite3"
    try:
        if os.path.exists(old) and not os.path.exists(DB_PATH):
            os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
            shutil.copy2(old, DB_PATH)
    except Exception:
        pass

_maybe_migrate_local_db()

CREATE_TICKETS_SQL = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS tickets (
    user_id INTEGER PRIMARY KEY,
    count   INTEGER NOT NULL
);
"""

async def init_tickets_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(CREATE_TICKETS_SQL)
        await db.commit()

async def get_tickets(user_id: int) -> int:
    await init_tickets_db()
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT count FROM tickets WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        await cur.close()
        return int(row[0]) if row else 0

async def add_tickets(user_id: int, delta: int) -> int:
    """Ajoute (ou retire) des tickets et retourne le nouveau total."""
    await init_tickets_db()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO tickets(user_id, count) VALUES(?, 0) "
            "ON CONFLICT(user_id) DO NOTHING",
            (user_id,),
        )
        await db.execute(
            "UPDATE tickets SET count = MAX(0, count + ?) WHERE user_id=?",
            (delta, user_id),
        )
        await db.commit()
        cur = await db.execute("SELECT count FROM tickets WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        await cur.close()
        return int(row[0]) if row else 0

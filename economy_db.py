# economy_db.py (extrait)
import time
import aiosqlite

DB_PATH = "gotvalis.sqlite3"

SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS wallets (
  user_id TEXT PRIMARY KEY,
  balance INTEGER NOT NULL DEFAULT 0,
  last_change_ts INTEGER NOT NULL DEFAULT 0,
  last_reason TEXT NOT NULL DEFAULT ''
);

-- (facultatif) journal
CREATE TABLE IF NOT EXISTS wallet_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id TEXT NOT NULL,
  delta INTEGER NOT NULL,
  reason TEXT NOT NULL,
  ts INTEGER NOT NULL
);
"""

async def init_economy_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(SCHEMA)
        await db.commit()

async def get_balance(user_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT balance FROM wallets WHERE user_id=?", (str(user_id),)) as cur:
            row = await cur.fetchone()
        return row[0] if row else 0

async def add_balance(user_id: int, delta: int, reason: str = "") -> int:
    """
    Ajoute (ou retire) des GoldValis, en clampant le solde à >= 0.
    Retourne le nouveau solde.
    """
    uid = str(user_id)
    now = int(time.time())
    async with aiosqlite.connect(DB_PATH) as db:
        # s'assure que le wallet existe
        await db.execute(
            "INSERT INTO wallets(user_id, balance, last_change_ts, last_reason) "
            "VALUES(?, 0, ?, ?) "
            "ON CONFLICT(user_id) DO NOTHING",
            (uid, now, reason),
        )
        # clamp en SQL (évite une lecture/écriture séparée)
        await db.execute(
            "UPDATE wallets "
            "SET balance = CASE WHEN balance + ? < 0 THEN 0 ELSE balance + ? END, "
            "    last_change_ts = ?, last_reason = ? "
            "WHERE user_id = ?",
            (delta, delta, now, reason, uid),
        )
        # (facultatif) journal
        await db.execute(
            "INSERT INTO wallet_logs(user_id, delta, reason, ts) VALUES(?,?,?,?)",
            (uid, delta, reason, now),
        )
        await db.commit()

        async with db.execute("SELECT balance FROM wallets WHERE user_id=?", (uid,)) as cur:
            (new_bal,) = await cur.fetchone()
    return new_bal

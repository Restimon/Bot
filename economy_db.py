# economy_db.py
# Portefeuille GoldValis basé SQLite (aiosqlite) + journal.
# Fonctions: init, get/set/add, transfert, leaderboard, historique.

from __future__ import annotations
import os, shutil, time
from typing import List, Tuple, Optional
import aiosqlite

# ── Chemin DB persistant ───────────────────────────────────────────
try:
    from data.storage import get_sqlite_path
except Exception:
    def get_sqlite_path(name="gotvalis.sqlite3"):
        return os.getenv("GOTVALIS_DB") or "/persistent/gotvalis.sqlite3"

DB_PATH = get_sqlite_path("gotvalis.sqlite3")

def _maybe_migrate_local_db():
    """Copie ./gotvalis.sqlite3 vers DB_PATH si la nouvelle n'existe pas encore."""
    old = "gotvalis.sqlite3"
    try:
        if os.path.exists(old) and not os.path.exists(DB_PATH):
            os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
            shutil.copy2(old, DB_PATH)
    except Exception:
        pass

_maybe_migrate_local_db()

SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS wallets (
  user_id TEXT PRIMARY KEY,
  balance INTEGER NOT NULL DEFAULT 0,
  last_change_ts INTEGER NOT NULL DEFAULT 0,
  last_reason TEXT NOT NULL DEFAULT ''
);

-- journal simple (facultatif mais utile)
CREATE TABLE IF NOT EXISTS wallet_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id TEXT NOT NULL,
  delta INTEGER NOT NULL,
  reason TEXT NOT NULL,
  ts INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_wallet_logs_user_ts ON wallet_logs(user_id, ts DESC);
"""

# ─────────────────────────────────────────────────────────────
# Init
# ─────────────────────────────────────────────────────────────

async def init_economy_db() -> None:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(SCHEMA)
        await db.commit()

# ─────────────────────────────────────────────────────────────
# Wallet helpers
# ─────────────────────────────────────────────────────────────

async def ensure_wallet(user_id: int) -> None:
    """Crée le wallet s'il n'existe pas (balance=0)."""
    uid = str(user_id)
    now = int(time.time())
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO wallets(user_id, balance, last_change_ts, last_reason) "
            "VALUES(?, 0, ?, '') ON CONFLICT(user_id) DO NOTHING",
            (uid, now),
        )
        await db.commit()

async def get_balance(user_id: int) -> int:
    """Retourne le solde courant (0 si wallet absent)."""
    uid = str(user_id)
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT balance FROM wallets WHERE user_id=?", (uid,)) as cur:
            row = await cur.fetchone()
        return row[0] if row else 0

async def set_balance(user_id: int, amount: int, reason: str = "admin_set") -> int:
    """Fixe le solde EXACT (>=0). Retourne le solde final."""
    uid = str(user_id)
    now = int(time.time())
    amount = max(0, int(amount))
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO wallets(user_id, balance, last_change_ts, last_reason) "
            "VALUES(?, ?, ?, ?) ON CONFLICT(user_id) DO UPDATE SET "
            "balance=excluded.balance, last_change_ts=excluded.last_change_ts, last_reason=excluded.last_reason",
            (uid, amount, now, reason),
        )
        await db.execute(
            "INSERT INTO wallet_logs(user_id, delta, reason, ts) VALUES(?,?,?,?)",
            (uid, amount, f"SET:{reason}", now),
        )
        await db.commit()
    return amount

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
            row = await cur.fetchone()
            new_bal = row[0] if row else 0
    return new_bal

async def transfer_balance(user_from: int, user_to: int, amount: int, reason: str = "transfer") -> bool:
    """Transfert sécurisé (clamp 0) de A vers B. Retourne True si ok (montant > 0 et solde suffisant)."""
    amount = int(amount)
    if amount <= 0:
        return False

    # Vérifie le solde dispo de A
    bal_from = await get_balance(user_from)
    if bal_from < amount:
        return False

    # Debit / Credit atomiques (deux requêtes, mais cohérents pour notre usage bot)
    deb_ok = (await add_balance(user_from, -amount, f"{reason}:debit")) >= 0
    if not deb_ok:
        return False

    await add_balance(user_to, amount, f"{reason}:credit")
    return True

async def reset_wallet(user_id: int, reason: str = "reset") -> None:
    """Remet à 0 le portefeuille (journalise)."""
    bal = await get_balance(user_id)
    if bal > 0:
        await add_balance(user_id, -bal, reason=reason)

# ─────────────────────────────────────────────────────────────
# Lectures avancées
# ─────────────────────────────────────────────────────────────

async def get_wallet(user_id: int) -> Tuple[int, int, str]:
    """
    Retourne (balance, last_change_ts, last_reason) pour un user.
    """
    uid = str(user_id)
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT balance, last_change_ts, last_reason FROM wallets WHERE user_id=?",
            (uid,),
        ) as cur:
            row = await cur.fetchone()
    if not row:
        return (0, 0, "")
    return int(row[0]), int(row[1]), str(row[2])

async def get_history(user_id: int, limit: int = 50) -> List[Tuple[int, int, str]]:
    """
    Retourne les dernières lignes du journal: [(delta, ts, reason), ...]
    """
    uid = str(user_id)
    limit = max(1, min(200, int(limit)))
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT delta, ts, reason FROM wallet_logs WHERE user_id=? ORDER BY ts DESC LIMIT ?",
            (uid, limit),
        ) as cur:
            rows = await cur.fetchall()
    return [(int(d), int(ts), str(r)) for (d, ts, r) in rows]

async def get_leaderboard(top_n: int = 25) -> List[Tuple[str, int]]:
    """
    Top joueurs par balance (desc).
    Retourne [(user_id_str, balance_int), ...]
    """
    top_n = max(1, min(100, int(top_n)))
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT user_id, balance FROM wallets ORDER BY balance DESC, user_id ASC LIMIT ?",
            (top_n,),
        ) as cur:
            rows = await cur.fetchall()
    return [(str(uid), int(bal)) for (uid, bal) in rows]

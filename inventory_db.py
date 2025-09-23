# inventory_db.py
# Gestion des inventaires d'objets (par émoji) pour GotValis.
# Base SQLite (asynchrone, via aiosqlite).
# Fournit : add/remove/get/set, listing, transferts, bulk ops, clear.

from __future__ import annotations
import os, shutil
import aiosqlite
from typing import Dict, List, Tuple, Optional

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

SCHEMA = """
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS inventories (
  user_id   TEXT NOT NULL,
  item_key  TEXT NOT NULL,   -- ex: "🧪", "🛡", etc.
  qty       INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (user_id, item_key)
);

CREATE INDEX IF NOT EXISTS idx_inventories_item ON inventories(item_key);
"""

# ─────────────────────────────────────────────────────────────
# Init
# ─────────────────────────────────────────────────────────────

async def init_inventory_db() -> None:
    """Initialise la table si nécessaire."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(SCHEMA)
        await db.commit()

# ─────────────────────────────────────────────────────────────
# Fonctions de base
# ─────────────────────────────────────────────────────────────

async def add_item(user_id: int, item_key: str, qty: int = 1) -> None:
    """Ajoute qty (>=1) d’un item à l’inventaire du joueur."""
    if qty <= 0:
        return
    uid = str(user_id)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO inventories(user_id, item_key, qty) VALUES(?, ?, ?)
            ON CONFLICT(user_id, item_key)
            DO UPDATE SET qty = qty + excluded.qty
            """,
            (uid, item_key, qty),
        )
        await db.commit()

async def remove_item(user_id: int, item_key: str, qty: int = 1) -> bool:
    """
    Retire qty (>=1) si disponible.
    Retourne True si l’opération réussit, False si stock insuffisant.
    """
    if qty <= 0:
        return False
    uid = str(user_id)
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT qty FROM inventories WHERE user_id=? AND item_key=?",
            (uid, item_key),
        ) as cur:
            row = await cur.fetchone()
        have = row[0] if row else 0
        if have < qty:
            return False

        new_q = have - qty
        if new_q == 0:
            await db.execute(
                "DELETE FROM inventories WHERE user_id=? AND item_key=?",
                (uid, item_key),
            )
        else:
            await db.execute(
                "UPDATE inventories SET qty=? WHERE user_id=? AND item_key=?",
                (new_q, uid, item_key),
            )
        await db.commit()
    return True

async def get_item_qty(user_id: int, item_key: str) -> int:
    """Retourne la quantité détenue pour un item (0 si absent)."""
    uid = str(user_id)
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT qty FROM inventories WHERE user_id=? AND item_key=?",
            (uid, item_key),
        ) as cur:
            row = await cur.fetchone()
    return row[0] if row else 0

async def get_all_items(user_id: int) -> List[Tuple[str, int]]:
    """Retourne [(emoji, qty), …] trié par emoji."""
    uid = str(user_id)
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT item_key, qty FROM inventories WHERE user_id=? ORDER BY item_key",
            (uid,),
        ) as cur:
            rows = await cur.fetchall()
    return [(r[0], r[1]) for r in rows]

# ─────────────────────────────────────────────────────────────
# Helpers avancés
# ─────────────────────────────────────────────────────────────

async def set_item_qty(user_id: int, item_key: str, qty: int) -> None:
    """
    Fixe la quantité EXACTE d’un item.
    Si qty <= 0 → suppression de l’entrée.
    """
    uid = str(user_id)
    async with aiosqlite.connect(DB_PATH) as db:
        if qty <= 0:
            await db.execute(
                "DELETE FROM inventories WHERE user_id=? AND item_key=?",
                (uid, item_key),
            )
        else:
            await db.execute(
                """
                INSERT INTO inventories(user_id, item_key, qty) VALUES(?, ?, ?)
                ON CONFLICT(user_id, item_key)
                DO UPDATE SET qty = excluded.qty
                """,
                (uid, item_key, qty),
            )
        await db.commit()

async def clear_inventory(user_id: int) -> None:
    """Supprime tout l’inventaire d’un joueur."""
    uid = str(user_id)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM inventories WHERE user_id=?", (uid,))
        await db.commit()

async def transfer_item(user_from: int, user_to: int, item_key: str, qty: int = 1) -> bool:
    """Transfert direct d’un item de user_from vers user_to. Retourne True si ok."""
    if qty <= 0:
        return False
    ok = await remove_item(user_from, item_key, qty)
    if not ok:
        return False
    await add_item(user_to, item_key, qty)
    return True

async def has_items(user_id: int, items: Dict[str, int]) -> bool:
    """
    Vérifie si user possède au moins les quantités demandées.
    Exemple: items = {"🧪": 2, "🛡": 1}
    """
    for k, q in items.items():
        if await get_item_qty(user_id, k) < q:
            return False
    return True

async def add_items_bulk(user_id: int, items: Dict[str, int]) -> None:
    """Ajoute plusieurs items d’un coup: items={'🧪':2,'🛡':1}"""
    uid = str(user_id)
    async with aiosqlite.connect(DB_PATH) as db:
        for k, q in items.items():
            if q <= 0:
                continue
            await db.execute(
                """
                INSERT INTO inventories(user_id, item_key, qty) VALUES(?, ?, ?)
                ON CONFLICT(user_id, item_key)
                DO UPDATE SET qty = qty + excluded.qty
                """,
                (uid, k, q),
            )
        await db.commit()

async def remove_items_bulk(user_id: int, items: Dict[str, int]) -> bool:
    """
    Retire plusieurs items si tous sont disponibles.
    Retourne False et n’effectue rien si un seul manque.
    """
    if not await has_items(user_id, items):
        return False

    uid = str(user_id)
    async with aiosqlite.connect(DB_PATH) as db:
        for k, q in items.items():
            async with db.execute(
                "SELECT qty FROM inventories WHERE user_id=? AND item_key=?",
                (uid, k),
            ) as cur:
                row = await cur.fetchone()
            have = row[0] if row else 0
            new_q = have - q
            if new_q <= 0:
                await db.execute(
                    "DELETE FROM inventories WHERE user_id=? AND item_key=?",
                    (uid, k),
                )
            else:
                await db.execute(
                    "UPDATE inventories SET qty=? WHERE user_id=? AND item_key=?",
                    (new_q, uid, k),
                )
        await db.commit()
    return True

async def get_inventory_map(user_id: int) -> Dict[str, int]:
    """Retourne l’inventaire sous forme de dict {item_key: qty} (quantités > 0)."""
    items = await get_all_items(user_id)
    return {k: int(v) for k, v in items if int(v) > 0}

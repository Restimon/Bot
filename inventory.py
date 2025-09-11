# inventory.py
import aiosqlite
from typing import Optional, Tuple

DB_PATH = "gotvalis.sqlite3"

SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS inventories(
  user_id TEXT NOT NULL,
  item_key TEXT NOT NULL,
  qty INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (user_id, item_key)
);
"""

async def init_inventory_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(SCHEMA)
        await db.commit()

async def add_item(user_id: int, item_key: str, qty: int = 1):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO inventories(user_id, item_key, qty) VALUES(?, ?, ?) "
            "ON CONFLICT(user_id, item_key) DO UPDATE SET qty = qty + excluded.qty",
            (str(user_id), item_key, qty)
        )
        await db.commit()

async def get_item_qty(user_id: int, item_key: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT qty FROM inventories WHERE user_id = ? AND item_key = ?",
            (str(user_id), item_key)
        ) as cur:
            row = await cur.fetchone()
    return row[0] if row else 0

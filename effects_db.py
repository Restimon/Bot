# effects_db.py
from __future__ import annotations

import aiosqlite
import asyncio
import json
import time
from typing import Callable, Awaitable, Dict, List, Optional, Tuple, Any

DB_PATH = "gotvalis.sqlite3"

SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS effects(
  user_id   TEXT NOT NULL,
  eff_type  TEXT NOT NULL,
  value     REAL NOT NULL DEFAULT 0,
  interval  INTEGER NOT NULL DEFAULT 0,
  next_ts   INTEGER NOT NULL DEFAULT 0,
  end_ts    INTEGER NOT NULL DEFAULT 0,
  source_id TEXT NOT NULL DEFAULT '0',
  meta_json TEXT,
  PRIMARY KEY(user_id, eff_type)
);
CREATE INDEX IF NOT EXISTS idx_effects_time ON effects(next_ts, end_ts);
"""

# Broadcaster & targets (injectés par le bot)
_BROADCASTER: Optional[Callable[[int, int, Dict[str, Any]], Awaitable[None]]] = None

def set_broadcaster(cb: Callable[[int, int, Dict[str, Any]], Awaitable[None]]) -> None:
    global _BROADCASTER
    _BROADCASTER = cb

# Util: now
def _now() -> int:
    return int(time.time())

# ─────────────────────────────────────────────────────────────
# Init
# ─────────────────────────────────────────────────────────────
_init_done = False
async def _ensure_init():
    global _init_done
    if _init_done:
        return
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(SCHEMA)
        await db.commit()
    _init_done = True

# ─────────────────────────────────────────────────────────────
# CRUD effets
# ─────────────────────────────────────────────────────────────
async def add_or_refresh_effect(
    user_id: int,
    eff_type: str,
    value: float,
    duration: int,
    interval: int = 0,
    source_id: Optional[int] = None,
    meta_json: Optional[str] = None,
) -> None:
    await _ensure_init()
    now = _now()
    next_ts = now + int(interval) if int(interval) > 0 else 0
    end_ts = now + max(0, int(duration))
    sid = str(source_id or 0)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO effects(user_id, eff_type, value, interval, next_ts, end_ts, source_id, meta_json)
            VALUES(?,?,?,?,?,?,?,?)
            ON CONFLICT(user_id, eff_type) DO UPDATE SET
              value=excluded.value,
              interval=excluded.interval,
              next_ts=excluded.next_ts,
              end_ts=excluded.end_ts,
              source_id=excluded.source_id,
              meta_json=excluded.meta_json
            """,
            (str(user_id), str(eff_type), float(value), int(interval), int(next_ts), int(end_ts), sid, meta_json)
        )
        await db.commit()

async def remove_effect(user_id: int, eff_type: str) -> None:
    await _ensure_init()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM effects WHERE user_id=? AND eff_type=?", (str(user_id), str(eff_type)))
        await db.commit()

async def has_effect(user_id: int, eff_type: str) -> bool:
    await _ensure_init()
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT 1 FROM effects WHERE user_id=? AND eff_type=? AND end_ts > ?",
            (str(user_id), str(eff_type), _now())
        ) as cur:
            row = await cur.fetchone()
    return bool(row)

async def list_effects(user_id: int) -> List[Tuple[str, float, int, int, int, str, Optional[str]]]:
    """
    Retourne [(eff_type, value, interval, next_ts, end_ts, source_id, meta_json), ...]
    (uniquement effets encore actifs)
    """
    await _ensure_init()
    now = _now()
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT eff_type, value, interval, next_ts, end_ts, source_id, meta_json "
            "FROM effects WHERE user_id=? AND end_ts > ?",
            (str(user_id), now)
        ) as cur:
            rows = await cur.fetchall()
    out: List[Tuple[str, float, int, int, int, str, Optional[str]]] = []
    for r in rows:
        out.append((r[0], float(r[1]), int(r[2]), int(r[3]), int(r[4]), str(r[5]), r[6]))
    return out

# ─────────────────────────────────────────────────────────────
# Malus d'attaque (flat + pourcentage)
# ─────────────────────────────────────────────────────────────
async def get_outgoing_damage_penalty(user_id: int, base: int = 0) -> int:
    """
    Calcule un malus total INT à soustraire :
      - flat : 1 si poison actif (simple), + somme des 'outgoing_penalty_flat'
      - pourcentage(s) : somme des 'outgoing_penalty' (0..1), appliquée à 'base'
    """
    await _ensure_init()
    rows = await list_effects(user_id)
    flat = 0
    pct  = 0.0

    # simple : poison = -1 (si tu veux infection/brûlure, ajoute-les ici)
    for eff_type, value, interval, next_ts, end_ts, source_id, meta in rows:
        if eff_type == "poison":
            flat += 1
        elif eff_type == "outgoing_penalty_flat":
            try:
                flat += int(value)
            except Exception:
                pass
        elif eff_type == "outgoing_penalty":  # ex: Nathaniel -10% (0.10) 1h
            try:
                pct += float(value)
            except Exception:
                pass

    pct = max(0.0, min(pct, 0.90))
    extra = int(round(max(0, int(base)) * pct))
    return max(0, int(flat) + int(extra))

# ─────────────────────────────────────────────────────────────
# Virus: transfert sur attaque si l’attaquant le porte
# ─────────────────────────────────────────────────────────────
async def transfer_virus_on_attack(attacker_id: int, target_id: int) -> None:
    await _ensure_init()
    now = _now()
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT value, interval, next_ts, end_ts FROM effects "
            "WHERE user_id=? AND eff_type='virus' AND end_ts > ?",
            (str(attacker_id), now)
        ) as cur:
            row = await cur.fetchone()
    if not row:
        return
    val, interval, next_ts, end_ts = float(row[0]), int(row[1]), int(row[2]), int(row[3])
    remain = max(0, end_ts - now)
    if remain <= 0:
        return
    # applique à la cible avec même reste de durée (rafraîchit next_ts)
    await add_or_refresh_effect(
        user_id=target_id, eff_type="virus", value=val,
        duration=remain, interval=interval, source_id=attacker_id, meta_json=None
    )

# ─────────────────────────────────────────────────────────────
# Boucle des effets (ticks) + broadcast
# ─────────────────────────────────────────────────────────────
async def _tick_damage(user_id: int, value: int, label: str, color: int, source_id: Optional[int] = None) -> Dict[str, Any]:
    """Inflige des dégâts 'value' au user_id (avec revive full si mort). Retourne payload de log."""
    from stats_db import deal_damage, is_dead, revive_full
    res = await deal_damage(int(source_id or 0), user_id, max(0, int(value)))
    ko_txt = ""
    if await is_dead(user_id):
        await revive_full(user_id)
        ko_txt = " (KO → réanimé)"
    return {
        "title": "Effets — dégâts",
        "lines": [f"{label}: **-{value} PV**{ko_txt}"],
        "color": color,
        "user_id": user_id,
    }

async def _tick_heal(user_id: int, value: int) -> Dict[str, Any]:
    from stats_db import heal_user
    await heal_user(user_id, user_id, max(0, int(value)))
    return {
        "title": "Effets — soin",
        "lines": [f"Régénération: **+{value} PV**"],
        "color": 0x2ecc71,
        "user_id": user_id,
    }

async def _broadcast_to_all_targets(payload: Dict[str, Any], get_targets: Callable[[], List[Tuple[int, int]]]) -> None:
    if _BROADCASTER is None:
        return
    try:
        for gid, cid in (get_targets() or []):
            await _BROADCASTER(int(gid), int(cid), dict(payload))
    except Exception:
        pass

async def _effects_gc(db: aiosqlite.Connection, now: int) -> None:
    await db.execute("DELETE FROM effects WHERE end_ts <= ?", (now,))
    await db.commit()

async def effects_loop(get_targets: Callable[[], List[Tuple[int, int]]], interval: int = 30):
    """
    Boucle asynchrone:
      - Ticks des effets à intervalle > 0 quand next_ts <= now (poison/infection/brûlure/regen)
      - GC des effets expirés
      - Broadcast de logs simples
    """
    await _ensure_init()
    await asyncio.sleep(2)
    while True:
        now = _now()
        try:
            # fetch ticks à exécuter
            async with aiosqlite.connect(DB_PATH) as db:
                async with db.execute(
                    "SELECT user_id, eff_type, value, interval, next_ts, end_ts, source_id "
                    "FROM effects WHERE next_ts > 0 AND next_ts <= ? AND end_ts > ?",
                    (now, now)
                ) as cur:
                    rows = await cur.fetchall()

                # exécute les ticks
                for uid, eff_type, value, itv, next_ts, end_ts, source_id in rows:
                    uid_i = int(uid)
                    itv_i = int(itv)
                    val_i = int(round(float(value)))
                    src_i = int(source_id) if str(source_id).isdigit() else 0

                    payload: Optional[Dict[str, Any]] = None

                    if eff_type in ("poison", "brulure", "infection"):
                        # infection: certains porteurs ne prennent pas les dégâts (Abomination/Anna)
                        if eff_type == "infection":
                            try:
                                from passifs import should_block_infection_tick_damage
                                if await should_block_infection_tick_damage(uid_i):
                                    payload = {
                                        "title": "Effets — infection",
                                        "lines": ["Infection: (aucun dégât — immunité spéciale)"],
                                        "color": 0xf39c12,
                                        "user_id": uid_i,
                                    }
                                else:
                                    payload = await _tick_damage(uid_i, val_i, "Infection", 0xf39c12, src_i)
                            except Exception:
                                payload = await _tick_damage(uid_i, val_i, "Infection", 0xf39c12, src_i)
                        elif eff_type == "poison":
                            payload = await _tick_damage(uid_i, val_i, "Poison", 0x9b59b6, src_i)
                        else:  # brûlure
                            payload = await _tick_damage(uid_i, val_i, "Brûlure", 0xe67e22, src_i)

                    elif eff_type == "regen":
                        payload = await _tick_heal(uid_i, val_i)

                    # planifie prochain tick
                    nxt = now + max(1, itv_i)
                    await db.execute("UPDATE effects SET next_ts=? WHERE user_id=? AND eff_type=?", (nxt, uid, eff_type))
                    await db.commit()

                    if payload:
                        await _broadcast_to_all_targets(payload, get_targets)

                # garbage collect (expirés)
                await _effects_gc(db, now)

        except Exception:
            # on avale pour ne pas arrêter la boucle
            pass

        await asyncio.sleep(max(5, int(interval)))

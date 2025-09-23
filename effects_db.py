# effects_db.py
from __future__ import annotations

import os, shutil, asyncio
import json
import time
from typing import Callable, Dict, List, Optional, Tuple, Any

import aiosqlite

# Utilisé par les ticks
from stats_db import deal_damage, heal_user, is_dead, revive_full

# Optionnel: immunités/particularités définies côté passifs
try:
    from passifs import should_block_infection_tick_damage, trigger as passifs_trigger
except Exception:
    async def should_block_infection_tick_damage(user_id: int) -> bool:  # type: ignore
        return False
    async def passifs_trigger(event: str, **ctx) -> Dict[str, Any]:  # type: ignore
        return {}

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
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS effects(
  user_id   TEXT NOT NULL,
  eff_type  TEXT NOT NULL,
  value     REAL NOT NULL DEFAULT 0,
  interval  INTEGER NOT NULL DEFAULT 0,     -- secondes (0 = pas de tick, buff pur)
  next_ts   INTEGER NOT NULL DEFAULT 0,     -- prochain tick
  end_ts    INTEGER NOT NULL,               -- expiration
  source_id TEXT NOT NULL DEFAULT '0',      -- appliqué par qui
  meta_json TEXT,                           -- champ libre
  PRIMARY KEY(user_id, eff_type)
);

CREATE INDEX IF NOT EXISTS idx_effects_end ON effects(end_ts);
CREATE INDEX IF NOT EXISTS idx_effects_next ON effects(next_ts);
"""

# ---------------------------------------------------------------------
# init
# ---------------------------------------------------------------------
async def init_effects_db() -> None:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(SCHEMA)
        await db.commit()

# ---------------------------------------------------------------------
# helpers basiques
# ---------------------------------------------------------------------
def _now() -> int:
    return int(time.time())

async def has_effect(user_id: int, eff_type: str) -> bool:
    now = _now()
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT 1 FROM effects WHERE user_id=? AND eff_type=? AND end_ts>?",
            (str(user_id), eff_type, now)
        ) as cur:
            return (await cur.fetchone()) is not None

async def list_effects(user_id: int) -> List[Tuple[str, float, int, int, int, str, Optional[str]]]:
    """
    Retourne une liste de tuples :
      (eff_type, value, interval, next_ts, end_ts, source_id, meta_json)
    pour les effets encore valides.
    """
    now = _now()
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """SELECT eff_type, value, interval, next_ts, end_ts, source_id, meta_json
               FROM effects
               WHERE user_id=? AND end_ts>? ORDER BY end_ts ASC""",
            (str(user_id), now)
        ) as cur:
            rows = await cur.fetchall()
    out: List[Tuple[str, float, int, int, int, str, Optional[str]]] = []
    for r in rows:
        out.append((
            str(r[0]), float(r[1]), int(r[2]), int(r[3]), int(r[4]),
            str(r[5]), r[6] if r[6] is None else str(r[6])
        ))
    return out

async def remove_effect(user_id: int, eff_type: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM effects WHERE user_id=? AND eff_type=?", (str(user_id), eff_type))
        await db.commit()

# ---------------------------------------------------------------------
# add_or_refresh_effect
# ---------------------------------------------------------------------
async def add_or_refresh_effect(
    user_id: int,
    eff_type: str,
    value: float,
    duration: int,
    interval: int,
    source_id: Optional[int] = 0,
    meta_json: Optional[str] = None,
) -> bool:
    """
    Ajoute ou prolonge un effet.
    - Si interval>0 → tick à chaque 'interval'.
    - Si interval==0 → buff/état passif (expire à end_ts, pas de tick).
    Retourne False si bloqué (ex: immunité via passifs) pour certains statuts.
    """

    # Vérification d'immunités côté passifs (statuts négatifs usuels)
    if eff_type in ("poison", "infection", "virus", "brulure"):
        try:
            res = await passifs_trigger("on_effect_pre_apply", user_id=int(user_id), eff_type=str(eff_type))
            if res.get("blocked"):
                return False
        except Exception:
            pass

    now = _now()
    end_ts = now + max(1, int(duration))
    iv = max(0, int(interval))
    val = float(value)

    # Stocke meta en JSON valide
    meta = None
    if meta_json is not None:
        try:
            json.loads(meta_json)  # valide ?
            meta = meta_json
        except Exception:
            meta = json.dumps({"raw": meta_json})

    existed = False
    prev_next = 0

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT next_ts FROM effects WHERE user_id=? AND eff_type=?",
            (str(user_id), eff_type)
        ) as cur:
            row = await cur.fetchone()
            if row:
                existed = True
                prev_next = int(row[0])

        if iv > 0:
            # Programme le prochain tick : si existait déjà, garde le plus proche
            next_ts = prev_next if (existed and prev_next > now) else (now + iv)
        else:
            next_ts = 0

        await db.execute(
            """INSERT INTO effects(user_id, eff_type, value, interval, next_ts, end_ts, source_id, meta_json)
               VALUES(?,?,?,?,?,?,?,?)
               ON CONFLICT(user_id, eff_type) DO UPDATE SET
                 value=excluded.value,
                 interval=excluded.interval,
                 next_ts=excluded.next_ts,
                 end_ts=excluded.end_ts,
                 source_id=excluded.source_id,
                 meta_json=excluded.meta_json
            """,
            (str(user_id), str(eff_type), float(val), int(iv), int(next_ts), int(end_ts), str(source_id or 0), meta)
        )
        await db.commit()

    return True

# ---------------------------------------------------------------------
# Pénalité aux dégâts sortants (malus d'attaque)
# ---------------------------------------------------------------------
async def get_outgoing_damage_penalty(user_id: int) -> int:
    """
    Somme des malus "plats" connus :
      - poison actif → -1
      - outgoing_penalty (effet appliqué par certains passifs) :
            * si value >= 1 → -int(value)
            * si 0 < value < 1 → -1 (au moins)
    """
    now = _now()
    penalty = 0

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT eff_type, value FROM effects WHERE user_id=? AND end_ts>?",
            (str(user_id), now)
        ) as cur:
            rows = await cur.fetchall()

    for t, v in rows:
        t = str(t)
        try:
            val = float(v)
        except Exception:
            val = 0.0

        if t == "poison":
            penalty += 1
        elif t == "outgoing_penalty":
            if val >= 1.0:
                penalty += int(val)
            elif val > 0.0:
                penalty += 1

    return max(0, int(penalty))

# ---------------------------------------------------------------------
# "Virus" — transfert sur attaque
# ---------------------------------------------------------------------
async def transfer_virus_on_attack(attacker_id: int, target_id: int) -> None:
    """
    Si l'attaquant a un effet 'virus', on le COPIE sur la cible avec la durée restante.
    (On ne le retire pas de l'attaquant → contagieux.)
    """
    now = _now()
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT value, interval, next_ts, end_ts, source_id, meta_json "
            "FROM effects WHERE user_id=? AND eff_type='virus' AND end_ts>?",
            (str(attacker_id), now)
        ) as cur:
            row = await cur.fetchone()

    if not row:
        return

    value, interval, next_ts, end_ts, source_id, meta_json = row
    remain = max(1, int(end_ts) - now)
    # Copie sur la cible (même interval/valeur)
    await add_or_refresh_effect(
        user_id=target_id,
        eff_type="virus",
        value=float(value),
        duration=remain,
        interval=int(interval),
        source_id=int(attacker_id),
        meta_json=meta_json if isinstance(meta_json, str) else None,
    )

# ---------------------------------------------------------------------
# Broadcaster & boucle de ticks
# ---------------------------------------------------------------------
from typing import Callable as _Callable
Broadcaster = _Callable[[int, int, Dict[str, Any]], Any]
_broadcaster: Optional[Broadcaster] = None

def set_broadcaster(cb: Broadcaster) -> None:
    """
    cb(guild_id:int, channel_id:int, payload:dict)
    payload attendu: {"title": str, "lines": List[str], "color": int, "user_id": Optional[int]}
    """
    global _broadcaster
    _broadcaster = cb

async def _broadcast_for_user(user_id: int, lines: List[str], color: int = 0x2ecc71) -> None:
    if not _broadcaster or not lines:
        return
    payload = {
        "title": "⏳ Effets en cours",
        "lines": lines,
        "color": color,
        "user_id": int(user_id),
    }
    try:
        await _broadcaster(0, 0, payload)  # type: ignore
    except Exception:
        pass

async def _tick_once() -> None:
    """
    Un passage de ticks :
      - applique les ticks échus (poison/infection/brulure/regen…)
      - nettoie les expirés
      - envoie un résumé par joueur
    """
    now = _now()
    to_heal: Dict[int, int] = {}     # user_id -> somme heal
    to_dot: Dict[int, int] = {}      # user_id -> somme dmg
    ticked: List[Tuple[str, str]] = []  # [(user_id, eff_type)] pour mettre à jour next_ts

    # 1) Récupère tous les effets avec tick dû
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """SELECT user_id, eff_type, value, interval, next_ts, end_ts, source_id
               FROM effects
               WHERE interval>0 AND next_ts>0 AND next_ts<=? AND end_ts>?""",
            (now, now)
        ) as cur:
            rows = await cur.fetchall()

    # 2) Applique les ticks
    for user_id_s, eff_type, value, interval, next_ts, end_ts, source_id in rows:
        uid = int(user_id_s)
        val = int(float(value))
        iv = int(interval)

        if end_ts <= now:
            continue

        if eff_type == "regen":
            if val > 0:
                await heal_user(uid, val)
                to_heal[uid] = to_heal.get(uid, 0) + val

        elif eff_type in ("poison", "infection", "brulure"):
            if eff_type == "infection":
                try:
                    if await should_block_infection_tick_damage(uid):
                        ticked.append((user_id_s, eff_type))
                        continue
                except Exception:
                    pass

            if val > 0:
                try:
                    await deal_damage(int(source_id) if str(source_id).isdigit() else 0, uid, val)
                except Exception:
                    pass
                to_dot[uid] = to_dot.get(uid, 0) + val

        ticked.append((user_id_s, eff_type))

        try:
            if await is_dead(uid):
                await revive_full(uid)
        except Exception:
            pass

    # 3) Décale next_ts
    if ticked:
        async with aiosqlite.connect(DB_PATH) as db:
            for uid_s, t in ticked:
                await db.execute(
                    "UPDATE effects SET next_ts = next_ts + interval WHERE user_id=? AND eff_type=?",
                    (uid_s, t)
                )
            await db.commit()

    # 4) Nettoyage simple des expirés
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM effects WHERE end_ts<=?", (now,))
        await db.commit()

    # 5) Broadcasting
    for uid, amount in to_heal.items():
        await _broadcast_for_user(uid, [f"💕 +{amount} PV (régénération)"], color=0x2ecc71)

    for uid, amount in to_dot.items():
        await _broadcast_for_user(uid, [f"☠️ -{amount} PV (DOT)"], color=0xe67e22)

# ---------------------------------------------------------------------
# Boucle publique
# ---------------------------------------------------------------------
async def effects_loop(
    get_targets: Optional[Callable[[], List[Tuple[int, int]]]] = None,
    interval: int = 30
) -> None:
    """
    Boucle infinie d'application des effets (ticks).
    """
    await init_effects_db()  # au cas où
    iv = max(5, int(interval))  # évite <5s
    while True:
        try:
            await _tick_once()
        except Exception:
            pass
        await asyncio.sleep(iv)

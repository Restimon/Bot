# effects_db.py
from __future__ import annotations

import asyncio
import random
import time
from typing import Optional, Dict, Any, List, Callable, Tuple

import aiosqlite

from stats_db import (
    deal_damage,
    heal_user,
    get_hp,
    is_dead,
    revive_full,
)
# NOTE: l'économie est déjà branchée dans stats_db (deal_damage / heal_user)

DB_PATH = "gotvalis.sqlite3"

SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS player_effects(
  user_id   TEXT NOT NULL,
  eff_type  TEXT NOT NULL,            -- 'poison','virus','infection','regen','reduction','esquive','immunite'
  value     REAL NOT NULL DEFAULT 0,  -- intensité (ex: dmg par tick, % reduc, % dodge)
  interval  INTEGER NOT NULL DEFAULT 0, -- secondes entre ticks (0 = pas de tick)
  next_ts   INTEGER NOT NULL DEFAULT 0, -- prochain tick
  end_ts    INTEGER NOT NULL,           -- fin d'effet (timestamp)
  source_id TEXT NOT NULL DEFAULT '0',  -- auteur de l'effet (pour attribuer dégâts/coins)
  meta      TEXT NOT NULL DEFAULT '{}', -- JSON libre (emoji, label, etc.)
  PRIMARY KEY(user_id, eff_type)
);

CREATE INDEX IF NOT EXISTS idx_player_effects_end ON player_effects(end_ts);
"""

# ─────────────────────────────────────────────────────────────
# RÉGLAGES
# ─────────────────────────────────────────────────────────────
DOT_CRIT_CHANCE = 0.05           # 5 % par tick
INFECTION_PROPAGATE_CHANCE = 0.25  # utilisée côté combat (hook), pas ici
TICK_SCAN_INTERVAL = 30          # fréquence du scanner global (sec)

# Broadcaster (défini par le cog) : async (guild_id, channel_id, payload_dict) -> None
_BROADCAST: Optional[Callable[[int, int, Dict[str, Any]], asyncio.Future]] = None

def set_broadcaster(cb: Callable[[int, int, Dict[str, Any]], asyncio.Future]) -> None:
    """Le cog combat fournit un callback pour poster les embeds de ticks."""
    global _BROADCAST
    _BROADCAST = cb

def _now() -> int:
    return int(time.time())

# ─────────────────────────────────────────────────────────────
# INIT
# ─────────────────────────────────────────────────────────────
async def init_effects_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(SCHEMA)
        await db.commit()

# ─────────────────────────────────────────────────────────────
# CRUD EFFETS
# ─────────────────────────────────────────────────────────────
async def add_or_refresh_effect(
    user_id: int,
    eff_type: str,
    value: float,
    duration: int,
    *,
    interval: int = 0,
    source_id: int = 0,
    meta_json: str = "{}",
) -> None:
    """
    Ajoute un effet, ou le remplace s'il existe déjà (renouvelle la durée).
    Ne stacke PAS la valeur (on remplace).
    """
    uid = str(user_id)
    sid = str(source_id)
    now = _now()
    end_ts = now + max(0, duration)
    next_ts = now + interval if interval > 0 else 0
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO player_effects(user_id, eff_type, value, interval, next_ts, end_ts, source_id, meta)
            VALUES(?,?,?,?,?,?,?,?)
            ON CONFLICT(user_id, eff_type) DO UPDATE SET
              value=excluded.value,
              interval=excluded.interval,
              next_ts=excluded.next_ts,
              end_ts=excluded.end_ts,
              source_id=excluded.source_id,
              meta=excluded.meta
            """,
            (uid, eff_type, float(value), int(interval), int(next_ts), int(end_ts), sid, meta_json),
        )
        await db.commit()

async def remove_effect(user_id: int, eff_type: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM player_effects WHERE user_id=? AND eff_type=?", (str(user_id), eff_type))
        await db.commit()

async def clear_effects(user_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM player_effects WHERE user_id=?", (str(user_id),))
        await db.commit()

async def purge_by_types(user_id: int, types: List[str]) -> None:
    if not types:
        return
    q = ",".join("?" for _ in types)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"DELETE FROM player_effects WHERE user_id=? AND eff_type IN ({q})", (str(user_id), *types))
        await db.commit()

async def get_effect(user_id: int, eff_type: str) -> Optional[Tuple[float, int, int, int, str, str]]:
    """Retourne (value, interval, next_ts, end_ts, source_id, meta_json) ou None."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT value, interval, next_ts, end_ts, source_id, meta FROM player_effects WHERE user_id=? AND eff_type=?",
            (str(user_id), eff_type),
        ) as cur:
            row = await cur.fetchone()
    return row if row else None

async def list_effects(user_id: int) -> List[Tuple[str, float, int, int, int, str, str]]:
    """
    Retourne liste de tuples:
      (eff_type, value, interval, next_ts, end_ts, source_id, meta_json)
    """
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT eff_type, value, interval, next_ts, end_ts, source_id, meta FROM player_effects WHERE user_id=?",
            (str(user_id),),
        ) as cur:
            rows = await cur.fetchall()
    return rows

async def has_effect(user_id: int, eff_type: str) -> bool:
    return (await get_effect(user_id, eff_type)) is not None

# ─────────────────────────────────────────────────────────────
# RÈGLES DE COMBAT — HELPERS POUR LE COG
# ─────────────────────────────────────────────────────────────
async def get_outgoing_damage_penalty(user_id: int) -> int:
    """
    Pénalité d'attaque directe appliquée à l'ATTAQUANT.
    Règle: si le joueur est sous **poison** → −1 dégât (min 0).
    (Le virus n'applique AUCUN malus direct.)
    """
    eff = await get_effect(user_id, "poison")
    return 1 if eff is not None else 0

async def transfer_virus_on_attack(attacker_id: int, target_id: int) -> bool:
    """
    Si l'attaquant porte un **virus** :
      - Inflige 5 dégâts directs à l'ANCIEN PORTEUR (source système = 0).
      - Inflige 5 dégâts directs à la CIBLE (source = attaquant).
      - Déplace l'effet 'virus' à la cible en **conservant** interval/next_ts/end_ts (timer inchangé).
      - Retourne True si transfert effectué.
    """
    row = await get_effect(attacker_id, "virus")
    if not row:
        return False

    value, interval, next_ts, end_ts, _src, meta_json = row

    # 1) piqûre de sortie (ancien porteur)
    await deal_damage(0, attacker_id, 5)

    # 2) piqûre d'entrée (nouvelle cible)
    await deal_damage(attacker_id, target_id, 5)

    # 3) transfert (timer conservé)
    await remove_effect(attacker_id, "virus")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO player_effects(user_id, eff_type, value, interval, next_ts, end_ts, source_id, meta)
            VALUES(?,?,?,?,?,?,?,?)
            ON CONFLICT(user_id, eff_type) DO UPDATE SET
              value=excluded.value,
              interval=excluded.interval,
              next_ts=excluded.next_ts,
              end_ts=excluded.end_ts,
              source_id=excluded.source_id,
              meta=excluded.meta
            """,
            (str(target_id), "virus", float(value), int(interval), int(next_ts), int(end_ts), str(attacker_id), meta_json or "{}"),
        )
        await db.commit()
    return True

# ─────────────────────────────────────────────────────────────
# TICKER : applique les effets périodiques
# ─────────────────────────────────────────────────────────────
async def _apply_dot_tick(
    guild_id: int,
    channel_id: int,
    user_id: int,
    eff_type: str,
    value: float,
    end_ts: int,
    source_id: int,
) -> None:
    """Applique un tick de DOT (crit 5%, pas de réduction, PB→PV), broadcast + KO handling."""
    # immunité bloque les dégâts (mais ne purge pas)
    if await has_effect(user_id, "immunite"):
        return

    dmg = int(value)
    if random.random() < DOT_CRIT_CHANCE:
        dmg *= 2  # crit par tick

    # Attribution: source du DOT, sauf si auto-dommage (source == victime) → système
    attacker = source_id if source_id != user_id else 0

    res = await deal_damage(attacker, user_id, dmg)

    # KO ? applique ta règle 14
    if await is_dead(user_id):
        await revive_full(user_id)   # PV = 100
        await clear_effects(user_id) # clear statuts

    # broadcast
    if _BROADCAST:
        hp, mx = await get_hp(user_id)
        remain_min = max(0, (end_ts - _now()) // 60)
        icon = "🧪" if eff_type == "poison" else ("🦠" if eff_type == "virus" else "🧟")
        title = f"{icon} @{user_id} subit {dmg} dégâts ({eff_type})."
        lines = [
            f"❤️ {hp + res['lost']} − {dmg} PV = ❤️ {hp}",
            f"⏳ Temps restant : **{remain_min} min**",
        ]
        await _BROADCAST(guild_id, channel_id, {"title": title, "lines": lines, "color": 0x2ecc71})

async def _apply_regen_tick(
    guild_id: int,
    channel_id: int,
    user_id: int,
    value: float,
    end_ts: int,
    source_id: int,
) -> None:
    healed = await heal_user(source_id or user_id, user_id, int(value))
    if healed <= 0:
        return
    # broadcast
    if _BROADCAST:
        hp, mx = await get_hp(user_id)
        remain_min = max(0, (end_ts - _now()) // 60)
        title = f"💕 @{user_id} régénère {healed} PV."
        lines = [
            f"❤️ {hp - healed} + {healed} PV = ❤️ {hp}",
            f"⏳ Temps restant : **{remain_min} min**",
        ]
        await _BROADCAST(guild_id, channel_id, {"title": title, "lines": lines, "color": 0xe91e63})

async def _tick_once(guild_id: int, channel_id: int) -> None:
    now = _now()

    # Expire naturellement
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM player_effects WHERE end_ts <= ?", (now,))
        await db.commit()

    # Effets à déclencher
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT user_id, eff_type, value, interval, next_ts, end_ts, source_id "
            "FROM player_effects "
            "WHERE interval > 0 AND next_ts > 0 AND next_ts <= ?",
            (now,),
        ) as cur:
            due = await cur.fetchall()

    # Replanifie + applique
    for uid, eff_type, value, interval, next_ts, end_ts, source_id in due:
        # replanifier le prochain tick AVANT d'appliquer (pour éviter double tick en cas d'exception)
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE player_effects SET next_ts = ? WHERE user_id=? AND eff_type=?",
                (now + int(interval), uid, eff_type),
            )
            await db.commit()

        uid_i = int(uid)
        src_i = int(source_id)

        try:
            if eff_type in ("poison", "virus", "infection"):
                await _apply_dot_tick(guild_id, channel_id, uid_i, eff_type, float(value), int(end_ts), src_i)
            elif eff_type == "regen":
                await _apply_regen_tick(guild_id, channel_id, uid_i, float(value), int(end_ts), src_i)
            else:
                # reduction/esquive/immunite n'ont pas de tick
                pass
        except Exception:
            # on isole les erreurs d'un joueur/effet pour ne pas arrêter la boucle
            pass

# ─────────────────────────────────────────────────────────────
# LOOP PUBLIQUE À LANCER DEPUIS LE COG
# ─────────────────────────────────────────────────────────────
async def effects_loop(get_targets: Callable[[], List[Tuple[int, int]]], interval: int = TICK_SCAN_INTERVAL):
    """
    Lance une boucle qui scanne tous les effets et exécute les ticks.
    - get_targets() doit renvoyer une liste de (guild_id, channel_id) où poster les embeds de ticks
      (ex: le dernier salon combat par serveur).
    - interval = fréquence de scan (en secondes). Les ticks réels suivent leur propre 'interval'.
    """
    await init_effects_db()
    while True:
        try:
            targets = get_targets() or []
            for guild_id, channel_id in targets:
                await _tick_once(guild_id, channel_id)
        except Exception:
            pass
        await asyncio.sleep(interval)

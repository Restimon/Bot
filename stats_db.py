# stats_db.py
# Gestion centralisée des stats joueurs :
# - PV (hp), PV max (max_hp), Bouclier (shield/PB)
# - Cumulés : kills, deaths, dmg_dealt, dmg_taken, heal_done
# - KO/kill automatiques
# - Récompenses éco : +1 GV/dégât, +1 GV/soin, +50 GV/kill, −25 GV/mort
# SQLite async (aiosqlite)

from __future__ import annotations
import os, shutil, time
from typing import Tuple, Optional, List, Dict, Any
import aiosqlite

from economy_db import add_balance  # doit clampler à >= 0 côté économie

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

CREATE TABLE IF NOT EXISTS players_stats(
  user_id   TEXT PRIMARY KEY,
  hp        INTEGER NOT NULL,
  max_hp    INTEGER NOT NULL,
  shield    INTEGER NOT NULL,
  -- cumulés
  kills     INTEGER NOT NULL DEFAULT 0,
  deaths    INTEGER NOT NULL DEFAULT 0,
  dmg_dealt INTEGER NOT NULL DEFAULT 0,
  dmg_taken INTEGER NOT NULL DEFAULT 0,
  heal_done INTEGER NOT NULL DEFAULT 0,
  -- état KO
  is_dead    INTEGER NOT NULL DEFAULT 0,
  last_ko_ts INTEGER NOT NULL DEFAULT 0
);
"""

# Valeurs par défaut
DEFAULT_HP = 100
DEFAULT_MAX_HP = 100
DEFAULT_SHIELD = 0

# Récompenses / pénalités économie
REWARD_PER_DMG    = 1     # +1 GV / PV perdu
REWARD_PER_HEAL   = 1     # +1 GV / PV soigné
REWARD_PER_KILL   = 50    # +50 GV pour l'attaquant
PENALTY_PER_DEATH = -25   # -25 GV pour la victime

# ─────────────────────────────────────────────────────────────
# Init & migration
# ─────────────────────────────────────────────────────────────

async def init_stats_db() -> None:
    """Crée la table si besoin et ajoute les colonnes manquantes si déjà existante."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(SCHEMA)
        # Migration défensive
        cols = {
            "kills": "INTEGER NOT NULL DEFAULT 0",
            "deaths": "INTEGER NOT NULL DEFAULT 0",
            "dmg_dealt": "INTEGER NOT NULL DEFAULT 0",
            "dmg_taken": "INTEGER NOT NULL DEFAULT 0",
            "heal_done": "INTEGER NOT NULL DEFAULT 0",
            "is_dead": "INTEGER NOT NULL DEFAULT 0",
            "last_ko_ts": "INTEGER NOT NULL DEFAULT 0",
        }
        await _ensure_columns(db, "players_stats", cols)
        await db.commit()

async def _ensure_columns(db: aiosqlite.Connection, table: str, needed: Dict[str, str]) -> None:
    async with db.execute(f"PRAGMA table_info({table})") as cur:
        existing = {row[1] for row in await cur.fetchall()}  # row[1] = name
    for col, decl in needed.items():
        if col not in existing:
            await db.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")

async def _ensure_row(user_id: int) -> None:
    uid = str(user_id)
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT 1 FROM players_stats WHERE user_id=?", (uid,)) as cur:
            row = await cur.fetchone()
        if not row:
            await db.execute(
                "INSERT INTO players_stats(user_id, hp, max_hp, shield) VALUES(?,?,?,?)",
                (uid, DEFAULT_HP, DEFAULT_MAX_HP, DEFAULT_SHIELD),
            )
            await db.commit()

# ─────────────────────────────────────────────────────────────
# Getters
# ─────────────────────────────────────────────────────────────

async def get_hp(user_id: int) -> Tuple[int, int]:
    await _ensure_row(user_id)
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT hp, max_hp FROM players_stats WHERE user_id=?", (str(user_id),)) as cur:
            hp, mx = await cur.fetchone()
    return hp, mx

async def get_shield(user_id: int) -> int:
    await _ensure_row(user_id)
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT shield FROM players_stats WHERE user_id=?", (str(user_id),)) as cur:
            (pb,) = await cur.fetchone()
    return pb

async def get_profile(user_id: int) -> Dict[str, Any]:
    """Résumé utile pour affichage (/profile, etc.)."""
    await _ensure_row(user_id)
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT hp, max_hp, shield, kills, deaths, dmg_dealt, dmg_taken, heal_done, is_dead, last_ko_ts "
            "FROM players_stats WHERE user_id=?",
            (str(user_id),)
        ) as cur:
            hp, mx, pb, k, d, dd, dt, hd, dead, ko_ts = await cur.fetchone()
    return {
        "hp": hp, "max_hp": mx, "shield": pb,
        "kills": k, "deaths": d, "dmg_dealt": dd, "dmg_taken": dt, "heal_done": hd,
        "is_dead": bool(dead), "last_ko_ts": ko_ts
    }

# ─────────────────────────────────────────────────────────────
# Setters simples
# ─────────────────────────────────────────────────────────────

async def set_hp(user_id: int, hp: int, *, clamp: bool = True) -> None:
    await _ensure_row(user_id)
    async with aiosqlite.connect(DB_PATH) as db:
        if clamp:
            async with db.execute("SELECT max_hp FROM players_stats WHERE user_id=?", (str(user_id),)) as cur:
                (mx,) = await cur.fetchone()
            hp = max(0, min(hp, mx))
        await db.execute("UPDATE players_stats SET hp=? WHERE user_id=?", (hp, str(user_id)))
        await db.commit()

async def set_max_hp(user_id: int, max_hp: int, *, keep_ratio: bool = False) -> None:
    await _ensure_row(user_id)
    max_hp = max(1, max_hp)
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT hp, max_hp FROM players_stats WHERE user_id=?", (str(user_id),)) as cur:
            hp, old_mx = await cur.fetchone()
        if keep_ratio and old_mx > 0:
            ratio = hp / old_mx
            hp = int(round(ratio * max_hp))
        hp = max(0, min(hp, max_hp))
        await db.execute("UPDATE players_stats SET hp=?, max_hp=? WHERE user_id=?", (hp, max_hp, str(user_id)))
        await db.commit()

async def set_shield(user_id: int, shield: int) -> None:
    await _ensure_row(user_id)
    shield = max(0, shield)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE players_stats SET shield=? WHERE user_id=?", (shield, str(user_id)))
        await db.commit()

# ─────────────────────────────────────────────────────────────
# Actions unitaires (sans attribution)
# ─────────────────────────────────────────────────────────────

async def heal_hp(user_id: int, amount: int) -> int:
    """Soigne 'amount' PV. Retourne les PV réellement rendus (pas d’éco ici)."""
    await _ensure_row(user_id)
    amount = max(0, amount)
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT hp, max_hp FROM players_stats WHERE user_id=?", (str(user_id),)) as cur:
            hp, mx = await cur.fetchone()
        if hp >= mx or amount <= 0:
            return 0
        new_hp = min(mx, hp + amount)
        healed = new_hp - hp
        await db.execute("UPDATE players_stats SET hp=? WHERE user_id=?", (new_hp, str(user_id)))
        await db.commit()
    return healed

async def damage_hp(user_id: int, amount: int) -> int:
    """
    Inflige des dégâts (sans attribution).
    Consomme d'abord le PB. Retourne les PV réellement perdus (pas d’éco ici).
    """
    await _ensure_row(user_id)
    dmg = max(0, amount)
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT hp, shield, is_dead FROM players_stats WHERE user_id=?", (str(user_id),)) as cur:
            hp, pb, dead = await cur.fetchone()

        if dead:
            return 0

        # consomme le bouclier
        if pb > 0 and dmg > 0:
            use = min(pb, dmg)
            pb -= use
            dmg -= use

        hp_after = max(0, hp - dmg)
        lost = hp - hp_after
        ko = 1 if hp_after == 0 and hp > 0 else 0
        ts = int(time.time()) if ko else 0

        await db.execute(
            "UPDATE players_stats SET hp=?, shield=?, deaths = deaths + ?, "
            "is_dead = CASE WHEN ?=1 THEN 1 ELSE is_dead END, "
            "last_ko_ts = CASE WHEN ?=1 THEN ? ELSE last_ko_ts END "
            "WHERE user_id=?",
            (hp_after, pb, ko, ko, ko, ts, str(user_id))
        )
        await db.commit()
    return lost

# ─────────────────────────────────────────────────────────────
# Actions AVEC attribution (combat) + économie
# ─────────────────────────────────────────────────────────────

async def heal_user(healer_id: int, target_id: int, amount: int) -> int:
    """
    Soigne target et crédite le soigneur (heal_done + économie).
    Retourne les PV réellement rendus.
    """
    await _ensure_row(healer_id)
    await _ensure_row(target_id)
    healed = await heal_hp(target_id, amount)
    if healed <= 0:
        return 0
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE players_stats SET heal_done = heal_done + ? WHERE user_id=?",
            (healed, str(healer_id))
        )
        await db.commit()
    # 💰 économie
    if REWARD_PER_HEAL and healed > 0:
        await add_balance(healer_id, healed * REWARD_PER_HEAL, "combat_heal")
    return healed

async def deal_damage(attacker_id: int, target_id: int, amount: int) -> Dict[str, Any]:
    """
    Inflige des dégâts avec attribution.
    - Consomme d'abord le PB de la cible.
    - Met à jour dmg_dealt (attaquant), dmg_taken (cible).
    - Si KO: deaths+1 (cible) et kills+1 (attaquant).
    - Applique les récompenses/penalités d'économie.
    Retourne: {'absorbed','lost','target_hp','target_shield','killed'}
    """
    await _ensure_row(attacker_id)
    await _ensure_row(target_id)
    dmg = max(0, amount)

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT hp, shield, is_dead FROM players_stats WHERE user_id=?",
            (str(target_id),)
        ) as cur:
            hp, pb, dead = await cur.fetchone()

        if dead:
            return {'absorbed': 0, 'lost': 0, 'target_hp': hp, 'target_shield': pb, 'killed': False}

        absorbed = 0
        if pb > 0 and dmg > 0:
            use = min(pb, dmg)
            pb -= use
            dmg -= use
            absorbed = use

        new_hp = max(0, hp - dmg)
        lost = hp - new_hp
        killed = (new_hp == 0 and hp > 0)
        ts = int(time.time()) if killed else 0

        # Update cible
        await db.execute(
            "UPDATE players_stats "
            "SET hp=?, shield=?, dmg_taken = dmg_taken + ?, deaths = deaths + ?, "
            "    is_dead = CASE WHEN ?=1 THEN 1 ELSE is_dead END, "
            "    last_ko_ts = CASE WHEN ?=1 THEN ? ELSE last_ko_ts END "
            "WHERE user_id=?",
            (new_hp, pb, lost, 1 if killed else 0, 1 if killed else 0, 1 if killed else 0, ts, str(target_id))
        )
        # Update attaquant
        await db.execute(
            "UPDATE players_stats SET dmg_dealt = dmg_dealt + ?, kills = kills + ? WHERE user_id=?",
            (lost, 1 if killed else 0, str(attacker_id))
        )
        await db.commit()

    # 💰 économie : récompenses & pénalités
    if REWARD_PER_DMG and lost > 0:
        await add_balance(attacker_id, lost * REWARD_PER_DMG, "combat_damage")
    if killed and REWARD_PER_KILL:
        await add_balance(attacker_id, REWARD_PER_KILL, "combat_kill")
    if killed and PENALTY_PER_DEATH:
        await add_balance(target_id, PENALTY_PER_DEATH, "combat_death")

    return {'absorbed': absorbed, 'lost': lost, 'target_hp': new_hp, 'target_shield': pb, 'killed': killed}

# ─────────────────────────────────────────────────────────────
# KO / Revive utilitaires
# ─────────────────────────────────────────────────────────────

async def is_dead(user_id: int) -> bool:
    await _ensure_row(user_id)
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT is_dead FROM players_stats WHERE user_id=?", (str(user_id),)) as cur:
            (dead,) = await cur.fetchone()
    return bool(dead)

async def revive_full(user_id: int) -> None:
    """Remet le joueur vivant et PV = max_hp (PB inchangé)."""
    await _ensure_row(user_id)
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT max_hp FROM players_stats WHERE user_id=?", (str(user_id),)) as cur:
            (mx,) = await cur.fetchone()
        await db.execute("UPDATE players_stats SET hp=?, is_dead=0 WHERE user_id=?", (mx, str(user_id)))
        await db.commit()

async def revive_with_hp(user_id: int, hp: int) -> None:
    """Remet le joueur vivant avec un nombre de PV donné (borné à max_hp)."""
    await _ensure_row(user_id)
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT max_hp FROM players_stats WHERE user_id=?", (str(user_id),)) as cur:
            (mx,) = await cur.fetchone()
        hp = max(1, min(hp, mx))
        await db.execute("UPDATE players_stats SET hp=?, is_dead=0 WHERE user_id=?", (hp, str(user_id)))
        await db.commit()

# ─────────────────────────────────────────────────────────────
# Leaderboards
# ─────────────────────────────────────────────────────────────

VALID_METRICS = {"kills", "deaths", "dmg_dealt", "dmg_taken", "heal_done"}

async def get_leaderboard(metric: str, limit: int = 10) -> List[Tuple[str, int]]:
    """
    Retourne [(user_id, value)] triés décroissants pour la métrique donnée.
    metric ∈ {'kills','deaths','dmg_dealt','dmg_taken','heal_done'}
    """
    if metric not in VALID_METRICS:
        raise ValueError(f"metric invalide: {metric}")
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            f"SELECT user_id, {metric} FROM players_stats ORDER BY {metric} DESC LIMIT ?",
            (limit,)
        ) as cur:
            rows = await cur.fetchall()
    return [(row[0], row[1]) for row in rows]

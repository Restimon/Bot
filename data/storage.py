# data/storage.py
from __future__ import annotations

import os
import io
import json
import time
import asyncio
from typing import Any, Dict, Optional, List, Tuple
from datetime import datetime

# ========= Emplacements persistants =========
PERSISTENT_PATH = "/persistent"
DATA_FILE = os.path.join(PERSISTENT_PATH, "data.json")

BACKUP_DIR = os.path.join(PERSISTENT_PATH, "backups")
AUTO_BACKUP_DIR = os.path.join(PERSISTENT_PATH, "auto_backups")

# ========= Réglages backups =========
MAX_BACKUPS = 20                 # backups manuels conservés
MAX_AUTO_BACKUPS = 30            # auto-backups conservés
AUTO_BACKUP_MIN_SPACING_SEC = 300  # pas d’auto-backup plus souvent que toutes les 5 min

# ========= Concurrence =========
_lock = asyncio.Lock()
_last_auto_backup_ts: float = 0.0


# ============ Utils fichiers ============
def _ensure_dirs() -> None:
    os.makedirs(PERSISTENT_PATH, exist_ok=True)
    os.makedirs(BACKUP_DIR, exist_ok=True)
    os.makedirs(AUTO_BACKUP_DIR, exist_ok=True)

def _timestamp() -> str:
    # format horodaté stable
    return datetime.utcnow().strftime("%Y-%m-%d_%H-%M-%S")

def _rotate(dirpath: str, keep: int) -> None:
    try:
        files = [os.path.join(dirpath, f) for f in os.listdir(dirpath)]
    except FileNotFoundError:
        return
    files = [f for f in files if os.path.isfile(f)]
    files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    for f in files[keep:]:
        try:
            os.remove(f)
        except Exception:
            pass

def _atomic_write_json(path: str, data: Dict[str, Any]) -> None:
    tmp = f"{path}.tmp"
    with io.open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


# ============ Schéma par défaut ============
def _default_root() -> Dict[str, Any]:
    return {
        "players": {},   # { user_id: {hp, shield, coins, tickets, stats{}, inventory{}, effects{}, cooldowns{}, equipped_character} }
        "config": {      # global + par serveur
            "guilds": {} # { guild_id: { leaderboard_channel, ... } }
        },
        "meta": {
            "last_backup": None
        }
    }

def _default_player() -> Dict[str, Any]:
    return {
        "hp": 100,
        "shield": 0,
        "coins": 0,
        "coins_total": 0,  # total cumulé gagné (classements long terme)
        "tickets": 0,
        "equipped_character": None,  # nom exact ou None
        "stats": {   # compteurs combats
            "damage": 0,
            "healing": 0,
            "kills": 0,
            "deaths": 0
        },
        "inventory": {},     # {emoji -> qty}
        "effects": {},       # {eff_type: {value, interval, end_ts, next_ts, source_id, meta}}
        "cooldowns": {}      # {"daily": ts, "attack": ts, ...}
    }


# ============ Core IO ============
async def init_storage() -> None:
    """À appeler au démarrage du bot."""
    _ensure_dirs()
    async with _lock:
        if not os.path.exists(DATA_FILE):
            _atomic_write_json(DATA_FILE, _default_root())

async def load_all() -> Dict[str, Any]:
    async with _lock:
        _ensure_dirs()
        if not os.path.exists(DATA_FILE):
            data = _default_root()
            _atomic_write_json(DATA_FILE, data)
            return data
        try:
            with io.open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            # garde-fous : assure présence des clés racines
            if not isinstance(data, dict):
                data = _default_root()
            data.setdefault("players", {})
            data.setdefault("config", {"guilds": {}})
            data.setdefault("meta", {"last_backup": None})
            return data
        except Exception:
            # si corrompu → repart propre (tu peux aussi tenter une restau auto ici)
            data = _default_root()
            _atomic_write_json(DATA_FILE, data)
            return data

async def save_all(data: Dict[str, Any], *, auto_backup: bool = True) -> None:
    async with _lock:
        _ensure_dirs()
        _atomic_write_json(DATA_FILE, data)
        if auto_backup:
            await _auto_backup(data)


# ============ Backups ============
async def backup_now(tag: Optional[str] = None) -> str:
    async with _lock:
        data = await load_all()
        stamp = _timestamp()
        base = f"backup_{stamp}"
        if tag:
            safe_tag = "".join(ch for ch in tag if ch.isalnum() or ch in "-_")
            if safe_tag:
                base += f"_{safe_tag}"
        path = os.path.join(BACKUP_DIR, base + ".json")
        _atomic_write_json(path, data)
        _rotate(BACKUP_DIR, MAX_BACKUPS)
        # maj meta.last_backup
        data["meta"]["last_backup"] = stamp
        _atomic_write_json(DATA_FILE, data)
        return path

async def _auto_backup(current_data: Optional[Dict[str, Any]] = None) -> None:
    global _last_auto_backup_ts
    now = time.time()
    if (now - _last_auto_backup_ts) < AUTO_BACKUP_MIN_SPACING_SEC:
        return
    try:
        data = current_data if current_data is not None else await load_all()
        stamp = _timestamp()
        path = os.path.join(AUTO_BACKUP_DIR, f"auto_{stamp}.json")
        _atomic_write_json(path, data)
        _rotate(AUTO_BACKUP_DIR, MAX_AUTO_BACKUPS)
        _last_auto_backup_ts = now
    except Exception:
        pass


# ============ Helpers joueurs ============
async def ensure_player(user_id: int | str) -> Dict[str, Any]:
    uid = str(user_id)
    data = await load_all()
    players = data["players"]
    if uid not in players or not isinstance(players[uid], dict):
        players[uid] = _default_player()
        await save_all(data)
    return players[uid]

async def get_player(user_id: int | str) -> Dict[str, Any]:
    data = await load_all()
    return data["players"].get(str(user_id), _default_player())

async def set_equipped_character(user_id: int | str, name: Optional[str]) -> None:
    data = await load_all()
    p = data["players"].setdefault(str(user_id), _default_player())
    p["equipped_character"] = name
    await save_all(data)

# ==== Coins / Tickets ====
async def add_coins(user_id: int | str, amount: int) -> int:
    if amount <= 0: return 0
    data = await load_all()
    p = data["players"].setdefault(str(user_id), _default_player())
    p["coins"] += amount
    p["coins_total"] += amount
    await save_all(data)
    return p["coins"]

async def spend_coins(user_id: int | str, amount: int) -> int:
    if amount <= 0: return await get_coins(user_id)
    data = await load_all()
    p = data["players"].setdefault(str(user_id), _default_player())
    p["coins"] = max(0, p["coins"] - amount)
    await save_all(data)
    return p["coins"]

async def get_coins(user_id: int | str) -> int:
    p = await get_player(user_id)
    return int(p.get("coins", 0))

async def add_tickets(user_id: int | str, qty: int) -> int:
    if qty <= 0: return await get_tickets(user_id)
    data = await load_all()
    p = data["players"].setdefault(str(user_id), _default_player())
    p["tickets"] = int(p.get("tickets", 0)) + qty
    await save_all(data)
    return p["tickets"]

async def use_ticket(user_id: int | str, qty: int = 1) -> bool:
    data = await load_all()
    p = data["players"].setdefault(str(user_id), _default_player())
    cur = int(p.get("tickets", 0))
    if cur < qty:
        return False
    p["tickets"] = cur - qty
    await save_all(data)
    return True

async def get_tickets(user_id: int | str) -> int:
    p = await get_player(user_id)
    return int(p.get("tickets", 0))

# ==== PV / PB ====
async def get_hp(user_id: int | str) -> Tuple[int, int]:
    p = await get_player(user_id)
    return int(p.get("hp", 100)), 100

async def get_shield(user_id: int | str) -> int:
    p = await get_player(user_id)
    return int(p.get("shield", 0))

async def set_hp(user_id: int | str, hp: int) -> int:
    data = await load_all()
    p = data["players"].setdefault(str(user_id), _default_player())
    p["hp"] = max(0, min(100, int(hp)))
    await save_all(data)
    return p["hp"]

async def set_shield(user_id: int | str, pb: int) -> int:
    cap = 20  # par défaut (peut être modifié par passifs ailleurs)
    data = await load_all()
    p = data["players"].setdefault(str(user_id), _default_player())
    p["shield"] = max(0, min(cap, int(pb)))
    await save_all(data)
    return p["shield"]

async def damage(user_id: int | str, amount: int) -> Dict[str, int]:
    """Inflige des dégâts → d’abord PB puis PV. Retourne dict: {'absorbed':x,'lost':y}."""
    if amount <= 0:
        return {"absorbed": 0, "lost": 0}
    data = await load_all()
    p = data["players"].setdefault(str(user_id), _default_player())
    pb = int(p.get("shield", 0))
    hp = int(p.get("hp", 100))
    absorbed = min(pb, amount)
    pb -= absorbed
    rest = amount - absorbed
    lost = min(hp, rest)
    hp -= lost
    p["shield"] = pb
    p["hp"] = hp
    await save_all(data)
    return {"absorbed": absorbed, "lost": lost}

async def heal(user_id: int | str, amount: int) -> int:
    """Soigne les PV (cap à 100). Retourne PV réellement rendus."""
    if amount <= 0:
        return 0
    data = await load_all()
    p = data["players"].setdefault(str(user_id), _default_player())
    hp = int(p.get("hp", 100))
    healed = min(100 - hp, amount)
    if healed > 0:
        p["hp"] = hp + healed
        await save_all(data)
    return healed

async def revive_full(user_id: int | str) -> None:
    data = await load_all()
    p = data["players"].setdefault(str(user_id), _default_player())
    p["hp"] = 100
    p["shield"] = 0
    # (on peut aussi vider les effets, cf. below)
    await save_all(data)

# ==== Stats (dégâts/heal/kills/morts) ====
async def add_damage_stat(user_id: int | str, amount: int) -> None:
    if amount <= 0: return
    data = await load_all()
    p = data["players"].setdefault(str(user_id), _default_player())
    p["stats"]["damage"] = int(p["stats"].get("damage", 0)) + amount
    await save_all(data, auto_backup=False)

async def add_heal_stat(user_id: int | str, amount: int) -> None:
    if amount <= 0: return
    data = await load_all()
    p = data["players"].setdefault(str(user_id), _default_player())
    p["stats"]["healing"] = int(p["stats"].get("healing", 0)) + amount
    await save_all(data, auto_backup=False)

async def add_kill(user_id: int | str) -> None:
    data = await load_all()
    p = data["players"].setdefault(str(user_id), _default_player())
    p["stats"]["kills"] = int(p["stats"].get("kills", 0)) + 1
    await save_all(data, auto_backup=False)

async def add_death(user_id: int | str) -> None:
    data = await load_all()
    p = data["players"].setdefault(str(user_id), _default_player())
    p["stats"]["deaths"] = int(p["stats"].get("deaths", 0)) + 1
    await save_all(data, auto_backup=False)

# ==== Inventaire ====
async def inv_add(user_id: int | str, emoji: str, qty: int = 1) -> int:
    if qty <= 0: return await inv_get(user_id, emoji)
    data = await load_all()
    p = data["players"].setdefault(str(user_id), _default_player())
    inv = p["inventory"]
    inv[emoji] = int(inv.get(emoji, 0)) + qty
    await save_all(data)
    return inv[emoji]

async def inv_remove(user_id: int | str, emoji: str, qty: int = 1) -> bool:
    if qty <= 0: return False
    data = await load_all()
    p = data["players"].setdefault(str(user_id), _default_player())
    inv = p["inventory"]
    have = int(inv.get(emoji, 0))
    if have < qty:
        return False
    left = have - qty
    if left <= 0:
        inv.pop(emoji, None)
    else:
        inv[emoji] = left
    await save_all(data)
    return True

async def inv_get(user_id: int | str, emoji: str) -> int:
    p = await get_player(user_id)
    return int(p.get("inventory", {}).get(emoji, 0))

async def inv_all(user_id: int | str) -> List[Tuple[str, int]]:
    p = await get_player(user_id)
    inv = p.get("inventory", {})
    return sorted([(k, int(v)) for k, v in inv.items()], key=lambda x: x[0])

# ==== Effets / DOT / Buffs ====
async def effects_get(user_id: int | str) -> Dict[str, Any]:
    p = await get_player(user_id)
    eff = p.get("effects", {})
    return eff if isinstance(eff, dict) else {}

async def effect_set(user_id: int | str, eff_type: str, payload: Dict[str, Any]) -> None:
    """payload peut contenir: value, interval, end_ts, next_ts, source_id, meta…"""
    data = await load_all()
    p = data["players"].setdefault(str(user_id), _default_player())
    eff = p["effects"]
    eff[eff_type] = dict(payload or {})
    await save_all(data)

async def effect_remove(user_id: int | str, eff_type: str) -> None:
    data = await load_all()
    p = data["players"].setdefault(str(user_id), _default_player())
    eff = p["effects"]
    eff.pop(eff_type, None)
    await save_all(data)

async def effects_clear(user_id: int | str) -> None:
    data = await load_all()
    p = data["players"].setdefault(str(user_id), _default_player())
    p["effects"] = {}
    await save_all(data)

# ==== Cooldowns (daily, attack, etc.) ====
async def cd_get(user_id: int | str, key: str) -> int:
    p = await get_player(user_id)
    cds = p.get("cooldowns", {})
    return int(cds.get(key, 0))

async def cd_set(user_id: int | str, key: str, ts: int) -> None:
    data = await load_all()
    p = data["players"].setdefault(str(user_id), _default_player())
    cds = p["cooldowns"]
    cds[key] = int(ts)
    await save_all(data)

# ==== Config serveur ====
async def guild_cfg_get(guild_id: int | str) -> Dict[str, Any]:
    data = await load_all()
    g = data["config"]["guilds"].setdefault(str(guild_id), {})
    return g

async def guild_cfg_update(guild_id: int | str, patch: Dict[str, Any]) -> Dict[str, Any]:
    data = await load_all()
    g = data["config"]["guilds"].setdefault(str(guild_id), {})
    g.update(patch or {})
    await save_all(data)
    return g

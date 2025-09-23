# data/storage.py
from __future__ import annotations

import os
import io
import json
import time
import asyncio
from typing import Any, Dict, Optional, List, Tuple
from datetime import datetime

# ╔══════════════════════════════════════════════════════════════════╗
# ║                 EMPLACEMENT PERSISTANT & BACKUPS                 ║
# ╚══════════════════════════════════════════════════════════════════╝
PERSISTENT_PATH = "/persistent"
DATA_FILE = os.path.join(PERSISTENT_PATH, "data.json")

BACKUP_DIR = os.path.join(PERSISTENT_PATH, "backups")
AUTO_BACKUP_DIR = os.path.join(PERSISTENT_PATH, "auto_backups")

MAX_BACKUPS = 20
MAX_AUTO_BACKUPS = 30
AUTO_BACKUP_MIN_SPACING_SEC = 300  # 5 min mini entre deux autobackups

_lock = asyncio.Lock()
_last_auto_backup_ts: float = 0.0


# ── Helper: chemin SQLite persistant ─────────────────────────────────────────
def get_sqlite_path(db_name: str = "gotvalis.sqlite3") -> str:
    """
    Renvoie un chemin de DB qui survit aux redémarrages.
    Priorité à la variable d'env GOTVALIS_DB, sinon utilise /persistent.
    """
    env = os.getenv("GOTVALIS_DB")
    if env:
        try:
            d = os.path.dirname(env)
            if d:
                os.makedirs(d, exist_ok=True)
        except Exception:
            pass
        return env

    base = PERSISTENT_PATH  # défini ci-dessus
    try:
        os.makedirs(base, exist_ok=True)
    except Exception:
        pass
    return os.path.join(base, db_name)


# ╔══════════════════════════════════════════════════════════════════╗
# ║                 STRUCTURE EN MÉMOIRE (GLOBAL STATE)              ║
# ╚══════════════════════════════════════════════════════════════════╝
# 1) Ancienne structure "players" que tes anciens cogs utilisaient
_players: Dict[str, Dict[str, Any]] = {}

# 2) Nouvelles maps "globales" attendues par /daily et d'autres cogs
# tickets[guild_id][user_id] -> int
tickets: Dict[str, Dict[str, int]] = {}
# cooldowns["daily"][guild_id][user_id] -> ts
cooldowns: Dict[str, Dict[str, Dict[str, int]]] = {}
# streaks[guild_id][user_id] -> {"count": int}
streaks: Dict[str, Dict[str, Dict[str, int]]] = {}
# leaderboard_channels[guild_id] -> channel_id
leaderboard_channels: Dict[str, int] = {}

# config général: config["guilds"][guild_id] -> {...}
_config: Dict[str, Any] = {"guilds": {}}

# meta
_meta: Dict[str, Any] = {"last_backup": None, "version": 2, "updated_at": int(time.time())}


# ╔══════════════════════════════════════════════════════════════════╗
# ║                         HELPERS FICHIERS                         ║
# ╚══════════════════════════════════════════════════════════════════╝
def _ensure_dirs() -> None:
    os.makedirs(PERSISTENT_PATH, exist_ok=True)
    os.makedirs(BACKUP_DIR, exist_ok=True)
    os.makedirs(AUTO_BACKUP_DIR, exist_ok=True)

def _timestamp() -> str:
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


# ╔══════════════════════════════════════════════════════════════════╗
# ║                       SNAPSHOT <-> GLOBALS                       ║
# ╚══════════════════════════════════════════════════════════════════╝
def _default_root() -> Dict[str, Any]:
    return {
        "players": {},                 # ancienne arborescence joueurs
        "config": {"guilds": {}},      # config serveur
        "meta": {"last_backup": None, "version": 2, "updated_at": int(time.time())},

        # nouvelles maps globales (compat /daily)
        "tickets": {},                 # {gid: {uid: int}}
        "cooldowns": {},               # {"daily": {gid: {uid: ts}}, ...}
        "streaks": {},                 # {gid: {uid: {"count": int}}}
        "leaderboard_channels": {},    # {gid: channel_id}
    }

def _default_player() -> Dict[str, Any]:
    return {
        "hp": 100,
        "shield": 0,
        "coins": 0,
        "coins_total": 0,
        "tickets": 0,
        "equipped_character": None,
        "stats": {"damage": 0, "healing": 0, "kills": 0, "deaths": 0},
        "inventory": {},     # {emoji -> qty}
        "effects": {},       # {eff_type: {...}}
        "cooldowns": {},     # ex: {"daily": ts}
    }

def _globals_to_snapshot() -> Dict[str, Any]:
    return {
        "players": _players,
        "config": _config,
        "meta": {"last_backup": _meta.get("last_backup"),
                 "version": 2,
                 "updated_at": int(time.time())},
        "tickets": tickets,
        "cooldowns": cooldowns,
        "streaks": streaks,
        "leaderboard_channels": leaderboard_channels,
    }

def _load_into_globals(data: Dict[str, Any]) -> None:
    global _players, _config, _meta, tickets, cooldowns, streaks, leaderboard_channels
    if not isinstance(data, dict):
        data = _default_root()

    _players = data.get("players") or {}
    if not isinstance(_players, dict):
        _players = {}

    _config = data.get("config") or {"guilds": {}}
    if not isinstance(_config, dict):
        _config = {"guilds": {}}
    _config.setdefault("guilds", {})

    tickets = data.get("tickets") or {}
    if not isinstance(tickets, dict):
        tickets = {}

    cooldowns = data.get("cooldowns") or {}
    if not isinstance(cooldowns, dict):
        cooldowns = {}

    streaks = data.get("streaks") or {}
    if not isinstance(streaks, dict):
        streaks = {}

    leaderboard_channels = data.get("leaderboard_channels") or {}
    if not isinstance(leaderboard_channels, dict):
        leaderboard_channels = {}

    _meta = data.get("meta") or {"last_backup": None}
    if not isinstance(_meta, dict):
        _meta = {"last_backup": None}
    _meta["version"] = 2
    _meta["updated_at"] = int(time.time())


# ╔══════════════════════════════════════════════════════════════════╗
# ║                            CORE I/O                              ║
# ╚══════════════════════════════════════════════════════════════════╝
async def init_storage() -> None:
    """À appeler au démarrage (main.py)."""
    _ensure_dirs()
    async with _lock:
        if not os.path.exists(DATA_FILE):
            _atomic_write_json(DATA_FILE, _default_root())
        # toujours recharger en mémoire
        try:
            with io.open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = _default_root()
        _load_into_globals(data)

async def load_all() -> Dict[str, Any]:
    """Snapshot complet (async) — utilisé par vieux helpers."""
    async with _lock:
        _ensure_dirs()
        if not os.path.exists(DATA_FILE):
            data = _default_root()
            _atomic_write_json(DATA_FILE, data)
            _load_into_globals(data)
            return data
        try:
            with io.open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                data = _default_root()
        except Exception:
            data = _default_root()
            _atomic_write_json(DATA_FILE, data)
        _load_into_globals(data)
        return data

async def save_all(data: Dict[str, Any], *, auto_backup: bool = True) -> None:
    """Écrit un snapshot fourni (async)."""
    async with _lock:
        _ensure_dirs()
        # met aussi à jour les globals pour rester cohérent
        _load_into_globals(data)
        _atomic_write_json(DATA_FILE, _globals_to_snapshot())
        if auto_backup:
            await _auto_backup()


# ╔══════════════════════════════════════════════════════════════════╗
# ║                   WRAPPERS SYNCHRONES (compat)                   ║
# ╚══════════════════════════════════════════════════════════════════╝
def load_data() -> Dict[str, Any]:
    """Lecture synchrone (utilisée par /admin pour afficher un aperçu)."""
    _ensure_dirs()
    try:
        if not os.path.exists(DATA_FILE):
            snap = _default_root()
            _atomic_write_json(DATA_FILE, snap)
            _load_into_globals(snap)
            return snap
        with io.open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            data = _default_root()
    except Exception:
        data = _default_root()
    _load_into_globals(data)
    return data

def save_data() -> None:
    """Écriture synchrone — sérialise l’état courant des globals."""
    _ensure_dirs()
    snap = _globals_to_snapshot()
    try:
        _atomic_write_json(DATA_FILE, snap)
    except Exception:
        pass


# ╔══════════════════════════════════════════════════════════════════╗
# ║                             BACKUPS                              ║
# ╚══════════════════════════════════════════════════════════════════╝
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
        # maj meta
        data["meta"]["last_backup"] = stamp
        _atomic_write_json(DATA_FILE, data)
        return path

async def _auto_backup() -> None:
    global _last_auto_backup_ts
    now = time.time()
    if (now - _last_auto_backup_ts) < AUTO_BACKUP_MIN_SPACING_SEC:
        return
    try:
        data = await load_all()
        stamp = _timestamp()
        path = os.path.join(AUTO_BACKUP_DIR, f"auto_{stamp}.json")
        _atomic_write_json(path, data)
        _rotate(AUTO_BACKUP_DIR, MAX_AUTO_BACKUPS)
        _last_auto_backup_ts = now
    except Exception:
        pass


# ╔══════════════════════════════════════════════════════════════════╗
# ║                     HELPERS JOUEURS (ANCIENS)                    ║
# ╚══════════════════════════════════════════════════════════════════╝
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

# Coins / Tickets (anciens, par joueur)
async def add_coins(user_id: int | str, amount: int) -> int:
    if amount <= 0: return await get_coins(user_id)
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

async def add_tickets_player(user_id: int | str, qty: int) -> int:
    """Ancien compteur de tickets par joueur (distinct des tickets /daily par guilde)."""
    if qty <= 0: return await get_tickets_player(user_id)
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

async def get_tickets_player(user_id: int | str) -> int:
    p = await get_player(user_id)
    return int(p.get("tickets", 0))

# PV / PB
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
    cap = 20  # cap par défaut (peut être modifié ailleurs)
    data = await load_all()
    p = data["players"].setdefault(str(user_id), _default_player())
    p["shield"] = max(0, min(cap, int(pb)))
    await save_all(data)
    return p["shield"]

async def damage(user_id: int | str, amount: int) -> Dict[str, int]:
    """Inflige des dégâts → d’abord PB puis PV."""
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
    await save_all(data)

# Stats
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

# Inventaire
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

# Effets
async def effects_get(user_id: int | str) -> Dict[str, Any]:
    p = await get_player(user_id)
    eff = p.get("effects", {})
    return eff if isinstance(eff, dict) else {}

async def effect_set(user_id: int | str, eff_type: str, payload: Dict[str, Any]) -> None:
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

# Cooldowns (par joueur)
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


# ╔══════════════════════════════════════════════════════════════════╗
# ║                        CONFIG SERVEUR (guild)                    ║
# ╚══════════════════════════════════════════════════════════════════╝
async def guild_cfg_get(guild_id: int | str) -> Dict[str, Any]:
    data = await load_all()
    g = data["config"]["guilds"].setdefault(str(guild_id), {})
    await save_all(data, auto_backup=False)
    return g

async def guild_cfg_update(guild_id: int | str, patch: Dict[str, Any]) -> Dict[str, Any]:
    data = await load_all()
    g = data["config"]["guilds"].setdefault(str(guild_id), {})
    g.update(patch or {})
    await save_all(data)
    return g

# Helpers pratiques pour les cogs leaderboard (synchros, utilisés parfois)
def set_leaderboard_channel(guild_id: int, channel_id: Optional[int]) -> None:
    gid = str(guild_id)
    if channel_id is None:
        leaderboard_channels.pop(gid, None)
    else:
        leaderboard_channels[gid] = int(channel_id)
    save_data()

def get_leaderboard_channel(guild_id: int) -> Optional[int]:
    val = leaderboard_channels.get(str(guild_id))
    try:
        return int(val) if val is not None else None
    except Exception:
        return None


# ╔══════════════════════════════════════════════════════════════════╗
# ║                              EXPORTS                             ║
# ╚══════════════════════════════════════════════════════════════════╝
__all__ = [
    # chemins
    "PERSISTENT_PATH", "DATA_FILE", "BACKUP_DIR", "AUTO_BACKUP_DIR", "get_sqlite_path",
    # globals exposés (pour /daily)
    "tickets", "cooldowns", "streaks", "leaderboard_channels",
    # init/io
    "init_storage", "load_all", "save_all", "load_data", "save_data",
    # backups
    "backup_now",
    # anciens helpers joueurs
    "ensure_player", "get_player", "set_equipped_character",
    "add_coins", "spend_coins", "get_coins",
    "add_tickets_player", "use_ticket", "get_tickets_player",
    "get_hp", "get_shield", "set_hp", "set_shield",
    "damage", "heal", "revive_full",
    "add_damage_stat", "add_heal_stat", "add_kill", "add_death",
    "inv_add", "inv_remove", "inv_get", "inv_all",
    "effects_get", "effect_set", "effect_remove", "effects_clear",
    "cd_get", "cd_set",
    # config serveur
    "guild_cfg_get", "guild_cfg_update",
    "set_leaderboard_channel", "get_leaderboard_channel",
]

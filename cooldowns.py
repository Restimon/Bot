# cooldowns.py
# Gestion centralisée des cooldowns (persistés dans data.cooldowns)

import time
from datetime import datetime, timezone

# On utilise l’objet partagé/persisté dans data.py
from data import cooldowns as _CD_STORE, sauvegarder

# (action -> dict par guilde)
# _CD_STORE = {
#   "attack": { "<guild_id>": { <key>: last_ts, ... } },
#   "heal":   { "<guild_id>": { <key>: last_ts, ... } },
# }

# Durées par défaut (secondes)
ATTACK_COOLDOWN = 120
HEAL_COOLDOWN   = 180

def _now() -> float:
    return time.time()

def _action_store(action: str) -> dict:
    """Retourne la map persistée pour une action ('attack' | 'heal')."""
    if action not in _CD_STORE:
        _CD_STORE[action] = {}
    return _CD_STORE[action]

def _guild_map(action: str, guild_id: str) -> dict:
    store = _action_store(action)
    gid = str(guild_id)
    if gid not in store:
        store[gid] = {}
    return store[gid]

def _key_norm(key):
    """Les clés peuvent être str ou tuple ; on normalise sans les transformer de type."""
    return tuple(key) if isinstance(key, tuple) else key

def _base_duration(action: str) -> int:
    return ATTACK_COOLDOWN if action == "attack" else HEAL_COOLDOWN

# ---------------------------------------------------------------------
# API principale
# ---------------------------------------------------------------------

def is_on_cooldown(guild_id: str, key, action: str) -> tuple[bool, int]:
    """
    Vérifie si une action est en cooldown.
    Renvoie (True/False, remaining_seconds).
    - guild_id: str
    - key: user_id OU tuple (user_id, target_id) selon le cas
    - action: "attack" | "heal"
    """
    now = _now()
    gmap = _guild_map(action, guild_id)
    last_ts = gmap.get(_key_norm(key))
    if last_ts is None:
        return False, 0

    cd = _base_duration(action)
    remaining = int(last_ts + cd - now)
    if remaining > 0:
        return True, remaining
    return False, 0

def set_cooldown(guild_id: str, key, action: str, duration: int | None = None) -> None:
    """
    Démarre (ou ajuste) le cooldown :
    - duration=None : enregistre le timestamp courant comme début de cooldown standard
    - duration=int  : force un "remaining" personnalisé (ex: pour passifs)
    """
    now = _now()
    cd = _base_duration(action)
    # Si duration est fourni, on recalcule un last_ts tel que (last_ts + cd) = now + duration
    last_ts = now if duration is None else (now - cd + int(duration))

    gmap = _guild_map(action, guild_id)
    gmap[_key_norm(key)] = last_ts

    # Persistance discrète
    try:
        sauvegarder()
    except Exception:
        pass

def get_remaining(guild_id: str, key, action: str) -> int:
    """Renvoie le temps restant (s) du cooldown, ou 0 si prêt."""
    on_cd, rem = is_on_cooldown(guild_id, key, action)
    return rem if on_cd else 0

def clear_cooldown(guild_id: str, key, action: str) -> None:
    """Supprime le cooldown pour une clé (utilitaire)."""
    gmap = _guild_map(action, guild_id)
    gmap.pop(_key_norm(key), None)
    try:
        sauvegarder()
    except Exception:
        pass

# ---------------------------------------------------------------------
# Limites quotidiennes (non persistées — quotas "par jour")
# ---------------------------------------------------------------------

_daily_counters: dict[str, tuple[int, str]] = {}  # { "guild:user:key": (count, yyyy-mm-dd-UTC) }

def daily_limit(guild_id: str, user_id: str, key: str, limit: int = 1) -> bool:
    """
    Incrémente et vérifie un quota quotidien.
    Retourne True si l'action est AUTORISÉE (compteur < limit) et incrémente le compteur.
    Retourne False si la limite quotidienne est déjà atteinte.
    Reset automatique chaque jour UTC.
    """
    gid = str(guild_id)
    uid = str(user_id)
    k = f"{gid}:{uid}:{key}"

    today = datetime.now(timezone.utc).date().isoformat()
    count, day = _daily_counters.get(k, (0, today))

    if day != today:
        count = 0
        day = today

    if count < max(0, int(limit)):
        count += 1
        _daily_counters[k] = (count, day)
        return True

    _daily_counters[k] = (count, day)
    return False

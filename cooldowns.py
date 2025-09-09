import time
from datetime import datetime, timezone

cooldowns = {
    "attack": {},  # cooldowns["attack"][guild_id][user_id]
    "heal": {}     # cooldowns["heal"][(guild_id, user_id, target_id)]
}

ATTACK_COOLDOWN = 120
HEAL_COOLDOWN = 180

# === Cooldowns classiques (attaque / soin) ===

def is_on_cooldown(guild_id, key, action):
    now = time.time()
    cd_dict = cooldowns[action].get(guild_id, {})
    
    # Récupérer la dernière utilisation
    value = cd_dict.get(tuple(key) if isinstance(key, tuple) else key)

    if value is None:
        return False, 0

    base_cd = ATTACK_COOLDOWN if action == "attack" else HEAL_COOLDOWN
    remaining = int(value + base_cd - now)
    return remaining > 0, remaining

def set_cooldown(guild_id, key, action, duration=None):
    now = time.time()
    base_cd = ATTACK_COOLDOWN if action == "attack" else HEAL_COOLDOWN

    if duration is None:
        cd_time = now
    else:
        cd_time = now - base_cd + duration

    cd_dict = cooldowns[action].setdefault(guild_id, {})
    cd_dict[tuple(key) if isinstance(key, tuple) else key] = cd_time

# === Limites quotidiennes (passifs / tirages spéciaux, etc.) ===

_daily_counters = {}  # { "guild:user:key": (count, jour) }

def daily_limit(guild_id, user_id, key: str, limit: int = 1) -> bool:
    """
    Incrémente et vérifie un quota quotidien.
    Retourne True si l'action est AUTORISÉE (compteur < limit) et incrémente le compteur.
    Retourne False si la limite quotidienne est déjà atteinte.
    Le reset se fait chaque jour UTC.
    """
    gid = str(guild_id)
    uid = str(user_id)
    k = f"{gid}:{uid}:{key}"

    today = datetime.now(timezone.utc).date().isoformat()

    count, day = _daily_counters.get(k, (0, today))
    if day != today:
        # nouveau jour → reset
        count = 0
        day = today

    if count < limit:
        count += 1
        _daily_counters[k] = (count, day)
        return True

    # Limite atteinte
    _daily_counters[k] = (count, day)
    return False

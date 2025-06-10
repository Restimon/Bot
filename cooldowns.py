import time

cooldowns = {
    "attack": {},  # cooldowns["attack"][guild_id][user_id]
    "heal": {}     # cooldowns["heal"][(guild_id, user_id, target_id)]
}

ATTACK_COOLDOWN = 120
HEAL_COOLDOWN = 180

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

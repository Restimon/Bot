cooldowns = {
    "attack": {},  # cooldowns["attack"][guild_id][user_id]
    "heal": {}     # cooldowns["heal"][(guild_id, user_id, target_id)]
}

ATTACK_COOLDOWN = 120
HEAL_COOLDOWN = 180

import time

def is_on_cooldown(guild_id, key, action):
    now = time.time()
    cd = cooldowns[action].get(guild_id, {})
    if isinstance(key, tuple):
        value = cd.get(tuple(key))
    else:
        value = cd.get(key)
    if value is None:
        return False, 0
    remaining = int(value + (ATTACK_COOLDOWN if action == "attack" else HEAL_COOLDOWN) - now)
    return remaining > 0, remaining

def set_cooldown(guild_id, key, action, duration=None):
    now = time.time()
    cd_time = now if duration is None else now - (ATTACK_COOLDOWN if action == "attack" else HEAL_COOLDOWN) + duration

    if isinstance(key, tuple):
        cooldowns[action].setdefault(guild_id, {})[tuple(key)] = cd_time
    else:
        cooldowns[action].setdefault(guild_id, {})[key] = cd_time

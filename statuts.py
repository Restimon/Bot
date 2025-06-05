import time
from data import virus_status, poison_status, infection_status, regeneration_status

TICK_DURATION = 1800  # 30 minutes

def appliquer_poison(guild_id, user_id, channel_id, source_id=None):
    now = time.time()
    poison_status.setdefault(guild_id, {})[user_id] = {
        "start": now,
        "duration": 3 * 3600,
        "next_tick": now + TICK_DURATION,
        "source": source_id,
        "channel_id": channel_id
    }

def appliquer_infection(guild_id, user_id, channel_id, source_id=None):
    now = time.time()
    infection_status.setdefault(guild_id, {})[user_id] = {
        "start": now,
        "duration": 3 * 3600,
        "next_tick": now + TICK_DURATION,
        "source": source_id,
        "channel_id": channel_id
    }

def appliquer_virus(guild_id, user_id, channel_id, source_id=None):
    now = time.time()
    virus_status.setdefault(guild_id, {})[user_id] = {
        "start": now,
        "duration": 6 * 3600,
        "next_tick": now + TICK_DURATION,
        "source": source_id,
        "channel_id": channel_id
    }

def appliquer_regen(guild_id, user_id, channel_id, source_id=None):
    now = time.time()
    regeneration_status.setdefault(guild_id, {})[user_id] = {
        "start": now,
        "duration": 3 * 3600,
        "next_tick": now + TICK_DURATION,
        "source": source_id,
        "channel_id": channel_id
    }

def supprimer_tous_statuts(guild_id, user_id):
    for statut_dict in [virus_status, poison_status, infection_status, regeneration_status]:
        if guild_id in statut_dict and user_id in statut_dict[guild_id]:
            del statut_dict[guild_id][user_id]

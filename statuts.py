import time
from data import virus_status, poison_status, infection_status, regeneration_status

def appliquer_poison(guild_id, user_id, channel_id, source_id=None):
    poison_status.setdefault(guild_id, {})[user_id] = {
        "start": time.time(),
        "duration": 3 * 3600,
        "last_tick": 0,
        "source": source_id,
        "channel_id": channel_id
    }

def appliquer_infection(guild_id, user_id, channel_id, source_id=None):
    infection_status.setdefault(guild_id, {})[user_id] = {
        "start": time.time(),
        "duration": 3 * 3600,
        "last_tick": 0,
        "source": source_id,
        "channel_id": channel_id
    }

def appliquer_virus(guild_id, user_id, channel_id, source_id=None):
    virus_status.setdefault(guild_id, {})[user_id] = {
        "start": time.time(),
        "duration": 6 * 3600,
        "last_tick": 0,
        "source": source_id,
        "channel_id": channel_id
    }

def appliquer_regen(guild_id, user_id, channel_id, source_id=None):
    regeneration_status.setdefault(guild_id, {})[user_id] = {
        "start": time.time(),
        "duration": 3 * 3600,
        "last_tick": 0,
        "source": source_id,
        "channel_id": channel_id
    }

def supprimer_tous_statuts(guild_id, user_id):
    for statut_dict in [virus_status, poison_status, infection_status, regeneration_status]:
        if guild_id in statut_dict and user_id in statut_dict[guild_id]:
            del statut_dict[guild_id][user_id]

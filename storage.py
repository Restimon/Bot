inventaire = {}
hp = {}
leaderboard = {}

def get_inventory(guild_id):
    return inventaire.setdefault(str(guild_id), {})

def get_hp(guild_id):
    return hp.setdefault(str(guild_id), {})

def get_leaderboard(guild_id):
    return leaderboard.setdefault(str(guild_id), {})

def get_user_data(guild_id, user_id):
    gid = str(guild_id)
    uid = str(user_id)

    inv = inventaire.setdefault(gid, {}).setdefault(uid, [])
    pv = hp.setdefault(gid, {}).setdefault(uid, 100)

    # Initialisation complète des stats avec degats, soin, kills, morts
    stats = leaderboard.setdefault(gid, {}).setdefault(uid, {
        "degats": 0,
        "soin": 0,
        "kills": 0,
        "morts": 0
    })

    # Correction éventuelle si stats existantes incomplètes
    if not isinstance(stats, dict):
        stats = {"degats": 0, "soin": 0, "kills": 0, "morts": 0}
        leaderboard[gid][uid] = stats
    else:
        for key in ("degats", "soin", "kills", "morts"):
            stats.setdefault(key, 0)

    return inv, pv, stats

def reset_guild_data(guild_id):
    gid = str(guild_id)
    inventaire[gid] = {}
    hp[gid] = {}
    leaderboard[gid] = {}

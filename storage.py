# storage.py
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
    stats = leaderboard.setdefault(gid, {}).setdefault(uid, {"degats": 0, "soin": 0})

    if not isinstance(inv, list):
        inventaire[gid][uid] = []
        inv = inventaire[gid][uid]

    if not isinstance(pv, int):
        hp[gid][uid] = 100
        pv = hp[gid][uid]

    if not isinstance(stats, dict) or "degats" not in stats or "soin" not in stats:
        leaderboard[gid][uid] = {"degats": 0, "soin": 0}
        stats = leaderboard[gid][uid]

    return inv, pv, stats

def reset_guild_data(guild_id):
    gid = str(guild_id)
    inventaire[gid] = {}
    hp[gid] = {}
    leaderboard[gid] = {}

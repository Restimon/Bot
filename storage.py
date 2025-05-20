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
    uid = str(user_id)
    g = str(guild_id)
    inv = get_inventory(g).setdefault(uid, [])
    pv = get_hp(g).setdefault(uid, 100)
    stats = get_leaderboard(g).setdefault(uid, {"degats": 0, "soin": 0})
    return inv, pv, stats

def reset_guild_data(guild_id):
    gid = str(guild_id)
    inventaire[gid] = {}
    hp[gid] = {}
    leaderboard[gid] = {}

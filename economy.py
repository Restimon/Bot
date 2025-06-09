gotcoins_stats = {}
gotcoins_balance = {}

def get_balance(guild_id, user_id):
    return gotcoins_balance.setdefault(guild_id, {}).get(user_id, 0)

def add_gotcoins(guild_id, user_id, amount):
    gotcoins_balance.setdefault(guild_id, {})
    gotcoins_balance[guild_id][user_id] = get_balance(guild_id, user_id) + amount

def remove_gotcoins(guild_id, user_id, amount):
    gotcoins_balance.setdefault(guild_id, {})
    gotcoins_balance[guild_id][user_id] = max(0, get_balance(guild_id, user_id) - amount)

def init_gotcoins_stats(guild_id, user_id):
    gotcoins_stats.setdefault(guild_id, {}).setdefault(user_id, {
        "degats": 0, "soin": 0, "kills": 0, "morts": 0, "autre": 0
    })

import random
from data import sauvegarder
from passifs import appliquer_passif  # ✅ Import pour gérer les passifs

gotcoins_stats = {}   # {guild_id: {user_id: {"degats": X, "soin": X, "kills": X, "morts": X, "autre": X, "achats": X}}}
gotcoins_balance = {} # {guild_id: {user_id: balance_int}}

DEFAULT_STATS = {
    "degats": 0,
    "soin": 0,
    "kills": 0,
    "morts": 0,
    "autre": 0,
    "achats": 0
}

def init_gotcoins_stats(guild_id, user_id):
    gotcoins_stats.setdefault(guild_id, {}).setdefault(user_id, DEFAULT_STATS.copy())
    gotcoins_balance.setdefault(guild_id, {}).setdefault(user_id, 0)

def get_balance(guild_id, user_id):
    init_gotcoins_stats(guild_id, user_id)
    return gotcoins_balance[guild_id][user_id]

def can_afford(guild_id, user_id, amount):
    if amount <= 0:
        return True
    init_gotcoins_stats(guild_id, user_id)
    return gotcoins_balance[guild_id][user_id] >= amount

def add_gotcoins(guild_id, user_id, amount, category="autre"):
    if amount <= 0:
        return
    init_gotcoins_stats(guild_id, user_id)
    gotcoins_balance[guild_id][user_id] += amount
    gotcoins_stats[guild_id][user_id].setdefault(category, 0)
    gotcoins_stats[guild_id][user_id][category] += amount
    sauvegarder()

# ✅ Utiliser cette fonction si tu veux déclencher les passifs de type "gain_gotcoins"
def add_gotcoins_with_passif(guild_id, user_id, amount, category="autre"):
    add_gotcoins(guild_id, user_id, amount, category)
    appliquer_passif(user_id, "gain_gotcoins", {
        "guild_id": guild_id,
        "user_id": user_id,
        "category": category
    })

def remove_gotcoins(guild_id, user_id, amount, log_as_purchase=True):
    if amount <= 0:
        return
    init_gotcoins_stats(guild_id, user_id)
    current_balance = gotcoins_balance[guild_id][user_id]
    gotcoins_balance[guild_id][user_id] = max(0, current_balance - amount)
    if log_as_purchase:
        gotcoins_stats[guild_id][user_id]["achats"] += amount
    sauvegarder()

def get_gotcoins_stats(guild_id, user_id):
    init_gotcoins_stats(guild_id, user_id)
    return gotcoins_stats[guild_id][user_id]

def get_leaderboard_ranking(guild_id):
    balances = gotcoins_balance.get(guild_id, {})
    return sorted(balances.items(), key=lambda x: x[1], reverse=True)

def get_total_gotcoins_earned(guild_id, user_id):
    init_gotcoins_stats(guild_id, user_id)
    stats = gotcoins_stats[guild_id][user_id]
    total = sum(v for k, v in stats.items() if k != "achats")
    return max(total, gotcoins_balance[guild_id][user_id])

def compute_message_gains(message_content):
    length = len(message_content.strip())
    if length == 0:
        return 0
    elif length < 20:
        return 1
    elif length < 50:
        return 2
    elif length < 100:
        return 3
    elif length < 200:
        return 4
    else:
        return 5

def compute_voice_gains(minutes_in_voice):
    num_chunks = minutes_in_voice // 30
    return sum(random.randint(1, 4) for _ in range(num_chunks))

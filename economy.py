import random
from passifs import appliquer_passif  # ✅ Gestion des passifs

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

    # ✅ Import local pour éviter circular import
    from data import sauvegarder
    sauvegarder()

def add_gotcoins_with_passif(guild_id, user_id, amount, category="autre"):
    if amount <= 0:
        return

    # 1. Gain normal
    add_gotcoins(guild_id, user_id, amount, category)

    # 2. Vérifie les passifs de gain
    result = appliquer_passif(user_id, "gain_gotcoins", {
        "guild_id": guild_id,
        "user_id": user_id,
        "category": category,
        "montant": amount
    })
    if result and "gotcoins_bonus" in result:
        bonus = result["gotcoins_bonus"]
        add_gotcoins(guild_id, user_id, bonus, category)
        print(f"💠 Bonus passif appliqué : +{bonus} GotCoins pour {user_id}")

def remove_gotcoins(guild_id, user_id, amount, log_as_purchase=True):
    if amount <= 0:
        return
    init_gotcoins_stats(guild_id, user_id)
    current_balance = gotcoins_balance[guild_id][user_id]
    gotcoins_balance[guild_id][user_id] = max(0, current_balance - amount)
    if log_as_purchase:
        gotcoins_stats[guild_id][user_id]["achats"] += amount

    # ✅ Import local pour éviter circular import
    from data import sauvegarder
    sauvegarder()

def get_gotcoins_stats(guild_id_

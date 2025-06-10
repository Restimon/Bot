gotcoins_stats = {}   # {guild_id: {user_id: {"degats": X, "soin": X, "kills": X, "morts": X, "autre": X, "achats": X}}}
gotcoins_balance = {} # {guild_id: {user_id: balance_int}}

# Valeurs par défaut pour les stats
DEFAULT_STATS = {
    "degats": 0,
    "soin": 0,
    "kills": 0,
    "morts": 0,
    "autre": 0,
    "achats": 0
}

# Initialisation des stats d'un joueur
def init_gotcoins_stats(guild_id, user_id):
    gotcoins_stats.setdefault(guild_id, {}).setdefault(user_id, DEFAULT_STATS.copy())
    gotcoins_balance.setdefault(guild_id, {}).setdefault(user_id, 0)

# Récupérer la balance actuelle
def get_balance(guild_id, user_id):
    init_gotcoins_stats(guild_id, user_id)
    return gotcoins_balance[guild_id][user_id]

# Vérifie si le joueur a assez de GotCoins
def can_afford(guild_id, user_id, amount):
    if amount <= 0:
        return True
    init_gotcoins_stats(guild_id, user_id)
    return gotcoins_balance[guild_id][user_id] >= amount

# Ajouter des GotCoins
def add_gotcoins(guild_id, user_id, amount, category="autre"):
    from data import sauvegarder
    if amount <= 0:
        return
    init_gotcoins_stats(guild_id, user_id)

    gotcoins_balance[guild_id][user_id] += amount
    gotcoins_stats[guild_id][user_id][category] += amount

    sauvegarder()

# Retirer des GotCoins
def remove_gotcoins(guild_id, user_id, amount, log_as_purchase=True):
    from data import sauvegarder
    if amount <= 0:
        return
    init_gotcoins_stats(guild_id, user_id)

    current_balance = gotcoins_balance[guild_id][user_id]
    new_balance = max(0, current_balance - amount)
    gotcoins_balance[guild_id][user_id] = new_balance

    if log_as_purchase:
        gotcoins_stats[guild_id][user_id]["achats"] += amount

    sauvegarder()

# Retourne les stats complètes d'un joueur
def get_gotcoins_stats(guild_id, user_id):
    init_gotcoins_stats(guild_id, user_id)
    return gotcoins_stats[guild_id][user_id]

# Retourne le leaderboard global
def get_leaderboard_ranking(guild_id):
    balances = gotcoins_balance.get(guild_id, {})
    sorted_balances = sorted(balances.items(), key=lambda x: x[1], reverse=True)
    return sorted_balances

# Retourne le total de GotCoins gagnés (hors achats)
def get_total_gotcoins_earned(guild_id, user_id):
    init_gotcoins_stats(guild_id, user_id)
    stats = gotcoins_stats[guild_id][user_id]
    total = sum(v for k, v in stats.items() if k != "achats")
    return total

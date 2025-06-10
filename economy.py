from data import sauvegarder

# Données économiques par serveur → à sauvegarder
gotcoins_stats = {}   # {guild_id: {user_id: {"degats": X, "soin": X, "kills": X, "morts": X, "autre": X}}}
gotcoins_balance = {} # {guild_id: {user_id: balance_int}}

# Valeurs par défaut pour les stats
DEFAULT_STATS = {
    "degats": 0,
    "soin": 0,
    "kills": 0,
    "morts": 0,
    "autre": 0
}

# Initialisation des stats d'un joueur (à appeler au besoin)
def init_gotcoins_stats(guild_id, user_id):
    gotcoins_stats.setdefault(guild_id, {}).setdefault(user_id, DEFAULT_STATS.copy())
    gotcoins_balance.setdefault(guild_id, {}).setdefault(user_id, 0)

# Récupérer la balance actuelle (GotCoins disponibles)
def get_balance(guild_id, user_id):
    init_gotcoins_stats(guild_id, user_id)
    return gotcoins_balance[guild_id][user_id]

# Ajouter des GotCoins à la balance (+ trace dans les stats)
# → par défaut catégorie = "autre" → utilisé pour : messages, vocal, daily, ravitaillement spécial
# → combat utilise les catégories "degats", "soin", "kills", "morts"
def add_gotcoins(guild_id, user_id, amount, category="autre"):
    if amount <= 0:
        return  # sécurité inutile de faire une op pour 0 ou négatif
    init_gotcoins_stats(guild_id, user_id)

    gotcoins_balance[guild_id][user_id] += amount

    # On trace la provenance (utile pour affichage de détail)
    if category in gotcoins_stats[guild_id][user_id]:
        gotcoins_stats[guild_id][user_id][category] += amount
    else:
        gotcoins_stats[guild_id][user_id]["autre"] += amount

    sauvegarder()

# Retirer des GotCoins (ex: achats, pénalités)
# → solde final ne peut pas être < 0
def remove_gotcoins(guild_id, user_id, amount):
    if amount <= 0:
        return  # sécurité
    init_gotcoins_stats(guild_id, user_id)

    current_balance = gotcoins_balance[guild_id][user_id]
    new_balance = max(0, current_balance - amount)
    gotcoins_balance[guild_id][user_id] = new_balance

    sauvegarder()

# Retourne les stats complètes d'un joueur (utile pour affichage détaillé / debug)
# → combat + "autre"
def get_gotcoins_stats(guild_id, user_id):
    init_gotcoins_stats(guild_id, user_id)
    return gotcoins_stats[guild_id][user_id]

# Retourne le leaderboard global (trié par balance réelle)
# → utilisé pour afficher le classement de richesse
def get_leaderboard_ranking(guild_id):
    balances = gotcoins_balance.get(guild_id, {})
    sorted_balances = sorted(balances.items(), key=lambda x: x[1], reverse=True)
    return sorted_balances

# economy.py
# → système économique indépendant du leaderboard (persistant dans data.json via sauvegarder())

from data import sauvegarder

# Données économiques par serveur → à sauvegarder
gotcoins_stats = {}   # {guild_id: {user_id: {"degats": 0, "soin": 0, "kills": 0, "morts": 0, "autre": 0}}}
gotcoins_balance = {} # {guild_id: {user_id: balance_int}}

# Initialisation des stats d'un joueur (à appeler au besoin)
def init_gotcoins_stats(guild_id, user_id):
    gotcoins_stats.setdefault(guild_id, {}).setdefault(user_id, {
        "degats": 0,
        "soin": 0,
        "kills": 0,
        "morts": 0,
        "autre": 0
    })
    gotcoins_balance.setdefault(guild_id, {}).setdefault(user_id, 0)

# Récupérer la balance actuelle
def get_balance(guild_id, user_id):
    gotcoins_balance.setdefault(guild_id, {}).setdefault(user_id, 0)
    return gotcoins_balance[guild_id][user_id]

# Ajouter des GotCoins à la balance (utilise la catégorie "autre" par défaut sauf si combat)
def add_gotcoins(guild_id, user_id, amount, category="autre"):
    init_gotcoins_stats(guild_id, user_id)
    gotcoins_balance[guild_id][user_id] += amount

    # On ajoute aussi dans les stats (utile pour l'affichage leaderboard par catégorie)
    if category in gotcoins_stats[guild_id][user_id]:
        gotcoins_stats[guild_id][user_id][category] += amount
    else:
        # Si catégorie inconnue, on le met quand même dans "autre"
        gotcoins_stats[guild_id][user_id]["autre"] += amount

    sauvegarder()

# Retirer des GotCoins (ex: achats)
def remove_gotcoins(guild_id, user_id, amount):
    init_gotcoins_stats(guild_id, user_id)
    current_balance = gotcoins_balance[guild_id][user_id]
    new_balance = max(0, current_balance - amount)
    gotcoins_balance[guild_id][user_id] = new_balance

    # Ici on ne touche pas aux stats → juste la balance
    sauvegarder()

# Retourne les stats complètes d'un joueur
def get_gotcoins_stats(guild_id, user_id):
    init_gotcoins_stats(guild_id, user_id)
    return gotcoins_stats[guild_id][user_id]

# Calcul du total de GotCoins pour affichage (balance réelle + score combat "virtuel")
def compute_total_gotcoins(guild_id, user_id):
    stats = get_gotcoins_stats(guild_id, user_id)
    # Le score combat virtuel (non déductible) :
    combat_score = (
        stats.get("degats", 0)
        + stats.get("soin", 0)
        + stats.get("kills", 0) * 50
        - stats.get("morts", 0) * 25
    )
    # La balance réelle
    balance = get_balance(guild_id, user_id)

    return balance + combat_score

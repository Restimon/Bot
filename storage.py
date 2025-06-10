from economy import get_balance  # ✅ pour exposer get_user_balance proprement

inventaire = {}    # {guild_id: {user_id: [objets]}}
hp = {}            # {guild_id: {user_id: hp_value}}
leaderboard = {}   # {guild_id: {user_id: {"degats": X, "soin": X, "kills": X, "morts": X}}}

# Accès direct à l'inventaire complet d'un serveur
def get_inventory(guild_id):
    return inventaire.setdefault(str(guild_id), {})

# Mise à jour manuelle des PV d'un joueur
def set_hp(guild_id, user_id, value):
    hp.setdefault(str(guild_id), {})
    hp[str(guild_id)][user_id] = value

# Accès direct au leaderboard d'un serveur (stats de combat uniquement)
def get_leaderboard(guild_id):
    return leaderboard.setdefault(str(guild_id), {})

# Accès au solde GotCoins d'un joueur (argent total actuel) → exposé ici proprement
def get_user_balance(guild_id, user_id):
    return get_balance(guild_id, user_id)

# Accès combiné complet aux données d'un joueur : inventaire, PV, stats de combat
def get_user_data(guild_id, user_id):
    gid = str(guild_id)
    uid = str(user_id)

    inv = inventaire.setdefault(gid, {}).setdefault(uid, [])
    pv = hp.setdefault(gid, {}).setdefault(uid, 100)

    # Initialisation complète des stats de COMBAT
    stats = leaderboard.setdefault(gid, {}).setdefault(uid, {
        "degats": 0,
        "soin": 0,
        "kills": 0,
        "morts": 0
    })

    # Correction éventuelle (si stats incomplètes)
    if not isinstance(stats, dict):
        stats = {"degats": 0, "soin": 0, "kills": 0, "morts": 0}
        leaderboard[gid][uid] = stats
    else:
        for key in ("degats", "soin", "kills", "morts"):
            stats.setdefault(key, 0)

    return inv, pv, stats

# Reset complet des données d'un serveur
def reset_guild_data(guild_id):
    gid = str(guild_id)
    inventaire[gid] = {}
    hp[gid] = {}
    leaderboard[gid] = {}

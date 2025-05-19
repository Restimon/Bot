import random

# Objets disponibles
OBJETS = {
    "❄️": {"type": "attaque", "degats": 1, "rarete": 1},
    "🔥": {"type": "attaque", "degats": 5, "rarete": 3},
    "⚡": {"type": "attaque", "degats": 10, "rarete": 5},
    "🔫": {"type": "attaque", "degats": 15, "rarete": 7},
    "🧨": {"type": "attaque", "degats": 20, "rarete": 9},
    "🍀": {"type": "soin", "soin": 5, "rarete": 5},
    "💊": {"type": "soin", "soin": 10, "rarete": 6},
    "💉": {"type": "soin", "soin": 15, "rarete": 8}
}

# Gifs associés aux objets
GIFS = {
    "❄️": "https://media4.giphy.com/media/v1.Y2lkPTc5MGI3NjExY3NlcTYyZDVkMjhpY3dpbmVhaXB2OXRoZGNxMHp2d3dnMmhldWR4OSZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/sTUe8s1481gY0/giphy.gif",
    "🔥": "https://i.gifer.com/MV3z.gif",
    "⚡": "https://act-webstatic.hoyoverse.com/upload/contentweb/2023/02/02/9ed221220865a923de00661f5f9e7dea_7010733949792563480.gif",
    "🔫": "https://www.reddit.com/media?url=https%3A%2F%2Fi.redd.it%2Fa9bj0bk6ssu61.gif",
    "🧨": "https://tenor.com/fr/view/konosuba-explosion-anime-gif-23322221",
    "🍀": "https://64.media.tumblr.com/858f7aa3c8cee743d61a5ff4d73a378f/tumblr_n2mzr2nf7C1sji00bo1_500.gifv",
    "💊": "https://www.reddit.com/media?url=https%3A%2F%2Fi.redd.it%2F9ojmyg3npkl91.gif",
    "💉": "https://static.wikia.nocookie.net/bokunoheroacademia/images/1/11/Heal.gif/revision/latest?cb=20180910131529",
    "soin_autre": "https://i.makeagif.com/media/9-05-2023/UUHN2G.gif"
}

# Liste d'objets avec pondération basée sur rareté
def get_random_item():
    pool = []
    for emoji, data in OBJETS.items():
        pool.extend([emoji] * (26 - data["rarete"]))
    return random.choice(pool)

# ====================== Données multi-serveur ======================

# {guild_id: {user_id: [objets]}}
inventaire = {}

# {guild_id: {user_id: 100}}
hp = {}

# {guild_id: {user_id: {"degats": x, "soin": y}}}
leaderboard = {}

# Cooldowns
cooldowns = {"attack": {}, "heal": {}}

# Constantes de cooldown en secondes
ATTACK_COOLDOWN = 15 * 60
HEAL_COOLDOWN = 60 * 60

# Fonction utilitaire pour s'assurer que les structures existent
def get_user_data(guild_id, user_id):
    gid = str(guild_id)
    uid = str(user_id)

    inventaire.setdefault(gid, {}).setdefault(uid, [])
    hp.setdefault(gid, {}).setdefault(uid, 100)
    leaderboard.setdefault(gid, {}).setdefault(uid, {"degats": 0, "soin": 0})

    return inventaire[gid][uid], hp[gid][uid], leaderboard[gid][uid]

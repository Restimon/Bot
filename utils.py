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
    "🔫": "https://media3.giphy.com/media/v1.Y2lkPTc5MGI3NjExc3NocHU2aGE5Nm0yM3NjdGF1OGR1MmRrZGp3d20ycGowcGM4Nm5ibyZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/10ZuedtImbopos/giphy.gif",
    "🧨": "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExenF3eHlsd2E5N3R3enNleHFoNzUwd2Iyc2NtdnBnZnprbjBjaWV1byZlcD12MV9naWZzX3NlYXJjaCZjdD1n/oe33xf3B50fsc/giphy.gif",
    "🍀": "https://media.giphy.com/media/jN07m6w9uuZAeh80z0/giphy.gif?cid=ecf05e474yl44a4sx6ndpqcajubfga6xbcy4y5w8dgclucck&ep=v1_gifs_search&rid=giphy.gif&ct=g",
    "💊": "https://64.media.tumblr.com/858f7aa3c8cee743d61a5ff4d73a378f/tumblr_n2mzr2nf7C1sji00bo1_500.gifv",
    "💉": "https://media.giphy.com/media/s8oHUwsjS8w5OD7Sg7/giphy.gif?cid=ecf05e47x77gai11gsj891f8jfzuntwv0detkk5p8vci8ig3&ep=v1_gifs_search&rid=giphy.gif&ct=g",
    "soin_autre": "https://i.makeagif.com/media/9-05-2023/UUHN2G.gif"
}

# Objets avec pondération (plus rare = moins probable)
def get_random_item():
    pool = []
    for emoji, data in OBJETS.items():
        pool.extend([emoji] * (26 - data["rarete"]))
    return random.choice(pool)

cooldowns = {"attack": {}, "heal": {}}

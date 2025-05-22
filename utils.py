import random

# Objets disponibles
OBJETS = {
    "❄️": {"type": "attaque", "degats": 1, "rarete": 1, "crit": 0.35},
    "🪓": {"type": "attaque", "degats": 3, "rarete": 2, "crit": 0.3},
    "🔥": {"type": "attaque", "degats": 5, "rarete": 3, "crit": 0.25},
    "⚡": {"type": "attaque", "degats": 10, "rarete": 5, "crit": 0.20},
    "🔫": {"type": "attaque", "degats": 15, "rarete": 12, "crit": 0.15},
    "🧨": {"type": "attaque", "degats": 20, "rarete": 15, "crit": 0.10},
    "☠️": {"type": "attaque", "degats_principal": 24, "degats_secondaire": 12, "rarete": 25, "crit": 0.15},
    "🦠": {"type": "virus", "status": "virus", "degats": 5, "duree": 6 * 3600, "rarete": 22, "crit": 0.1},
    "🧪": {"type": "poison", "status": "poison", "degats": 3, "intervalle": 1800, "duree": 3 * 3600, "rarete": 13, "crit": 0.1},
    "🧟": {"type": "infection", "status": "infection", "degats": 5, "intervalle": 1800, "duree": 3 * 3600, "rarete": 25},
    "🍀": {"type": "soin", "soin": 1, "rarete": 2, "crit": 0.35},
    "🩸": {"type": "soin", "soin": 5, "rarete": 6, "crit": 0.3},
    "🩹": {"type": "soin", "soin": 10, "rarete": 9, "crit": 0.2},
    "💊": {"type": "soin", "soin": 15, "rarete": 15, "crit": 0.2},
    "💕": {"type": "regen", "valeur": 3, "intervalle": 1800, "duree": 3 * 3600, "rarete": 20, "crit": 0.10},
    "📦": {"type": "mysterybox", "rarete": 16},
    "🔍": {"type": "vol", "rarete": 12},
    "💉": {"type": "vaccin", "rarete": 17},
    "🛡": {"type": "bouclier", "valeur": 20, "rarete": 18},
    "👟": {"type": "esquive+", "valeur": 0.2, "duree": 3 * 3600, "rarete": 14},
    "🪖": {"type": "reduction", "valeur": 0.5, "duree": 4 * 3600, "rarete": 16},
    "⭐️": {"type": "immunite", "duree": 2 * 3600, "rarete": 22}
}

GIFS = {
    "❄️": "https://media4.giphy.com/media/v1.Y2lkPTc5MGI3NjExY3NlcTYyZDVkMjhpY3dpbmVhaXB2OXRoZGNxMHp2d3dnMmhldWR4OSZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/sTUe8s1481gY0/giphy.gif",
    "🪓": "https://media.giphy.com/media/oFVr84BOpjyiA/giphy.gif?cid=ecf05e47gwzwh637iu0dhwjgzh8hm1leeettft94zqx4qbxn&ep=v1_gifs_search&rid=giphy.gif&ct=g",
    "🔥": "https://i.gifer.com/MV3z.gif",
    "⚡": "https://act-webstatic.hoyoverse.com/upload/contentweb/2023/02/02/9ed221220865a923de00661f5f9e7dea_7010733949792563480.gif",
    "🔫": "https://media3.giphy.com/media/v1.Y2lkPTc5MGI3NjExc3NocHU2aGE5Nm0yM3NjdGF1OGR1MmRrZGp3d20ycGowcGM4Nm5ibyZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/10ZuedtImbopos/giphy.gif",
    "🧨": "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExenF3eHlsd2E5N3R3enNleHFoNzUwd2Iyc2NtdnBnZnprbjBjaWV1byZlcD12MV9naWZzX3NlYXJjaCZjdD1n/oe33xf3B50fsc/giphy.gif",
    "🦠": "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExYjN5aTJzYmhma2trYzhpcWpxaTQxMHE1dHEyZzcyZXlpMGFhNTI2eiZlcD12MV9naWZzX3NlYXJjaCZjdD1n/7htcRg2IORvgKBKryu/giphy.gif",
    "🧪": "https://media2.giphy.com/media/v1.Y2lkPTc5MGI3NjExbHFhOG0zaTQxaDQ5a2JndWVxMm0yc3BmOGRlaXVubDdqdGJheHNhdyZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/9lHsP26ijVJwylXsff/giphy.gif",
    "🧟": "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExZGcyNjVzYWwxamNhN29sOHFidGRtcWg0bnEweWR0bXE0dW9sbWI3bCZlcD12MV9naWZzX3NlYXJjaCZjdD1n/10bKG23wIFlKmc/giphy.gif",
    "🍀": "https://i.makeagif.com/media/9-05-2023/UUHN2G.gif",
    "🩸": "https://media.giphy.com/media/jN07m6w9uuZAeh80z0/giphy.gif?cid=ecf05e474yl44a4sx6ndpqcajubfga6xbcy4y5w8dgclucck&ep=v1_gifs_search&rid=giphy.gif&ct=g",
    "🩹": "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExcGk1b205enk4MXpzcWp0MjV5YjdrNHM0ODZheWxzOGRicTZ1eTJubiZlcD12MV9naWZzX3NlYXJjaCZjdD1n/EwKe1XdABwk2yvTyQt/giphy.gif",
    "💊": "https://64.media.tumblr.com/858f7aa3c8cee743d61a5ff4d73a378f/tumblr_n2mzr2nf7C1sji00bo1_500.gifv",
    "💉": "https://media.giphy.com/media/s8oHUwsjS8w5OD7Sg7/giphy.gif?cid=ecf05e47x77gai11gsj891f8jfzuntwv0detkk5p8vci8ig3&ep=v1_gifs_search&rid=giphy.gif&ct=g",
    "🔍": "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExZHpjbGI0dHRueHAwemhvY2Ztd2NjdHVqdnZka2lueHM3c2E3amtmMCZlcD12MV9naWZzX3NlYXJjaCZjdD1n/1fih1TYYBONo0Dkdmx/giphy.gif",
    "⭐️": "https://media4.giphy.com/media/v1.Y2lkPTc5MGI3NjExYm5od3Z4YXpubGRib3FkNTF5bTJiejczejFoOXpzemZxaXhkZmhpayZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/9tz1MAa6NzMDhXiD00/giphy.gif",
    "🪖": "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExcWFqa2Uzd25uM3dsMjd0eGs4a2xtdTJpaW0wajFrZ3Nlc3RjanM2eiZlcD12MV9naWZzX3NlYXJjaCZjdD1n/VxHixRra5rtEMMw7b0/giphy.gif",
    "🛡": "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExMDBmZzY3bXdpeWNncnVnMHNieW45dHVpZnRpOWM1bW9qcDhtYm5kMSZlcD12MV9naWZzX3NlYXJjaCZjdD1n/rR7wrU76zfWnf7xBDR/giphy.gif",
    "👟": "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExenJtZmFoem13aGwxNTVwYzVrc3k0cG00enBkZ3lxeHV2MTVjeTBoNSZlcD12MV9naWZzX3NlYXJjaCZjdD1n/EBiho5DrxUQ75JMcq7/giphy.gif",
    "☠️": "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExMDdqb2R0eWJvZzh4eXJuZXNuYmJjZDZzeWxtZDF3Zjg2bmpsMHpsbCZlcD12MV9naWZzX3NlYXJjaCZjdD1n/qtkfPuvX4wrSuW5Q4T/giphy.gif",
    "soin_autre": "https://media2.giphy.com/media/v1.Y2lkPTc5MGI3NjExcDVwc21sMTQ5MGF2bjRrazdmdHJpMmFoNGgzeGxtazF4Mnl6MHByNyZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/Mxb7h4hq6mJNzWNF5W/giphy.gif",
    "critique": "https://media0.giphy.com/media/v1.Y2lkPTc5MGI3NjExcnRsZDZzNmUxM3N4OHVqbXhmOWUxbzVjOGkyeTR2cW1tMHlzamxnbCZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/o2TqK6vEzhp96/giphy.gif",
    "esquive": "https://media2.giphy.com/media/v1.Y2lkPTc5MGI3NjExNHdzZDd6eHhyMHZqdmZnMGg5ZXoybnMwM3g5NzgwbXVuNjFqNjI4dCZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/eIm624c8nnNbiG0V3g/giphy.gif"
}

# Objets avec pondération (plus rare = moins probable)
def get_random_item():
    pool = []
    for emoji, data in OBJETS.items():
        pool.extend([emoji] * (26 - data["rarete"]))
    return random.choice(pool)

# Cooldowns globaux (utilisés dans data.py)
cooldowns = {
    "attack": {},
    "heal": {}
}

# Cooldowns en secondes
ATTACK_COOLDOWN = 15 * 60  # 15 minutes
HEAL_COOLDOWN = 60 * 60    # 1 heure

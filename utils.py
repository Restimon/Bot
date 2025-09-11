# utils.py
import random
import time

# --- Imports "souples" pour éviter les crashs si tout n'est pas encore présent
try:
    # On importe le module complet pour pouvoir modifier ses attributs au besoin
    import storage as _storage
    from storage import get_user_data
except Exception:  # Si storage pas prêt
    _storage = type("S", (), {})()
    _storage.hp = {}
    _storage.leaderboard = {}
    def get_user_data(guild_id, user_id):
        return [], 100, None  # fallback ultra-minimal

# Assure l'existence de hp/leaderboard dans storage
if not hasattr(_storage, "hp") or not isinstance(getattr(_storage, "hp"), dict):
    _storage.hp = {}
if not hasattr(_storage, "leaderboard") or not isinstance(getattr(_storage, "leaderboard"), dict):
    _storage.leaderboard = {}

# Cooldowns (facultatif ici, on laisse des placeholders si module absent)
try:
    from cooldowns import is_on_cooldown, cooldowns, ATTACK_COOLDOWN, HEAL_COOLDOWN
except Exception:
    def is_on_cooldown(*args, **kwargs): return False
    cooldowns = {}
    ATTACK_COOLDOWN = 0
    HEAL_COOLDOWN = 0

# Effets (on fait un no-op si le module n'existe pas)
try:
    from effects import remove_status_effects
except Exception:
    def remove_status_effects(guild_id, user_id):  # no-op
        return

# Statut d'esquive (on tolère l'absence)
try:
    from data import esquive_status
except Exception:
    esquive_status = {}

# =========================
# Objets disponibles
# =========================
OBJETS = {
    "❄️": {"type": "attaque", "degats": 1, "rarete": 1, "crit": 0.35},
    "🪓": {"type": "attaque", "degats": 3, "rarete": 2, "crit": 0.3},
    "🔥": {"type": "attaque", "degats": 5, "rarete": 3, "crit": 0.25},
    "⚡": {"type": "attaque", "degats": 10, "rarete": 5, "crit": 0.20},
    "🔫": {"type": "attaque", "degats": 15, "rarete": 12, "crit": 0.15},
    "🧨": {"type": "attaque", "degats": 20, "rarete": 20, "crit": 0.10},
    "☠️": {"type": "attaque_chaine", "degats_principal": 24, "degats_secondaire": 12, "rarete": 25, "crit": 0.15},
    "🦠": {"type": "virus", "status": "virus", "degats": 5, "duree": 6 * 3600, "rarete": 22, "crit": 0.1},
    "🧪": {"type": "poison", "status": "poison", "degats": 3, "intervalle": 1800, "duree": 3 * 3600, "rarete": 13, "crit": 0.1},
    "🧟": {"type": "infection", "status": "infection", "degats": 5, "intervalle": 1800, "duree": 3 * 3600, "rarete": 25, "crit": 0.1},
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
    "⭐️": {"type": "immunite", "duree": 2 * 3600, "rarete": 22},
}

GIFS = {
    "❄️": "https://media4.giphy.com/media/v1.Y2lkPTc5MGI3NjExY3NlcTYyZDVkMjhpY3dpbmVhaXB2OXRoZGNxMHp2d3dnMmhldWR4OSZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/sTUe8s1481gY0/giphy.gif",
    "🪓": "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExeTNtZnJ4MDd2eGpodmZnYzhpcXJlZjJsbmUwMmY2cjg2cmF5YjgxeSZlcD12MV9naWZzX3NlYXJjaCZjdD1n/oFVr84BOpjyiA/giphy.gif",
    "🔥": "https://i.gifer.com/MV3z.gif",
    "⚡": "https://act-webstatic.hoyoverse.com/upload/contentweb/2023/02/02/9ed221220865a923de00661f5f9e7dea_7010733949792563480.gif",
    "🔫": "https://www.reddit.com/media?url=https%3A%2F%2Fi.redd.it%2Fa9bj0bk6ssu61.gif",
    "🧨": "https://tenor.com/fr/view/konosuba-explosion-anime-gif-23322221",
    "☠️": "https://media3.giphy.com/media/v1.Y2lkPTc5MGI3NjExb3Nqc3E1dWpwaHFxcjFsMGdodm5ndmIxMjh1ZW10bXc4dDV3bXB4dCZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/qtkfPuvX4wrSuW5Q4T/giphy.gif",
    "🦠": "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExMWwyNjRldHBvNWNtaDk2eTMybjkxOHIwajB6b3Jxd3Q1cWVjcWNwZyZlcD12MV9naWZzX3NlYXJjaCZjdD1n/7htcRg2IORvgKBKryu/giphy.gif",
    "🧪": "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExOXpubGQwd3A5am11eHN4YmQwaHh3aWtxNnpxN296NGl6aG5xbnB2YSZlcD12MV9naWZzX3NlYXJjaCZjdD1n/9lHsP26ijVJwylXsff/giphy.gif",
    "🧟": "https://media0.giphy.com/media/v1.Y2lkPTc5MGI3NjExYWdlZzNoYmdjd29lY29qbjE1OWY0M2gwOXRuZXlqdXVnYXh0ZWttaiZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/UB1ZaCan78Ydj67IQl/giphy.gif",
    "🍀": "https://64.media.tumblr.com/858f7aa3c8cee743d61a5ff4d73a378f/tumblr_n2mzr2nf7C1sji00bo1_500.gifv",
    "🩸": "https://media2.giphy.com/media/v1.Y2lkPTc5MGI3NjExdDhub24zeTFxbnk4ZHJ0bHkxbXVxOTVlZjljYzd0dGR5dGk4cWU1ayZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/jN07m6w9uuZAeh80z0/giphy.gif",
    "🩹": "https://media1.giphy.com/media/v1.Y2lkPTc5MGI3NjExbmJzam1wdTU2d3hvZjR4anhtYTdqeWFnY3M1eXdzNnRvZ2lncWViOSZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/EwKe1XdABwk2yvTyQt/giphy.gif",
    "💊": "https://www.reddit.com/media?url=https%3A%2F%2Fi.redd.it%2F9ojmyg3npkl91.gif",
    "💕": "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExdGw5dGZkZHp2azRjNzU5Zms1dzFkM21wczYzajA5OWk2ZjAycTNnYyZlcD12MV9naWZzX3NlYXJjaCZjdD1n/CoKJD9a9pxc9W/giphy.gif",
    "🔍" "https://media0.giphy.com/media/v1.Y2lkPTc5MGI3NjExd2Q0MGh0MmxzbWJkZW41d3ZremZudm8xaWsxbnBveW1vbmpvNDc3YyZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/1fih1TYYBONo0Dkdmx/giphy.gif",
    "💉": "https://static.wikia.nocookie.net/bokunoheroacademia/images/1/11/Heal.gif/revision/latest?cb=20180910131529",
    "🛡": "https://media2.giphy.com/media/v1.Y2lkPTc5MGI3NjExNTkzb3hiNnR5Y2F1dmxycTl1OXZ6OWY0dTJ0eXoxdDlnMjZteDJmaiZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/rR7wrU76zfWnf7xBDR/giphy.gif",
    "👟": "https://media0.giphy.com/media/v1.Y2lkPTc5MGI3NjExYzEwNngwZzk4ejd2ejg1YTZ4YWtkYmQzaG4zdW9lbzFvZThsNnp6MiZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/EBiho5DrxUQ75JMcq7/giphy.gif",
    "🪖": "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExN2I1amJ0eDgyZGVjZWYwdG5yYmF5ZnVjZTR2ZTNwZDlha2QwZGFnciZlcD12MV9naWZzX3NlYXJjaCZjdD1n/a0BE1Myry8SsR61BP7/giphy.gif",
    "⭐️": "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExeXhkencxNTVud25lbzd6OHkyNHd3MXdtMWx4dm5tNm04MmNqanhpeSZlcD12MV9naWZzX3NlYXJjaCZjdD1n/2GBfKwJ7bypANDoqRt/giphy.gif",
    "soin_autre": "https://i.makeagif.com/media/9-05-2023/UUHN2G.gif"
}

REWARD_EMOJIS = ["💰"]

# =========================
# Utilitaires
# =========================
def check_crit(chance: float) -> bool:
    try:
        return random.random() < float(chance or 0.0)
    except Exception:
        return False

def get_random_item(debug: bool = False):
    # 5% : drop de coins
    if random.random() < 0.05:
        if debug:
            print("[get_random_item] 💰 Tirage spécial : Coins")
        return random.choice(REWARD_EMOJIS)

    pool = []
    for emoji, data in OBJETS.items():
        poids = 26 - int(data.get("rarete", 25))
        if poids > 0:
            pool.extend([emoji] * poids)

    if debug:
        print(f"[get_random_item] Pool objets = {pool}")

    return random.choice(pool) if pool else None

def _ensure_guild_user_hp(guild_id: str, user_id: str):
    _storage.hp.setdefault(str(guild_id), {}).setdefault(str(user_id), 100)

def handle_death(guild_id: str, target_id: str, source_id: str | None = None):
    """Réinitialise PV, nettoie les statuts, met à jour le leaderboard (safe)."""
    gid = str(guild_id)
    tid = str(target_id)
    _ensure_guild_user_hp(gid, tid)

    # Reset PV
    _storage.hp[gid][tid] = 100

    # Suppression des statuts (si système d'effets non présent, no-op)
    try:
        remove_status_effects(gid, tid)
    except Exception as e:
        print(f"[handle_death] Erreur de suppression des statuts : {e}")

    # Leaderboard
    if source_id and str(source_id) != tid:
        update_leaderboard(gid, str(source_id), points_delta=50, kill=1)
    update_leaderboard(gid, tid, points_delta=-25, death=1)

def get_mention(guild, user_id: str):
    try:
        member = guild.get_member(int(user_id))
        return member.mention if member else f"<@{user_id}>"
    except Exception:
        return f"<@{user_id}>"

# ---------- ✅ Nouveaux utilitaires demandés par passifs.py ----------
def remove_random_item(guild_id: str, user_id: str):
    """Retire un objet (emoji str) aléatoire de l'inventaire d'un joueur. Ignore les entrées 'personnage' (dict)."""
    inv, _, _ = get_user_data(str(guild_id), str(user_id))
    indices = [i for i, it in enumerate(inv) if isinstance(it, str)]
    if not indices:
        return None
    idx = random.choice(indices)
    return inv.pop(idx)

def give_random_item(guild_id: str, user_id: str, item: str):
    """Ajoute un objet (emoji str) à l'inventaire d'un joueur."""
    inv, _, _ = get_user_data(str(guild_id), str(user_id))
    inv.append(item)
    return True

def get_random_enemy(guild_id: str, exclude=None):
    """
    Renvoie l'ID (str) d’un joueur aléatoire différent du porteur.
    On parcourt les joueurs connus via hp[guild_id].
    """
    exclude = set(map(str, exclude or []))
    gid = str(guild_id)
    candidates = [uid for uid in _storage.hp.get(gid, {}).keys() if str(uid) not in exclude]
    return random.choice(candidates) if candidates else None
# ---------- Fin des utilitaires pour passifs.py ----------

def get_evade_chance(guild_id: str, user_id: str) -> float:
    """Calcule la chance d'esquive pour un utilisateur, avec bonus de statut et passifs."""
    base_chance = 0.10  # 10 % de base
    bonus = 0.0
    now = time.time()

    # 🔷 Statut temporaire d'esquive (ex: 👟)
    try:
        data = esquive_status.get(str(guild_id), {}).get(str(user_id))
        if data and (now - float(data.get("start", 0))) < float(data.get("duration", 0)):
            bonus += float(data.get("valeur", 0.2))
    except Exception:
        pass

    # 🌀 Passifs (appel paresseux pour éviter import circulaire)
    try:
        from passifs import appliquer_passif as _appliquer_passif
        result = _appliquer_passif("calcul_esquive", {
            "guild_id": str(guild_id),
            "defenseur": str(user_id)
        })
    except Exception:
        result = {}

    # clamp raisonnable
    total = max(0.0, min(0.95, base_chance + bonus))
    return total

# =========================
# Leaderboard helper (safe)
# =========================
def update_leaderboard(guild_id: str, user_id: str, points_delta: int = 0, kill: int = 0, death: int = 0):
    """
    Maintient un leaderboard très simple.
    Structure: storage.leaderboard[guild_id][user_id] = {"points": int, "kills": int, "deaths": int}
    """
    gid = str(guild_id)
    uid = str(user_id)
    _storage.leaderboard.setdefault(gid, {}).setdefault(uid, {"points": 0, "kills": 0, "deaths": 0})
    entry = _storage.leaderboard[gid][uid]
    try:
        entry["points"] = int(entry.get("points", 0)) + int(points_delta)
        entry["kills"] = int(entry.get("kills", 0)) + int(kill)
        entry["deaths"] = int(entry.get("deaths", 0)) + int(death)
    except Exception:
        # si jamais un type inattendu s'est glissé dedans
        entry["points"] = int(points_delta)
        entry["kills"] = int(kill)
        entry["deaths"] = int(death)



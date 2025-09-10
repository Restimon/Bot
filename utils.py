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
        from passifs import appliquer_passif
        result = appliquer_passif({"nom": ""}, "calcul_esquive", {
            "guild_id": str(guild_id),
            "defenseur": str(user_id)
        })
        if isinstance(result, dict):
            bonus += float(result.get("bonus_esquive", 0.0)) / 100.0  # en pourcentage
    except Exception:
        pass

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

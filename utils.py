import random
import time

from storage import hp, leaderboard
from cooldowns import is_on_cooldown, cooldowns, ATTACK_COOLDOWN, HEAL_COOLDOWN
from leaderboard_utils import update_leaderboard
from effects import remove_status_effects

# Objets disponibles
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
    "⭐️": {"type": "immunite", "duree": 2 * 3600, "rarete": 22}
}

# Objets avec pondération (plus rare = moins probable)
def check_crit(chance):
    """Renvoie True si un coup critique a lieu selon la probabilité `chance` (0.0 à 1.0)."""
    return random.random() < chance

def get_random_item():
    pool = []
    for emoji, data in OBJETS.items():
        pool.extend([emoji] * (26 - data["rarete"]))
    return random.choice(pool)

def handle_death(guild_id, target_id, source_id=None):
    hp[guild_id][target_id] = 100  # Remise à 100 PV

    try:
        remove_status_effects(guild_id, target_id)
    except Exception as e:
        print(f"[handle_death] Erreur lors de la suppression des statuts : {e}")

    if source_id and source_id != target_id:
        update_leaderboard(guild_id, source_id, 50, kill=1)
        update_leaderboard(guild_id, target_id, -25, death=1)
    else:
        update_leaderboard(guild_id, target_id, -25, death=1)

import json
import os
import time

from storage import inventaire, hp, leaderboard

# ✅ Utilisation du disk persistant monté via Render
DATA_FILE = "/persistent/data.json"

# États persistants
infection_status = {} 
virus_status = {}
poison_status = {}
last_daily_claim = {}
shields = {}
esquive_bonus = {}  
casque_bonus = {}
regeneration_status = {}  
immunite_status = {} 

# Cooldowns globaux (utilisés dans data.py)
cooldowns = {
    "attack": {},
    "heal": {}
}

def is_on_cooldown(guild_id, key, action_type):
    now = time.time()
    guild_cooldowns = cooldowns[action_type].setdefault(str(guild_id), {})
    last_used = guild_cooldowns.get(key, 0)
    duration = ATTACK_COOLDOWN if action_type == "attack" else HEAL_COOLDOWN
    remaining = duration - (now - last_used)
    return (remaining > 0), max(int(remaining), 0)

ATTACK_COOLDOWN = 120  # en secondes
HEAL_COOLDOWN = 180

def sauvegarder():
    """Sauvegarde toutes les données SomniCorp dans un seul fichier JSON."""
    try:
        os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "inventaire": inventaire,
                "hp": hp,
                "leaderboard": leaderboard,
                "last_daily_claim": last_daily_claim,
                "cooldowns": cooldowns,
                "virus_status": virus_status,
                "poison_status": poison_status,
                "infection_status": infection_status,
                "regeneration_status": regeneration_status,
                "immunite_status": immunite_status,
                "shields": shields,
                "esquive_bonus": esquive_bonus,
                "casque_bonus": casque_bonus
            }, f, indent=4, ensure_ascii=False)
        print("💾 Données sauvegardées dans data.json.")  
    except Exception as e:
        print(f"❌ Erreur lors de la sauvegarde : {e}")

def charger():
    """Charge toutes les données SomniCorp depuis un seul fichier JSON."""
    global last_daily_claim
    if not os.path.exists(DATA_FILE):
        print("ℹ️ Aucun fichier data.json trouvé — initialisation d'une nouvelle base.")
        return

    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        inventaire.clear()
        hp.clear()
        leaderboard.clear()
        cooldowns["attack"].clear()
        cooldowns["heal"].clear()

        inventaire.update(data.get("inventaire", {}))
        hp.update(data.get("hp", {}))
        leaderboard.update(data.get("leaderboard", {}))

        last_daily_claim.clear()
        last_daily_claim.update(data.get("last_daily_claim", {}))

        cooldowns.update(data.get("cooldowns", {"attack": {}, "heal": {}}))

        virus_status.clear()
        virus_status.update(data.get("virus_status", {}))

        poison_status.clear()
        poison_status.update(data.get("poison_status", {}))

        regeneration_status.clear()
        regeneration_status.update(data.get("regeneration_status", {}))
        
        infection_status.clear()
        infection_status.update(data.get("infection_status", {}))

        immunite_status.clear()
        immunite_status.update(data.get("immunite_status", {}))

        shields.clear()
        shields.update(data.get("shields", {}))

        esquive_bonus.clear()
        esquive_bonus.update(data.get("esquive_bonus", {}))

        casque_bonus.clear()
        casque_bonus.update(data.get("casque_bonus", {}))

        print("✅ Données chargées depuis data.json.")

    except json.JSONDecodeError:
        print("⚠️ Le fichier data.json est corrompu ou mal formé.")
    except Exception as e:
        print(f"❌ Erreur inattendue lors du chargement : {e}")

def remove_status_effects(guild_id, user_id):
    for status_dict in [virus_status, poison_status, infection_status]:
        if guild_id in status_dict and user_id in status_dict[guild_id]:
            del status_dict[guild_id][user_id]

def update_leaderboard(guild_id, user_id, points, kill=0, death=0):
    leaderboard.setdefault(guild_id, {})
    leaderboard[guild_id].setdefault(user_id, {"degats": 0, "soin": 0, "kills": 0, "morts": 0})
    leaderboard[guild_id][user_id]["degats"] += points
    leaderboard[guild_id][user_id]["kills"] += kill
    leaderboard[guild_id][user_id]["morts"] += death

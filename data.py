import json
import os
from storage import inventaire, hp, leaderboard
from utils import cooldowns  # Important pour accès aux cooldowns globaux

# ✅ Utilisation du disk persistant monté via Render
DATA_FILE = "/persistent/data.json"

# États persistants
virus_status = {}
poison_status = {}
last_daily_claim = {}

# Cooldowns globaux
cooldowns = {
    "attack": {},
    "heal": {}
}

ATTACK_COOLDOWN = 3 * 60 
HEAL_COOLDOWN = 2 * 60    

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
                "poison_status": poison_status
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

        print("✅ Données chargées depuis data.json.")

    except json.JSONDecodeError:
        print("⚠️ Le fichier data.json est corrompu ou mal formé.")
    except Exception as e:
        print(f"❌ Erreur inattendue lors du chargement : {e}")

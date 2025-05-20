import json
import os
from storage import inventaire, hp, leaderboard

DATA_FILE = "data.json"

def sauvegarder():
    """Sauvegarde toutes les données par serveur dans un fichier JSON."""
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "inventaire": inventaire,
                "hp": hp,
                "leaderboard": leaderboard
            }, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"❌ Erreur lors de la sauvegarde : {e}")

def charger():
    """Charge les données depuis le fichier si existant, sinon initialise."""
    if not os.path.exists(DATA_FILE):
        print("ℹ️ Aucun fichier data.json trouvé — initialisation d'une nouvelle base.")
        return

    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        inventaire.clear()
        hp.clear()
        leaderboard.clear()

        inventaire.update(data.get("inventaire", {}))
        hp.update(data.get("hp", {}))
        leaderboard.update(data.get("leaderboard", {}))

    except json.JSONDecodeError:
        print("⚠️ Le fichier data.json est corrompu ou mal formé.")
    except Exception as e:
        print(f"❌ Erreur inattendue lors du chargement : {e}")
        
LAST_CLAIM_FILE = "daily_claims.json"
last_daily_claim = {}

def sauvegarder_daily_claims():
    with open(LAST_CLAIM_FILE, "w", encoding="utf-8") as f:
        json.dump(last_daily_claim, f, indent=4)

def charger_daily_claims():
    global last_daily_claim
    if os.path.exists(LAST_CLAIM_FILE):
        with open(LAST_CLAIM_FILE, "r", encoding="utf-8") as f:
            last_daily_claim = json.load(f)

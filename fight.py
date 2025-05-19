import json
import os
from utils import inventaire, hp, leaderboard

DATA_FILE = "data.json"

def sauvegarder():
    """Sauvegarde toutes les données des joueurs dans un fichier JSON."""
    data = {
        "inventaire": inventaire,
        "hp": hp,
        "leaderboard": leaderboard
    }
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"❌ Erreur lors de la sauvegarde : {e}")

def charger():
    """Charge les données depuis un fichier JSON si existant, sinon initialise les structures."""
    if os.path.exists(DATA_FILE):
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
            print("⚠️ Erreur : data.json est corrompu ou mal formé.")
        except Exception as e:
            print(f"❌ Erreur inattendue lors du chargement : {e}")
    else:
        print("ℹ️ Aucun fichier data.json trouvé — initialisation d'une nouvelle base.")

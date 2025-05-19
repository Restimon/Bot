import json
import os
from utils import inventaire, hp, leaderboard

DATA_FILE = "data.json"

def sauvegarder():
    data = {
        "inventaire": inventaire,
        "hp": hp,
        "leaderboard": leaderboard
    }
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def charger():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            inventaire.clear()
            hp.clear()
            leaderboard.clear()

            inventaire.update(data.get("inventaire", {}))
            hp.update(data.get("hp", {}))
            leaderboard.update(data.get("leaderboard", {}))

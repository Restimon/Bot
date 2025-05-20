import json
import os
from utils import OBJETS

DATA_FILE = "data.json"
CONFIG_FILE = "config.json"

def check_data():
    print("\n🔍 Vérification de data.json...")
    if not os.path.exists(DATA_FILE):
        print("❌ Fichier data.json manquant.")
        return

    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"❌ Erreur de lecture de data.json : {e}")
        return

    inventaire = data.get("inventaire", {})
    hp = data.get("hp", {})
    leaderboard = data.get("leaderboard", {})

    ok = True

    for gid, users in inventaire.items():
        for uid, items in users.items():
            if not isinstance(items, list):
                print(f"❌ {gid}/{uid} : inventaire n'est pas une liste")
                ok = False
            for item in items:
                if item not in OBJETS:
                    print(f"⚠️ {gid}/{uid} : objet inconnu '{item}'")

    for gid, users in hp.items():
        for uid, value in users.items():
            if not isinstance(value, int) or not (0 <= value <= 100):
                print(f"❌ {gid}/{uid} : HP invalide : {value}")
                ok = False

    for gid, users in leaderboard.items():
        for uid, stats in users.items():
            if not isinstance(stats, dict):
                print(f"❌ {gid}/{uid} : leaderboard invalide")
                ok = False
            if "degats" not in stats or "soin" not in stats:
                print(f"❌ {gid}/{uid} : stats incomplètes")
                ok = False

    if ok:
        print("✅ data.json : OK")


def check_config():
    print("\n🔍 Vérification de config.json...")
    if not os.path.exists(CONFIG_FILE):
        print("❌ Fichier config.json manquant.")
        return

    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            config = json.load(f)
    except Exception as e:
        print(f"❌ Erreur de lecture de config.json : {e}")
        return

    ok = True
    for gid, conf in config.items():
        if not isinstance(conf, dict):
            print(f"❌ {gid} : config invalide")
            ok = False
            continue
        if "leaderboard_channel_id" not in conf or "leaderboard_message_id" not in conf:
            print(f"❌ {gid} : champ manquant dans config")
            ok = False

    if ok:
        print("✅ config.json : OK")


if __name__ == "__main__":
    check_data()
    check_config()

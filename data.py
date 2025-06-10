import json
import os
import time
import shutil
from datetime import datetime

from storage import inventaire, hp, leaderboard

# ✅ Utilisation du disque persistant
PERSISTENT_PATH = "/persistent"
DATA_FILE = os.path.join(PERSISTENT_PATH, "data.json")
BACKUP_DIR = os.path.join(PERSISTENT_PATH, "backups")
AUTO_BACKUP_DIR = os.path.join(PERSISTENT_PATH, "auto_backups")  # <-- BACKUP INDÉPENDANTE

# Cooldowns par action
cooldowns = {
    "attack": {},
    "heal": {}
}

# États persistants
virus_status = {}
poison_status = {}
infection_status = {}
regeneration_status = {}
immunite_status = {}
shields = {}
esquive_status = {}
casque_status = {}
last_daily_claim = {}
supply_data = {}

# ✅ Miroir local → pour éviter circular import (sera MAJ par charger)
gotcoins_balance = {}

# ============================
# ✅ Sauvegarde manuelle (data.json + backup horodatée)
# ============================

def sauvegarder():
    try:
        # Import ici → pour éviter circular import
        import economy

        os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
        os.makedirs(BACKUP_DIR, exist_ok=True)

        # 🔁 Créer une backup horodatée de data.json (classique)
        if os.path.exists(DATA_FILE):
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            backup_name = f"data_backup_{timestamp}.json"
            shutil.copy2(DATA_FILE, os.path.join(BACKUP_DIR, backup_name))

        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "inventaire": inventaire,
                "hp": hp,
                "leaderboard": leaderboard,
                "gotcoins_balance": economy.gotcoins_balance,  # on sauvegarde l'original
                "cooldowns": cooldowns,
                "virus_status": virus_status,
                "poison_status": poison_status,
                "infection_status": infection_status,
                "regeneration_status": regeneration_status,
                "immunite_status": immunite_status,
                "shields": shields,
                "esquive_status": esquive_status,
                "casque_status": casque_status,
                "last_daily_claim": last_daily_claim,
                "supply_data": supply_data
            }, f, indent=4, ensure_ascii=False)

        print("💾 Données sauvegardées avec backup horodatée.")
    except Exception as e:
        print(f"❌ Erreur lors de la sauvegarde : {e}")

# ============================
# ✅ Charger les données (data.json)
# ============================

def charger():
    global last_daily_claim
    if not os.path.exists(DATA_FILE):
        print("ℹ️ Aucun fichier data.json trouvé — initialisation d'une nouvelle base.")
        return

    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        inventaire.clear()
        inventaire.update(data.get("inventaire", {}))

        hp.clear()
        hp.update(data.get("hp", {}))

        leaderboard.clear()
        leaderboard.update(data.get("leaderboard", {}))

        # Import ici → pour éviter circular import
        import economy
        economy.gotcoins_balance.clear()
        economy.gotcoins_balance.update(data.get("gotcoins_balance", {}))

        cooldowns["attack"].clear()
        cooldowns["heal"].clear()
        cooldowns.update(data.get("cooldowns", {"attack": {}, "heal": {}}))

        virus_status.clear()
        virus_status.update(data.get("virus_status", {}))

        poison_status.clear()
        poison_status.update(data.get("poison_status", {}))

        infection_status.clear()
        infection_status.update(data.get("infection_status", {}))

        regeneration_status.clear()
        regeneration_status.update(data.get("regeneration_status", {}))

        immunite_status.clear()
        immunite_status.update(data.get("immunite_status", {}))

        shields.clear()
        shields.update(data.get("shields", {}))

        esquive_status.clear()
        esquive_status.update(data.get("esquive_status", {}))

        casque_status.clear()
        casque_status.update(data.get("casque_status", {}))

        supply_data.clear()
        supply_data.update(data.get("supply_data", {}))

        last_daily_claim.clear()
        last_daily_claim.update(data.get("last_daily_claim", {}))

        print(f"✅ Données chargées depuis data.json : {len(inventaire)} serveurs | {sum(len(u) for u in inventaire.values())} joueurs.")
    except json.JSONDecodeError:
        print("⚠️ Le fichier data.json est corrompu ou mal formé.")
    except Exception as e:
        print(f"❌ Erreur inattendue lors du chargement : {e}")

# ============================
# ✅ Backup auto indépendante (RAM vers fichier)
# ============================

def backup_auto_independante():
    try:
        import economy

        os.makedirs(AUTO_BACKUP_DIR, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        filename = f"auto_backup_{timestamp}.json"
        path = os.path.join(AUTO_BACKUP_DIR, filename)

        data = {
            "inventaire": inventaire,
            "hp": hp,
            "leaderboard": leaderboard,
            "gotcoins_balance": economy.gotcoins_balance  # on sauvegarde l'original
        }

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

        print(f"✅ Backup auto indépendante créée : {filename}")

    except Exception as e:
        print(f"❌ Erreur lors de la backup auto indépendante : {e}")

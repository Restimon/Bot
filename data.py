# data.py
import json
import os
import time
import shutil
from datetime import datetime

# ⚙️ États partagés côté stockage
from storage import inventaire, hp, leaderboard

# 📁 Emplacements de persistance
PERSISTENT_PATH = "/persistent"
DATA_FILE = os.path.join(PERSISTENT_PATH, "data.json")
BACKUP_DIR = os.path.join(PERSISTENT_PATH, "backups")
AUTO_BACKUP_DIR = os.path.join(PERSISTENT_PATH, "auto_backups")  # backups RAM indépendantes

# ============================
# ✅ États & structures globales
# ============================

# Cooldowns par action
cooldowns = {
    "attack": {},
    "heal": {},
}

# Statuts / effets
virus_status = {}
poison_status = {}
infection_status = {}
regeneration_status = {}
immunite_status = {}
burn_status = {}

# Buffs / malus
shields = {}
esquive_status = {}
esquive_bonus = {}
casque_status = {}
resistance_bonus = {}
malus_degat = {}

# Profiles & progression
last_daily_claim = {}
supply_data = {}

# Activité hebdo
weekly_message_count = {}
weekly_voice_time = {}
weekly_message_log = {}

# Tirages / gacha
tirages = {}

# Personnages
personnages_equipés = {}   # {guild_id: {user_id: "Nom du perso"}}
derniere_equip = {}        # {guild_id: {user_id: timestamp}}

# Légendaires / spécifiques
zeyra_last_survive_time = {}  # {guild_id: {user_id: ts}}
valen_seuils = {}             # {f"{gid}:{uid}": set([40,30,...])}

# ============================
# ✅ Sauvegarde disque
# ============================

def sauvegarder():
    """
    Sauvegarde l’intégralité de l’état en JSON.
    Crée une backup horodatée de l’ancien fichier avant d’écrire.
    """
    try:
        # Import paresseux pour éviter les imports circulaires
        import economy

        os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
        os.makedirs(BACKUP_DIR, exist_ok=True)

        # 🔁 Backup horodatée si un data.json existe déjà
        if os.path.exists(DATA_FILE):
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            backup_name = f"data_backup_{timestamp}.json"
            shutil.copy2(DATA_FILE, os.path.join(BACKUP_DIR, backup_name))

        # 💾 Écriture de l’instantané courant
        payload = {
            "inventaire": inventaire,
            "hp": hp,
            "leaderboard": leaderboard,

            # 💰 Économie (source de vérité dans economy)
            "gotcoins_balance": economy.gotcoins_balance,
            "gotcoins_stats": economy.gotcoins_stats,

            # Cooldowns
            "cooldowns": cooldowns,

            # Statuts
            "virus_status": virus_status,
            "poison_status": poison_status,
            "infection_status": infection_status,
            "regeneration_status": regeneration_status,
            "immunite_status": immunite_status,
            "burn_status": burn_status,

            # Buffs / malus
            "shields": shields,
            "esquive_status": esquive_status,
            "esquive_bonus": esquive_bonus,
            "casque_status": casque_status,
            "resistance_bonus": resistance_bonus,
            "malus_degat": malus_degat,

            # Progression / divers
            "last_daily_claim": last_daily_claim,
            "supply_data": supply_data,

            # Activité hebdo
            "weekly_message_count": weekly_message_count,
            "weekly_voice_time": weekly_voice_time,
            "weekly_message_log": weekly_message_log,

            # Tirages
            "tirages": tirages,

            # Personnages
            "personnages_equipés": personnages_equipés,
            "derniere_equip": derniere_equip,

            # Légendaires
            "zeyra_last_survive_time": zeyra_last_survive_time,
            "valen_seuils": valen_seuils,
        }

        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=4, ensure_ascii=False)

        print("💾 Données sauvegardées avec backup horodatée.")
    except Exception as e:
        print(f"❌ Erreur lors de la sauvegarde : {e}")

# ============================
# ✅ Chargement depuis le disque
# ============================

def charger():
    """
    Charge DATA_FILE si présent et hydrate toutes les structures en mémoire.
    Met à jour les objets de l’économie directement dans le module `economy`.
    """
    if not os.path.exists(DATA_FILE):
        print("ℹ️ Aucun fichier data.json trouvé — initialisation d'une nouvelle base.")
        return

    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Stockage principal
        inventaire.clear(); inventaire.update(data.get("inventaire", {}))
        hp.clear(); hp.update(data.get("hp", {}))
        leaderboard.clear(); leaderboard.update(data.get("leaderboard", {}))

        # 💰 Économie (import paresseux)
        import economy
        economy.gotcoins_balance.clear()
        economy.gotcoins_balance.update(data.get("gotcoins_balance", {}))
        economy.gotcoins_stats.clear()
        economy.gotcoins_stats.update(data.get("gotcoins_stats", {}))

        # Cooldowns
        cd = data.get("cooldowns", {"attack": {}, "heal": {}})
        cooldowns["attack"].clear(); cooldowns["attack"].update(cd.get("attack", {}))
        cooldowns["heal"].clear(); cooldowns["heal"].update(cd.get("heal", {}))

        # Statuts
        virus_status.clear(); virus_status.update(data.get("virus_status", {}))
        poison_status.clear(); poison_status.update(data.get("poison_status", {}))
        infection_status.clear(); infection_status.update(data.get("infection_status", {}))
        regeneration_status.clear(); regeneration_status.update(data.get("regeneration_status", {}))
        immunite_status.clear(); immunite_status.update(data.get("immunite_status", {}))
        burn_status.clear(); burn_status.update(data.get("burn_status", {}))

        # Buffs / malus
        shields.clear(); shields.update(data.get("shields", {}))
        esquive_status.clear(); esquive_status.update(data.get("esquive_status", {}))
        esquive_bonus.clear(); esquive_bonus.update(data.get("esquive_bonus", {}))
        casque_status.clear(); casque_status.update(data.get("casque_status", {}))
        resistance_bonus.clear(); resistance_bonus.update(data.get("resistance_bonus", {}))
        malus_degat.clear(); malus_degat.update(data.get("malus_degat", {}))

        # Divers progression
        last_daily_claim.clear(); last_daily_claim.update(data.get("last_daily_claim", {}))
        supply_data.clear(); supply_data.update(data.get("supply_data", {}))

        # Activité hebdo
        weekly_message_count.clear(); weekly_message_count.update(data.get("weekly_message_count", {}))
        weekly_voice_time.clear(); weekly_voice_time.update(data.get("weekly_voice_time", {}))
        weekly_message_log.clear(); weekly_message_log.update(data.get("weekly_message_log", {}))

        # Tirages
        tirages.clear(); tirages.update(data.get("tirages", {}))

        # Personnages
        personnages_equipés.clear(); personnages_equipés.update(data.get("personnages_equipés", {}))
        derniere_equip.clear(); derniere_equip.update(data.get("derniere_equip", {}))

        # Légendaires
        zeyra_last_survive_time.clear(); zeyra_last_survive_time.update(data.get("zeyra_last_survive_time", {}))
        valen_seuils.clear(); valen_seuils.update(data.get("valen_seuils", {}))

        print(
            f"✅ Données chargées depuis data.json : "
            f"{len(inventaire)} serveurs | {sum(len(u) for u in inventaire.values())} joueurs."
        )
    except json.JSONDecodeError:
        print("⚠️ Le fichier data.json est corrompu ou mal formé.")
    except Exception as e:
        print(f"❌ Erreur inattendue lors du chargement : {e}")

# ============================
# ✅ Import des personnages (optionnel)
# ============================

try:
    from personnage import PERSONNAGES  # noqa: F401
except Exception:
    PERSONNAGES = {}
    print("⚠️ Impossible d'importer les personnages depuis personnage.py")

# ============================
# ✅ Backups RAM indépendantes
# ============================

def backup_auto_independante():
    """
    Écrit un snapshot léger (RAM → fichier horodaté) dans AUTO_BACKUP_DIR,
    sans toucher au fichier principal data.json.
    """
    try:
        import economy
        os.makedirs(AUTO_BACKUP_DIR, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        path = os.path.join(AUTO_BACKUP_DIR, f"auto_backup_{timestamp}.json")

        data = {
            "inventaire": inventaire,
            "hp": hp,
            "leaderboard": leaderboard,
            "gotcoins_balance": economy.gotcoins_balance,
            "gotcoins_stats": economy.gotcoins_stats,
            "weekly_voice_time": weekly_voice_time,
            "weekly_message_log": weekly_message_log,
        }

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

        print(f"✅ Backup auto indépendante créée : {os.path.basename(path)}")
    except Exception as e:
        print(f"❌ Erreur lors de la backup auto indépendante : {e}")

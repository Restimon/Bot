import json
import os
import time
import shutil

from storage import inventaire, hp, leaderboard
from embeds import build_embed_from_item
from datetime import datetime

# ✅ Utilisation du disque persistant
PERSISTENT_PATH = "/persistent"
DATA_FILE = os.path.join(PERSISTENT_PATH, "data.json")
BACKUP_DIR = os.path.join(PERSISTENT_PATH, "backups")

# Cooldowns par action
cooldowns = {
    "attack": {},  # cooldowns["attack"][guild_id][user_id]
    "heal": {}     # cooldowns["heal"][(guild_id, user_id, target_id)]
}

# États persistants
virus_status = {}             # guild_id -> user_id -> {start_time, source, channel_id}
poison_status = {}            # idem
infection_status = {}         # idem
regeneration_status = {}      # idem
immunite_status = {}          # guild_id -> user_id -> expire_time
shields = {}                  # guild_id -> user_id -> valeur
esquive_bonus = {}            # guild_id -> user_id -> expire_time
casque_bonus = {}             # guild_id -> user_id -> True
last_daily_claim = {}         # guild_id -> user_id -> timestamp
supply_data = {}              # autres données diverses

def sauvegarder():
    try:
        os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
        os.makedirs(BACKUP_DIR, exist_ok=True)

        # 🔁 Créer une sauvegarde horodatée
        if os.path.exists(DATA_FILE):
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            backup_name = f"data_backup_{timestamp}.json"
            shutil.copy2(DATA_FILE, os.path.join(BACKUP_DIR, backup_name))

        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "inventaire": inventaire,
                "hp": hp,
                "leaderboard": leaderboard,
                "cooldowns": cooldowns,
                "virus_status": virus_status,
                "poison_status": poison_status,
                "infection_status": infection_status,
                "regeneration_status": regeneration_status,
                "immunite_status": immunite_status,
                "shields": shields,
                "esquive_bonus": esquive_bonus,
                "casque_status": casque_bonus,
                "last_daily_claim": last_daily_claim,
                "supply_data": supply_data
            }, f, indent=4, ensure_ascii=False)

        print("💾 Données sauvegardées avec backup horodaté.")
    except Exception as e:
        print(f"❌ Erreur lors de la sauvegarde : {e}")

def charger():
    """Charge toutes les données depuis le fichier JSON."""
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

        esquive_bonus.clear()
        esquive_bonus.update(data.get("esquive_bonus", {}))

        casque_bonus.clear()
        casque_bonus.update(data.get("casque_status", {}))

        supply_data.clear()
        supply_data.update(data.get("supply_data", {}))

        last_daily_claim.clear()
        last_daily_claim.update(data.get("last_daily_claim", {}))

        print(f"✅ Données chargées depuis data.json : {len(inventaire)} serveurs | {sum(len(u) for u in inventaire.values())} joueurs.")
    except json.JSONDecodeError:
        print("⚠️ Le fichier data.json est corrompu ou mal formé.")
    except Exception as e:
        print(f"❌ Erreur inattendue lors du chargement : {e}")

@bot.tree.command(name="backup", description="💾 Sauvegarde les données de ce serveur")
async def backup_server(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ Seuls les administrateurs peuvent utiliser cette commande.", ephemeral=True)

    try:
        from data import inventaire, hp, leaderboard
        guild_id = str(interaction.guild.id)

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        filename = f"data_backup_{guild_id}_{timestamp}.json"
        backup_path = os.path.join(BACKUP_DIR, filename)

        os.makedirs(BACKUP_DIR, exist_ok=True)

        data = {
            "inventaire": inventaire.get(guild_id, {}),
            "hp": hp.get(guild_id, {}),
            "leaderboard": leaderboard.get(guild_id, {}),
        }

        with open(backup_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

        await interaction.response.send_message(f"✅ Sauvegarde créée : `{filename}`", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Erreur : {e}", ephemeral=True)


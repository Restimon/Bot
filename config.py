import json
import os

CONFIG_FILE = "/persistent/config.json"
config = None 

def get_config():
    global config
    if config is None:
        load_config()
    return config

def load_config():
    """Charge la configuration depuis le fichier JSON. Initialise si absent ou invalide."""
    global config
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                config = json.load(f)
        except json.JSONDecodeError:
            print("⚠️ Erreur : config.json est corrompu. Recréation d'une configuration vide.")
            config = {}
        except Exception as e:
            print(f"❌ Erreur lors du chargement de config.json : {e}")
            config = {}
    else:
        print("ℹ️ Aucun fichier config.json trouvé. Initialisation d'une nouvelle configuration.")
        config = {}

def save_config():
    """Sauvegarde la configuration actuelle dans un fichier JSON."""
    try:
        os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)  
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
        print("💾 Configuration sauvegardée dans config.json")
    except Exception as e:
        print(f"❌ Erreur lors de la sauvegarde de la configuration : {e}")

def get_guild_config(guild_id: str) -> dict:
    """
    Récupère la configuration spécifique à un serveur Discord.
    Initialise l'entrée si elle n'existe pas.
    """
    cfg = get_config()
    cfg.setdefault(guild_id, {})
    return cfg[guild_id]

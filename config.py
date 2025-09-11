import json
import os
from typing import Any, Dict

CONFIG_FILE = "/persistent/config.json"
config: Dict[str, Any] | None = None

def get_config() -> Dict[str, Any]:
    """Retourne la config complète (globale + guilds)."""
    global config
    if config is None:
        load_config()
    return config

def load_config() -> None:
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

def save_config() -> None:
    """Sauvegarde la configuration actuelle dans un fichier JSON."""
    try:
        os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
        print("💾 Configuration sauvegardée dans config.json")
    except Exception as e:
        print(f"❌ Erreur lors de la sauvegarde de la configuration : {e}")

def get_guild_config(guild_id: str) -> Dict[str, Any]:
    """
    Récupère la configuration spécifique à un serveur Discord.
    Initialise l'entrée si elle n'existe pas.
    """
    cfg = get_config()
    cfg.setdefault(guild_id, {})
    return cfg[guild_id]

def get_value(key: str, default: Any = None) -> Any:
    """Récupère une valeur globale de config avec fallback."""
    return get_config().get(key, default)

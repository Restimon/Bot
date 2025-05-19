import json
import os

CONFIG_FILE = "config.json"
config = {}  # Structure attendue : {guild_id: {"leaderboard_channel_id": x, "leaderboard_message_id": y}}

def load_config():
    global config
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            config = json.load(f)
    else:
        config = {}

def save_config():
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4, ensure_ascii=False)

def get_guild_config(guild_id: str) -> dict:
    """Renvoie la config pour un serveur donné, ou l'initialise si absente."""
    config.setdefault(guild_id, {})
    return config[guild_id]

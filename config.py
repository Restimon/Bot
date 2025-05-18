import json
import os

CONFIG_FILE = "config.json"
config = {}

def load_config():
    global config
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            config = json.load(f)
    else:
        config = {}

def save_config():
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=4)

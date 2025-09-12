import os, json

DATA_DIR = "data"

FILES = {
    "players": os.path.join(DATA_DIR, "players.json"),
    "inventory": os.path.join(DATA_DIR, "inventory.json"),
    "effects": os.path.join(DATA_DIR, "effects.json"),
    "config": os.path.join(DATA_DIR, "config.json"),
}

def _load(path):
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def _save(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

# ── API publique ────────────────────────────────
def load_players(): return _load(FILES["players"])
def save_players(data): _save(FILES["players"], data)

def load_inventory(): return _load(FILES["inventory"])
def save_inventory(data): _save(FILES["inventory"], data)

def load_effects(): return _load(FILES["effects"])
def save_effects(data): _save(FILES["effects"], data)

def load_config(): return _load(FILES["config"])
def save_config(data): _save(FILES["config"], data)

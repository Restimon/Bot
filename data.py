# data/storage.py
from __future__ import annotations

import os
import io
import json
import time
import shutil
import asyncio
from typing import Any, Dict, Optional, Callable, Tuple, List
from datetime import datetime

# 📁 Emplacements de persistance
PERSISTENT_PATH = "/persistent"
DATA_FILE = os.path.join(PERSISTENT_PATH, "data.json")
BACKUP_DIR = os.path.join(PERSISTENT_PATH, "backups")
AUTO_BACKUP_DIR = os.path.join(PERSISTENT_PATH, "auto_backups")  # backups RAM indépendantes

# Réglages de rotation
MAX_BACKUPS = 20         # Manuels (backup_now)
MAX_AUTO_BACKUPS = 30    # Automatiques (sauvegardes tournantes)
AUTO_BACKUP_MIN_SPACING_SEC = 300  # évite de spammer l’auto-backup (5 min)

# Concurrence
_lock = asyncio.Lock()
_last_auto_backup_ts: float = 0.0

# -----------------------------------------------------------------------------
# Utilitaires fichiers
# -----------------------------------------------------------------------------
def _ensure_dirs() -> None:
    os.makedirs(PERSISTENT_PATH, exist_ok=True)
    os.makedirs(BACKUP_DIR, exist_ok=True)
    os.makedirs(AUTO_BACKUP_DIR, exist_ok=True)

def _timestamp() -> str:
    # 2025-09-05_13-06-44
    return datetime.utcnow().strftime("%Y-%m-%d_%H-%M-%S")

def _rotate(dirpath: str, keep: int) -> None:
    files = sorted(
        [os.path.join(dirpath, f) for f in os.listdir(dirpath)],
        key=lambda p: os.path.getmtime(os.path.join(dirpath, os.path.basename(p))),
        reverse=True,
    )
    for f in files[keep:]:
        try:
            os.remove(f)
        except Exception:
            pass

def _atomic_write_json(path: str, data: Dict[str, Any]) -> None:
    # écriture atomique via fichier temporaire
    tmp = f"{path}.tmp"
    with io.open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)

# -----------------------------------------------------------------------------
# Core API
# -----------------------------------------------------------------------------
async def init_storage() -> None:
    """À appeler au démarrage du bot (ex: dans on_ready/init db)."""
    _ensure_dirs()
    # si data.json absent, créer squelette
    if not os.path.exists(DATA_FILE):
        await save_data({})

async def load_data() -> Dict[str, Any]:
    """Charge tout le JSON. S’il est corrompu, tente un fallback depuis le dernier backup."""
    async with _lock:
        _ensure_dirs()
        if not os.path.exists(DATA_FILE):
            return {}

        try:
            with io.open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            # Essaye fallback depuis le backup le plus récent
            backups = sorted(
                [os.path.join(BACKUP_DIR, f) for f in os.listdir(BACKUP_DIR)],
                key=lambda p: os.path.getmtime(p),
                reverse=True,
            )
            for b in backups:
                try:
                    with io.open(b, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    # restaure
                    _atomic_write_json(DATA_FILE, data)
                    return data
                except Exception:
                    continue
            # si aucun backup valide
            return {}
        except Exception:
            return {}

async def save_data(data: Dict[str, Any], *, do_auto_backup: bool = True) -> None:
    """Sauvegarde **atomiquement** puis crée un auto-backup (rotatif)."""
    async with _lock:
        _ensure_dirs()
        _atomic_write_json(DATA_FILE, data)

        if do_auto_backup:
            await _auto_backup(data)

async def backup_now(tag: Optional[str] = None) -> str:
    """Crée un backup manuel (nom horodaté). Retourne le chemin du backup."""
    async with _lock:
        _ensure_dirs()
        data = await load_data()
        stamp = _timestamp()
        base = f"backup_{stamp}"
        if tag:
            safe_tag = "".join(ch for ch in tag if ch.isalnum() or ch in ("-", "_"))
            if safe_tag:
                base += f"_{safe_tag}"
        path = os.path.join(BACKUP_DIR, base + ".json")
        _atomic_write_json(path, data)
        _rotate(BACKUP_DIR, MAX_BACKUPS)
        return path

async def restore_from_backup(backup_path: str) -> bool:
    """Restaure data.json depuis un fichier de backup fourni."""
    async with _lock:
        if not os.path.isfile(backup_path):
            return False
        try:
            with io.open(backup_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            _atomic_write_json(DATA_FILE, data)
            return True
        except Exception:
            return False

# -----------------------------------------------------------------------------
# Sections pratiques (lecture/écriture partielle)
# -----------------------------------------------------------------------------
async def get_section(key: str, default: Any = None) -> Any:
    data = await load_data()
    return data.get(key, default)

async def set_section(key: str, value: Any) -> None:
    data = await load_data()
    data[key] = value
    await save_data(data)

async def update_section(key: str, patch: Dict[str, Any]) -> Dict[str, Any]:
    """Merge dict superficiel sur une section (dict)."""
    data = await load_data()
    cur = data.get(key, {})
    if not isinstance(cur, dict):
        cur = {}
    cur.update(patch or {})
    data[key] = cur
    await save_data(data)
    return cur

# -----------------------------------------------------------------------------
# Auto-backups
# -----------------------------------------------------------------------------
async def _auto_backup(current_data: Optional[Dict[str, Any]] = None) -> None:
    """Sauvegarde tournante dans AUTO_BACKUP_DIR, bridée par un spacing de quelques minutes."""
    global _last_auto_backup_ts
    now = time.time()
    if (now - _last_auto_backup_ts) < AUTO_BACKUP_MIN_SPACING_SEC:
        return

    try:
        data = current_data if current_data is not None else await load_data()
        stamp = _timestamp()
        path = os.path.join(AUTO_BACKUP_DIR, f"auto_{stamp}.json")
        _atomic_write_json(path, data)
        _rotate(AUTO_BACKUP_DIR, MAX_AUTO_BACKUPS)
        _last_auto_backup_ts = now
    except Exception:
        # On ne casse pas l’app si un auto-backup échoue
        pass

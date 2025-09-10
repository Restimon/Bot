# storage.py
from __future__ import annotations

from typing import Dict, List, Tuple, Any

# Mémoire vive (persistée via data.sauvegarder())
inventaire: Dict[str, Dict[str, List[Any]]] = {}   # {guild_id: {user_id: [objets (emoji str | {"personnage": nom})]}}
hp:         Dict[str, Dict[str, int]]        = {}  # {guild_id: {user_id: hp_value}}
leaderboard:Dict[str, Dict[str, Dict[str,int]]] = {
    # {guild_id: {user_id: {"degats": X, "soin": X, "kills": X, "morts": X}}}
}


# -----------------------------------------------------------------------------
# Internes
# -----------------------------------------------------------------------------
def _lb_default() -> Dict[str, int]:
    return {"degats": 0, "soin": 0, "kills": 0, "morts": 0}

def ensure_user(guild_id: str, user_id: str) -> Tuple[List[Any], int, Dict[str, int]]:
    """Garantit inventaire, hp, leaderboard pour (guild,user) et renvoie les refs."""
    gid, uid = str(guild_id), str(user_id)
    inv = inventaire.setdefault(gid, {}).setdefault(uid, [])
    pv  = hp.setdefault(gid, {}).setdefault(uid, 100)
    stats = leaderboard.setdefault(gid, {}).setdefault(uid, _lb_default().copy())
    # Correction de structure si besoin
    for k in ("degats", "soin", "kills", "morts"):
        stats.setdefault(k, 0)
    return inv, pv, stats


# -----------------------------------------------------------------------------
# Accès simples
# -----------------------------------------------------------------------------
def get_inventory(guild_id: str) -> Dict[str, List[Any]]:
    """Accès direct à l'inventaire complet d'un serveur."""
    return inventaire.setdefault(str(guild_id), {})

def get_leaderboard(guild_id: str) -> Dict[str, Dict[str, int]]:
    """Accès direct au leaderboard (stats de combat uniquement)."""
    return leaderboard.setdefault(str(guild_id), {})

def set_hp(guild_id: str, user_id: str, value: int) -> None:
    """Met à jour manuellement les PV d'un joueur (clamp 0..100)."""
    gid, uid = str(guild_id), str(user_id)
    hp.setdefault(gid, {})
    hp[gid][uid] = max(0, min(100, int(value)))


def get_user_data(guild_id: str, user_id: str) -> Tuple[List[Any], int, Dict[str, int]]:
    """
    Accès combiné complet aux données d'un joueur : (inventaire, PV, stats combat)
    - inventaire: list[emoji | {"personnage": nom}]
    - pv: int
    - stats: {"degats","soin","kills","morts"}
    """
    return ensure_user(guild_id, user_id)


# -----------------------------------------------------------------------------
# Inventaire: helpers pratiques
# -----------------------------------------------------------------------------
def add_item(guild_id: str, user_id: str, item: Any) -> None:
    """Ajoute un item (emoji str ou objet dict) à l'inventaire."""
    inv, _, _ = ensure_user(guild_id, user_id)
    inv.append(item)

def remove_item(guild_id: str, user_id: str, item: Any) -> bool:
    """Retire UNE occurrence de l'item s'il existe. Renvoie True si retiré."""
    inv, _, _ = ensure_user(guild_id, user_id)
    try:
        inv.remove(item)
        return True
    except ValueError:
        return False

def count_item(guild_id: str, user_id: str, item: Any) -> int:
    """Compte le nombre d'occurrences d'un item dans l'inventaire."""
    inv, _, _ = ensure_user(guild_id, user_id)
    return sum(1 for it in inv if it == item)


# -----------------------------------------------------------------------------
# Tickets & personnages (qualité de vie)
# -----------------------------------------------------------------------------
TICKET_EMOJI = "🎟️"

def get_ticket_count(guild_id: str, user_id: str) -> int:
    """Nombre de tickets de tirage possédés par l'utilisateur."""
    return count_item(guild_id, user_id, TICKET_EMOJI)

def ajouter_personnage(guild_id: str, user_id: str, nom_perso: str) -> None:
    """Ajoute un personnage (stocké sous forme d'objet dict) dans l'inventaire."""
    add_item(guild_id, user_id, {"personnage": nom_perso})

def get_collection(guild_id: str, user_id: str) -> Dict[str, int]:
    """
    Extrait la collection {nom_perso: quantité} depuis l'inventaire (sans side effects).
    """
    inv, _, _ = ensure_user(guild_id, user_id)
    coll: Dict[str, int] = {}
    for it in inv:
        if isinstance(it, dict) and "personnage" in it:
            nom = it["personnage"]
            coll[nom] = coll.get(nom, 0) + 1
    return coll


# -----------------------------------------------------------------------------
# Leaderboard (combat) — helpers mis à disposition
# -----------------------------------------------------------------------------
def update_leaderboard(
    guild_id: str,
    user_id: str,
    degats_add: int = 0,
    soin_add: int = 0,
    kill: int = 0,
    death: int = 0
) -> Dict[str, int]:
    """
    Met à jour les stats de combat d'un joueur.
    - degats_add: ajout aux dégâts infligés (≥0)
    - soin_add: ajout aux soins prodigués (≥0)
    - kill: +n kills
    - death: +n morts
    Renvoie l'objet stats mis à jour.
    """
    _, _, stats = ensure_user(guild_id, user_id)
    if degats_add:
        stats["degats"] = max(0, stats.get("degats", 0) + int(degats_add))
    if soin_add:
        stats["soin"] = max(0, stats.get("soin", 0) + int(soin_add))
    if kill:
        stats["kills"] = max(0, stats.get("kills", 0) + int(kill))
    if death:
        stats["morts"] = max(0, stats.get("morts", 0) + int(death))

    # Sauvegarde discrète (pas d’exception bloquante)
    try:
        from data import sauvegarder
        sauvegarder()
    except Exception:
        pass

    return stats


# Aliases pratiques utilisés par d’autres modules (combat.py, utils.py…)
def add_damage(guild_id: str, user_id: str, amount: int) -> Dict[str, int]:
    return update_leaderboard(guild_id, user_id, degats_add=max(0, int(amount)))

def add_heal(guild_id: str, user_id: str, amount: int) -> Dict[str, int]:
    return update_leaderboard(guild_id, user_id, soin_add=max(0, int(amount)))

def add_kill(guild_id: str, user_id: str, n: int = 1) -> Dict[str, int]:
    return update_leaderboard(guild_id, user_id, kill=max(0, int(n)))

def add_death(guild_id: str, user_id: str, n: int = 1) -> Dict[str, int]:
    return update_leaderboard(guild_id, user_id, death=max(0, int(n)))


# -----------------------------------------------------------------------------
# Reset serveur
# -----------------------------------------------------------------------------
def reset_guild_data(guild_id: str) -> None:
    """Réinitialise les données d’un serveur (inventaire / hp / leaderboard)."""
    gid = str(guild_id)
    inventaire[gid] = {}
    hp[gid] = {}
    leaderboard[gid] = {}

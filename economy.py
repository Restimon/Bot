# economy.py
from __future__ import annotations

# --- États en mémoire (persistés via data.sauvegarder) ----------------------

# {guild_id: {user_id: {"autre": X, "achats": X, ...}}}
gotcoins_stats: dict[str, dict[str, dict[str, int]]] = {}

# {guild_id: {user_id: balance_int}}
gotcoins_balance: dict[str, dict[str, int]] = {}

DEFAULT_STATS: dict[str, int] = {
    "autre": 0,   # gains génériques
    "achats": 0,  # dépenses (on additionne les montants dépensés)
    # Tu peux ajouter librement d'autres catégories: "combat", "box", "loot", ...
}

# ---------------------------------------------------------------------------
# Init & helpers
# ---------------------------------------------------------------------------

def init_gotcoins_stats(guild_id: str, user_id: str) -> None:
    gid, uid = str(guild_id), str(user_id)
    gotcoins_stats.setdefault(gid, {}).setdefault(uid, DEFAULT_STATS.copy())
    gotcoins_balance.setdefault(gid, {}).setdefault(uid, 0)

def _stats(guild_id: str, user_id: str) -> dict[str, int]:
    init_gotcoins_stats(guild_id, user_id)
    return gotcoins_stats[str(guild_id)][str(user_id)]

def _balance_ref(guild_id: str) -> dict[str, int]:
    gotcoins_balance.setdefault(str(guild_id), {})
    return gotcoins_balance[str(guild_id)]

# ---------------------------------------------------------------------------
# Accès & vérifications
# ---------------------------------------------------------------------------

def get_gotcoins(guild_id: str, user_id: str) -> int:
    """Alias utilitaire (utilisé par /shop)."""
    return get_balance(guild_id, user_id)

def get_balance(guild_id: str, user_id: str) -> int:
    init_gotcoins_stats(guild_id, user_id)
    return gotcoins_balance[str(guild_id)][str(user_id)]

def can_afford(guild_id: str, user_id: str, amount: int) -> bool:
    if amount <= 0:
        return True
    return get_balance(guild_id, user_id) >= amount

# ---------------------------------------------------------------------------
# Ajout / retrait
# ---------------------------------------------------------------------------

def add_gotcoins(guild_id: str, user_id: str, amount: int, category: str = "autre") -> None:
    """
    Crédite 'amount' au solde et journalise le gain dans 'category'.
    amount <= 0 → ignoré (utilise remove_gotcoins pour dépenser).
    """
    if amount <= 0:
        return

    gid, uid = str(guild_id), str(user_id)
    init_gotcoins_stats(gid, uid)

    # Solde
    gotcoins_balance[gid][uid] += int(amount)

    # Stats de gain
    st = _stats(gid, uid)
    st[category] = st.get(category, 0) + int(amount)

    # Sauvegarde
    try:
        from data import sauvegarder
        sauvegarder()
    except Exception:
        pass  # safe during early imports

def ajouter_gotcoins(guild_id: str, user_id: str, amount: int, category: str = "autre") -> None:
    """Alias FR (utilisé par /shop, /special_supply, etc.)."""
    add_gotcoins(guild_id, user_id, amount, category)

def add_gotcoins_with_passif(guild_id: str, user_id: str, amount: int, category: str = "autre") -> None:
    """
    Ajoute un gain puis applique un éventuel bonus de passif (ex: Silien Dorr).
    Import paresseux pour éviter les imports circulaires.
    """
    if amount <= 0:
        return

    add_gotcoins(guild_id, user_id, amount, category)

    try:
        # API suggérée côté passifs (si différente, adapte le nom)
        from passifs import appliquer_passif_utilisateur
        res = appliquer_passif_utilisateur(
            str(guild_id), str(user_id),
            "gain_gotcoins",
            {"guild_id": str(guild_id), "user_id": str(user_id),
             "category": category, "montant": amount}
        )
        if isinstance(res, dict) and "gotcoins_bonus" in res:
            bonus = int(res["gotcoins_bonus"])
            if bonus > 0:
                add_gotcoins(guild_id, user_id, bonus, category)
                print(f"💠 Bonus passif: +{bonus} GC pour {user_id}")
    except Exception:
        # Passifs non dispo: on ignore proprement
        pass

def remove_gotcoins(guild_id: str, user_id: str, amount: int, log_as_purchase: bool = True) -> None:
    """
    Débite 'amount' du solde. Si log_as_purchase=True, on incrémente la
    catégorie 'achats' (suivi des dépenses cumulées).
    """
    if amount <= 0:
        return

    gid, uid = str(guild_id), str(user_id)
    init_gotcoins_stats(gid, uid)

    # Débit (plancher 0)
    cur = gotcoins_balance[gid][uid]
    gotcoins_balance[gid][uid] = max(0, cur - int(amount))

    # Log des dépenses
    if log_as_purchase:
        st = _stats(gid, uid)
        st["achats"] = st.get("achats", 0) + int(amount)

    try:
        from data import sauvegarder
        sauvegarder()
    except Exception:
        pass

def retirer_gotcoins(guild_id: str, user_id: str, amount: int) -> None:
    """Alias FR (utilisé par /shop)."""
    remove_gotcoins(guild_id, user_id, amount, log_as_purchase=True)

# ---------------------------------------------------------------------------
# Stats & totaux
# ---------------------------------------------------------------------------

def get_gotcoins_stats(guild_id: str, user_id: str) -> dict[str, int]:
    """
    Renvoie l'objet stats de l'utilisateur (catégories).
    Exemple: {"autre": 40, "achats": 30, "combat": 50, ...}
    """
    return _stats(guild_id, user_id).copy()

def get_total_gotcoins_earned(guild_id: str, user_id: str) -> int:
    """
    Total cumulé des gains (toutes catégories **sauf** 'achats').
    Sert pour “GotCoins totaux (carrière)”.
    """
    st = _stats(guild_id, user_id)
    return sum(v for k, v in st.items() if k != "achats")

# ---------------------------------------------------------------------------
# Gains liés aux messages (utilisé par main.py)
# ---------------------------------------------------------------------------

def compute_message_gains(message_len: int = 0, has_attachments: bool = False) -> int:
    """
    Petit gain d’activité:
      - 0 GC pour < 10 caractères
      - 1 GC pour 10–80
      - 2 GC au-delà de 80
      - +1 GC si pièce jointe
      - clamp [0, 5]
    """
    base = 0
    if message_len >= 80:
        base = 2
    elif message_len >= 10:
        base = 1
    if has_attachments:
        base += 1
    return max(0, min(5, base))

# economy.py
import random
from passifs import appliquer_passif  # ✅ Gestion des passifs

# {guild_id: {user_id: {"autre": X, "achats": X, ...}}}
gotcoins_stats = {}

# {guild_id: {user_id: balance_int}}
gotcoins_balance = {}

DEFAULT_STATS = {
    "autre": 0,    # gains génériques
    "achats": 0,   # dépenses (on additionne les montants dépensés)
    # Tu peux librement ajouter d'autres catégories de gain :
    # "combat": 0, "box": 0, "loot": 0, "ventes": 0, etc.
}

# ---------------------------------------------------------------------------
# Init & helpers
# ---------------------------------------------------------------------------

def init_gotcoins_stats(guild_id: str, user_id: str):
    gid, uid = str(guild_id), str(user_id)
    gotcoins_stats.setdefault(gid, {}).setdefault(uid, DEFAULT_STATS.copy())
    gotcoins_balance.setdefault(gid, {}).setdefault(uid, 0)

def _stats(guild_id: str, user_id: str) -> dict:
    init_gotcoins_stats(guild_id, user_id)
    return gotcoins_stats[str(guild_id)][str(user_id)]

def _balance_ref(guild_id: str, user_id: str) -> dict:
    init_gotcoins_stats(guild_id, user_id)
    return gotcoins_balance[str(guild_id)]

# ---------------------------------------------------------------------------
# Accès & vérifications
# ---------------------------------------------------------------------------

def get_gotcoins(guild_id: str, user_id: str) -> int:
    """Alias utilité (utilisé par /shop)."""
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

def add_gotcoins(guild_id: str, user_id: str, amount: int, category: str = "autre"):
    """
    Ajoute des GotCoins au solde et log le gain dans la catégorie.
    amount <= 0 : ignoré (utilise remove_gotcoins pour dépenser).
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

    # ✅ Sauvegarde
    from data import sauvegarder  # import local pour éviter les imports circulaires
    sauvegarder()

def ajouter_gotcoins(guild_id: str, user_id: str, amount: int, category: str = "autre"):
    """Alias francisé utilisé par /shop, /special_supply, etc."""
    add_gotcoins(guild_id, user_id, amount, category)

def add_gotcoins_with_passif(guild_id: str, user_id: str, amount: int, category: str = "autre"):
    """
    Ajoute un gain puis applique un éventuel bonus de passif (ex : Alphonse, Silien...).
    """
    if amount <= 0:
        return

    # Gain normal
    add_gotcoins(guild_id, user_id, amount, category)

    # Vérifie les passifs de gain
    res = appliquer_passif({
        "nom": None  # le dispatcher interne n'utilise pas ce champ ici
    }, "gain_gotcoins", {
        "guild_id": str(guild_id),
        "user_id": str(user_id),
        "category": category,
        "montant": amount
    })
    if res and "gotcoins_bonus" in res:
        bonus = int(res["gotcoins_bonus"])
        add_gotcoins(guild_id, user_id, bonus, category)
        print(f"💠 Bonus passif appliqué : +{bonus} GotCoins pour {user_id}")

def remove_gotcoins(guild_id: str, user_id: str, amount: int, log_as_purchase: bool = True):
    """
    Retire des GotCoins du solde. Si log_as_purchase=True, on trace la dépense
    dans la catégorie 'achats' (additionne le montant positif dépensé).
    """
    if amount <= 0:
        return

    gid, uid = str(guild_id), str(user_id)
    init_gotcoins_stats(gid, uid)

    # Solde (plancher 0)
    cur = gotcoins_balance[gid][uid]
    gotcoins_balance[gid][uid] = max(0, cur - int(amount))

    # Log dépenses
    if log_as_purchase:
        st = _stats(gid, uid)
        st["achats"] = st.get("achats", 0) + int(amount)

    from data import sauvegarder
    sauvegarder()

def retirer_gotcoins(guild_id: str, user_id: str, amount: int):
    """Alias francisé (utilisé par /shop)."""
    remove_gotcoins(guild_id, user_id, amount, log_as_purchase=True)

# ---------------------------------------------------------------------------
# Stats & totaux
# ---------------------------------------------------------------------------

def get_gotcoins_stats(guild_id: str, user_id: str) -> dict:
    """
    Renvoie l'objet stats de l'utilisateur (catégories).
    Exemple: {"autre": 40, "achats": 30, "combat": 50, ...}
    """
    return _stats(guild_id, user_id).copy()

def get_total_gotcoins_earned(guild_id: str, user_id: str) -> int:
    """
    Total cumulé des gains (toutes catégories **sauf** 'achats').
    Sert pour les classements (profile.py / stats.py).
    """
    st = _stats(guild_id, user_id)
    return sum(v for k, v in st.items() if k != "achats")

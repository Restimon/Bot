# data/personnage.py
from __future__ import annotations
from typing import Dict, Any, List, Optional

"""
Bridge vers le fichier racine `personnage.py`.

Expose :
- PERSONNAGES_LIST : List[Dict[str, Any]] (normalisée)
- PERSONNAGES, PASSIF_CODE_MAP, trouver, get_tous_les_noms

La normalisation ajoute des champs manquants et met invocable=True
par défaut pour éviter que certains cogs filtrent tout à vide.
"""

# ─────────────────────────────────────────────────────────────
# Import source (racine)
# ─────────────────────────────────────────────────────────────
try:
    from personnage import (
        PERSONNAGES,         # Dict[str, Dict[str, Any]]
        PASSIF_CODE_MAP,     # Dict[str, str]
        trouver,             # (q: str) -> Optional[Dict[str, Any]]
        get_tous_les_noms,   # () -> List[str]
    )
except Exception:
    # Fallback minimal si le module racine n'est pas dispo
    PERSONNAGES: Dict[str, Dict[str, Any]] = {}
    PASSIF_CODE_MAP: Dict[str, str] = {}

    def trouver(q: str) -> Optional[Dict[str, Any]]:
        q = (q or "").strip().lower()
        for nom, p in PERSONNAGES.items():
            if q in nom.lower():
                f = dict(p)
                f.setdefault("nom", nom)
                return f
        return None

    def get_tous_les_noms() -> List[str]:
        return list(PERSONNAGES.keys())

# ─────────────────────────────────────────────────────────────
# Normalisation des fiches
# ─────────────────────────────────────────────────────────────
def _normalize_fiche(nom: str, raw: Any) -> Dict[str, Any]:
    """
    S’assure que chaque fiche a :
      - nom (str)
      - rarete (str, défaut "Commun")
      - faction (str, défaut "GotValis")
      - passif: {nom:str, effet:str}
      - invocable: bool (défaut True)
      - key interne optionnelle (identique au nom), utile à certains cogs
    """
    f: Dict[str, Any] = dict(raw) if isinstance(raw, dict) else {}
    f.setdefault("nom", nom)
    f.setdefault("rarete", "Commun")
    f.setdefault("faction", "GotValis")
    # structure de passif
    p = f.get("passif")
    if not isinstance(p, dict):
        p = {}
    p.setdefault("nom", f.get("passif_nom", "Passif"))
    p.setdefault("effet", f.get("passif_effet", ""))
    f["passif"] = p
    # clé interne et invocabilité
    f.setdefault("key", nom)
    f.setdefault("invocable", True)  # <— important : défaut True
    return f

def _to_list(src: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for nom, p in (src or {}).items():
        out.append(_normalize_fiche(nom, p))
    return out

# ─────────────────────────────────────────────────────────────
# Exports
# ─────────────────────────────────────────────────────────────
PERSONNAGES_LIST: List[Dict[str, Any]] = _to_list(PERSONNAGES)

# petit log de debug (facultatif) : combien de persos chargés
if not PERSONNAGES_LIST:
    # Utilise print pour qu'on voie quelque chose dans les logs Render
    print("[data.personnage] ATTENTION: PERSONNAGES_LIST est vide. "
          "Vérifie `personnage.py` (PERSONNAGES) ou les chemins d'import.")

__all__ = [
    "PERSONNAGES_LIST",
    "PERSONNAGES",
    "PASSIF_CODE_MAP",
    "trouver",
    "get_tous_les_noms",
]

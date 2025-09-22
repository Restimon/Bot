# data/personnage.py
from __future__ import annotations
from typing import Dict, Any, List, Optional

"""
Pont vers le fichier racine `personnage.py`.

- Importe PERSONNAGES (dict {nom: fiche}) et divers helpers.
- Construit PERSONNAGES_LIST (liste de fiches), pour compatibilité
  avec les anciens cogs qui l’attendent depuis data.personnage.
"""

try:
    # Ton module racine avec toutes les définitions
    from personnage import (
        PERSONNAGES,         # Dict[str, Dict[str, Any]]
        PASSIF_CODE_MAP,     # Dict[str, str]
        trouver,             # (q: str) -> Optional[Dict[str, Any]]
        get_tous_les_noms,   # () -> List[str]
    )
except Exception:
    # Fallback ultra minimal (au cas où le module racine n'est pas dispo au runtime)
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


def _to_list(src: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Convertit le dict PERSONNAGES {nom: {...}} en liste de fiches
    [{nom, rarete, faction, passif, ...}] comme certains cogs l’attendent.
    Garantit que la clé 'nom' est toujours présente dans chaque fiche.
    """
    out: List[Dict[str, Any]] = []
    for nom, p in (src or {}).items():
        fiche = dict(p) if isinstance(p, dict) else {}
        fiche.setdefault("nom", nom)
        out.append(fiche)
    return out


# Ce que des cogs importent depuis data.personnage :
PERSONNAGES_LIST: List[Dict[str, Any]] = _to_list(PERSONNAGES)

# On ré-exporte aussi ces symboles pour convenance
__all__ = [
    "PERSONNAGES_LIST",
    "PERSONNAGES",
    "PASSIF_CODE_MAP",
    "trouver",
    "get_tous_les_noms",
]

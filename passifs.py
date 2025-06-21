def appliquer_passif(personnage, contexte, données):
    """
    Applique l’effet du passif du personnage selon le contexte.
    
    Args:
        personnage (dict): Contient les infos du personnage, dont 'nom'.
        contexte (str): Type d’action (ex: "attaque", "defense", "soin", etc.)
        données (dict): Infos utiles pour le traitement (PV, dégâts, cible, etc.)

    Returns:
        dict ou None : Un dictionnaire décrivant l’effet à appliquer, ou None s’il n’y a pas d’effet.
    """
    nom = personnage.get("nom")

    if nom == "Zeyra Kael":
        return passif_zeyra_kael(contexte, données)
    elif nom == "Valen Drexar":
        return passif_valen_drexar(contexte, données)
    elif nom == "Maître d’Hôtel":
        return passif_maitre_hotel(contexte, données)

    # ➕ Ajouter ici les autres personnages à mesure
    return None


# ----------------------------
# 🔽 Définir chaque passif ici
# ----------------------------

def passif_zeyra_kael(contexte, données):
    # TODO : Implémenter l'effet de Zeyra
    return None

def passif_valen_drexar(contexte, données):
    # TODO : Implémenter l'effet de Valen
    return None

def passif_maitre_hotel(contexte, données):
    # TODO : Implémenter l'effet du Maître d’Hôtel
    return None

# ➕ Ajouter d’autres fonctions à mesure (ex : passif_varkhel_drayne, etc.)


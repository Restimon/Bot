RARETES = ["Commun", "Rare", "Épique", "Légendaire"]
FACTION_ORDER = ["Monarchie", "Gouvernement", "Citoyen", "GotValis", "Hôtel Dormant", "La Fracture", "Infection"]

PERSONNAGES = [

  #Fracture
    {
        "nom": "Niv Kress",
        "rarete": "Commun",
        "faction": "La Fracture",
        "phrase": "Si je te prends un truc… je te prends sûrement un autre sans que tu le saches.",
        "passif": {
            "nom": "Vol opportuniste 🪙",
            "effet": "Lorsqu’il utilise un objet de type \"vol\", Niv a 10 % de chance de voler un deuxième objet aléatoire dans l’inventaire de la cible."
        },
        "image": "fccf91de-f3e2-43ab-966a-24607a9ebf2c.png"
    },
    
    {
        "nom": "Lior Danen",
        "rarete": "Commun",
        "faction": "Citoyen",
        "phrase": "Tu veux que ça arrive vite, en silence, et sans poser de questions ? C’est moi.",
        "passif": {
            "nom": "Récompense fantôme 📦",
            "effet": "A 5% de chance de doubler les récompenses Daily."
        },
        "image": ""  # Remplace par le nom réel du fichier image si tu l'as
    }


]


def get_par_rarete(rarete):
    """Retourne tous les personnages d'une rareté, triés par faction."""
    return sorted(
        [p for p in PERSONNAGES if p["rarete"] == rarete],
        key=lambda p: FACTION_ORDER.index(p.get("faction", ""))
    )


def get_par_nom(nom):
    """Retourne un personnage selon son nom exact."""
    return next((p for p in PERSONNAGES if p["nom"] == nom), None)


def get_tous_les_noms():
    """Retourne la liste des noms de tous les personnages."""
    return [p["nom"] for p in PERSONNAGES]

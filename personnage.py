RARETES = ["Commun", "Rare", "Épique", "Légendaire"]
FACTION_ORDER = ["Monarchie", "Gouvernement", "Citoyen", "GotValis", "Hôtel Dormant", "La Fracture", "Infection"]

PERSONNAGES = [


    # Gouvernement 
    {
        "nom": "Cassian Vale",
        "rarete": "Commun",
        "faction": "Gouvernement",
        "description": "Je ne représente pas un homme. Je représente un système.",
        "passif": {
            "nom": "Éloquence officielle 🕊️",
            "effet": "+1 % de résistance durant 24h pour chaque attaque reçue."
        },
        "image": "assets/personnage/Cassian Vale.png"
    },
    {
        "nom": "Darin Venhal",
        "rarete": "Commun",
        "faction": "Gouvernement",
        "description": "Je ferai mes preuves... tôt ou tard !",
        "passif": {
            "nom": "Volonté mal orientée 💼",
            "effet": "10 % de chance de réduire les dégâts entrants de moitié."
        },
        "image": "assets/personnage/Darin Venhal.png"
    },
    {
        "nom": "Elwin Jarr",
        "rarete": "Commun",
        "faction": "Gouvernement",
        "description": "Je fais ce qu’on me dit. Et je le fais bien.",
        "passif": {
            "nom": "Archivage parfait 📑",
            "effet": "L'objet 'vol' a 10 % de chance de voler un deuxième item."
        },
        "image": "assets/personnage/Elwin Jarr.png"
    },
    {
        "nom": "Liora Venhal",
        "rarete": "Commun",
        "faction": "Gouvernement",
        "description": "Je ne veux pas d’ennuis... mais je sais qui appeler si j’en ai.",
        "passif": {
            "nom": "Protection implicite 👑",
            "effet": "Chaque attaque reçue a 25 % de chance d’augmenter son esquive de 3 % pendant 24h."
        },
        "image": "assets/personnage/Liora Venhal.png"
    },
    {
        "nom": "Maelis Dorné",
        "rarete": "Commun",
        "faction": "Gouvernement",
        "description": "Les souvenirs s'effacent. Les documents, eux, restent.",
        "passif": {
            "nom": "Mémoire d'État 📚",
            "effet": "+1 % de chance d’être purgé d’un effet toutes les heures."
        },
        "image": "assets/personnage/Maelis Dorné.png"
    }

    # Citoyens
    {
        "nom": "Lior Danen",
        "rarete": "Commun",
        "faction": "Citoyen",
        "description": "Tu veux que ça arrive vite, en silence, et sans poser de questions ? C’est moi.",
        "passif": {
            "nom": "Récompense fantôme 📦",
            "effet": "A 5% de chance de doubler les récompenses Daily."
        },
        "image": "assets/personnage/Lior Danen.png"
    },
    {
        "nom": "Nael Mirren",
        "rarete": "Commun",
        "faction": "Citoyen",
        "description": "Toujours souriant, toujours bien habillé — mais ne vous fiez pas à son apparence douce.",
        "passif": {
            "nom": "Écho de Grâce 🎁",
            "effet": "A 1% de chance d'augmenter la rareté de votre prochain tirage."
        },
        "image": "assets/personnage/Nael Mirren.png"
    },
    {
        "nom": "Niv Kress",
        "rarete": "Commun",
        "faction": "La Fracture",
        "description": "Si je te prends un truc… je te prends sûrement un autre sans que tu le saches.",
        "passif": {
            "nom": "Vol opportuniste 🪙",
            "effet": "Lorsqu’il utilise un objet de type \"vol\", Niv a 10 % de chance de voler un deuxième objet aléatoire dans l’inventaire de la cible."
        },
        "image": "assets/personnage/Niv Kress.png"
    },
    {
        "nom": "Lyss Tenra",
        "rarete": "Commun",
        "faction": "Citoyen",
        "description": "Je garde mes trésors ici… pas dans mes poches.",
        "passif": {
            "nom": "Intouchable 🛡",
            "effet": "Immunisée à tous les effets de vol."
        },
        "image": "assets/personnage/Lyss Tenra.png"
    },
    {
        "nom": "Mira Oskra",
        "rarete": "Commun",
        "faction": "Citoyen",
        "description": "Ce que les autres piétinent, je le transforme en lame.",
        "passif": {
            "nom": "Éclats recyclés 🔪",
            "effet": "Si elle subit une attaque mais reste en vie, elle a 3 % de chance de générer un objet entre « boule de neige, boule de feu ou trèfle »."
        },
        "image": "assets/personnage/Mira Oskra.png"
    },
    {
        "nom": "Sel Varnik",
        "rarete": "Commun",
        "faction": "Citoyen",
        "description": "Je vends des objets… et parfois des vérités, si t’as de quoi payer.",
        "passif": {
            "nom": "Vendeur rusé 💰",
            "effet": "Vend les objets 25 % plus cher."
        },
        "image": "assets/personnage/Sel Varnik.png"
    }

    # GotValis
    {
        "nom": "Cielya Morn",
        "rarete": "Commun",
        "faction": "GotValis",
        "description": "Vous êtes bien sur le réseau GotValis. Tout ce que vous dites sera traité... ou non.",
        "passif": {
            "nom": "Filtrage actif 🎧",
            "effet": "Tant que le porteur a un PB, les dégâts sont diminués de 25 %."
        },
        "image": "assets/personnage/Cielya Morn.png"
    },
    {
        "nom": "Kevar Rin",
        "rarete": "Commun",
        "faction": "GotValis",
        "description": "J’efface les traces. Peu importe ce qu’il y avait avant.",
        "passif": {
            "nom": "Zone propre 🧼",
            "effet": "Inflige 3 dégâts supplémentaires aux personnes infectées."
        },
        "image": "assets/personnage/Kevar Rin.png"
    },
    {
        "nom": "Lysha Varn",
        "rarete": "Commun",
        "faction": "GotValis",
        "description": "Si vous ne les entendez pas crier… c’est grâce à moi.",
        "passif": {
            "nom": "Champ brouillé 📡",
            "effet": "Dès que le porteur soigne quelqu’un, il gagne 1 PB."
        },
        "image": "assets/personnage/Lysha Varn.png"
    },
    {
        "nom": "Kerin Dross",
        "rarete": "Commun",
        "faction": "GotValis",
        "description": "Je n’interviens jamais. Je note.",
        "passif": {
            "nom": "Observation continue 📹",
            "effet": "A 5 % de chance de se faire soigner de 1 PV quand quelqu’un est soigné."
        },
        "image": "assets/personnage/Kerin Dross.png"
    },
    {
        "nom": "Nova Rell",
        "rarete": "Commun",
        "faction": "GotValis",
        "description": "Moteur prêt. Si t’arrives pas à me suivre… c’est pas mon problème.",
        "passif": {
            "nom": "Réflexes Accélérés 🚗💨",
            "effet": "+5 % de chance d’esquiver toutes les attaques."
        },
        "image": "assets/personnage/Nova Rell.png"
    },
    {
        "nom": "Raya Nys",
        "rarete": "Commun",
        "faction": "GotValis",
        "description": "J’augmente la tolérance. Vous encaissez le reste.",
        "passif": {
            "nom": "Cadence de surcharge 🛡",
            "effet": "Augmente la capacité maximale de PB à 25 au lieu de 20."
        },
        "image": "assets/personnage/Raya Nys.png"
    },
    {
        "nom": "Tessa Korrin",
        "rarete": "Commun",
        "faction": "GotValis",
        "description": "Les vivants coûtent moins cher que les morts. Alors je vous garde en vie.",
        "passif": {
            "nom": "Injection stabilisante 💉",
            "effet": "Les soins prodigués rendent +1 PV."
        },
        "image": "assets/personnage/Tessa Korrin.png"
    },

    # La Fracture
    {
        "nom": "Niv Kress",
        "rarete": "Commun",
        "faction": "La Fracture",
        "description": "Si je te prends un truc… je te prends sûrement un autre sans que tu le saches.",
        "passif": {
            "nom": "Vol opportuniste 🪙",
            "effet": "Lorsqu’il utilise un objet de type \"vol\", Niv a 10 % de chance de voler un deuxième objet aléatoire dans l’inventaire de la cible."
        },
        "image": "assets/personnage/Niv Kress.png"
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

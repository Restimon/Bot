# personnage.py
# ─────────────────────────────────────────────────────────────────────────────
# Module de données + petites utilitaires autour des personnages.
# - Données : PERSONNAGES_LIST (inchangée), PERSONNAGES (index par nom)
# - Helpers : slug, recherche par nom/slug, listes par rareté/faction,
#   tirage aléatoire, validation douce.
# - Sans dépendance externe (standard lib uniquement).
# ─────────────────────────────────────────────────────────────────────────────

from __future__ import annotations
import random
import unicodedata
from typing import Dict, List, Optional, Tuple

# ─────────────────────────────────────────────────────────────────────────────
# Constantes / Ordres
# ─────────────────────────────────────────────────────────────────────────────

RARETES: List[str] = ["Commun", "Rare", "Épique", "Légendaire"]
FACTION_ORDER: List[str] = ["Monarchie", "Gouvernement", "Citoyen", "GotValis", "Hôtel Dormant", "La Fracture", "Infection"]

# Poids par rareté pour un futur système de tirage (modifiable selon besoin)
RARETE_WEIGHTS: Dict[str, int] = {
    "Commun": 70,
    "Rare": 22,
    "Épique": 7,
    "Légendaire": 1,
}

# ─────────────────────────────────────────────────────────────────────────────
# Données
# ─────────────────────────────────────────────────────────────────────────────

PERSONNAGES_LIST: List[Dict] = [

    # Gouvernement
    {
        "nom": "Cassiane Vale",
        "rarete": "Commun",
        "faction": "Gouvernement",
        "description": "Je ne représente pas un homme. Je représente un système.",
        "passif": {"nom": "Éloquence officielle 🕊️", "effet": "+1 % de résistance durant 24h pour chaque attaque reçue."},
        "image": "assets/personnage/Cassiane Vale.png",
    },
    {
        "nom": "Darin Venhal",
        "rarete": "Commun",
        "faction": "Gouvernement",
        "description": "Je ferai mes preuves... tôt ou tard !",
        "passif": {"nom": "Volonté mal orientée 💼", "effet": "10 % de chance de réduire les dégâts entrants de moitié."},
        "image": "assets/personnage/Darin Venhal.png",
    },
    {
        "nom": "Elwin Jarr",
        "rarete": "Commun",
        "faction": "Gouvernement",
        "description": "Je fais ce qu’on me dit. Et je le fais bien.",
        "passif": {"nom": "Archivage parfait 📑", "effet": "L'objet 'vol' a 10 % de chance de voler un deuxième item."},
        "image": "assets/personnage/Elwin Jarr.png",
    },
    {
        "nom": "Liora Venhal",
        "rarete": "Commun",
        "faction": "Gouvernement",
        "description": "Je ne veux pas d’ennuis... mais je sais qui appeler si j’en ai.",
        "passif": {"nom": "Protection implicite 👑", "effet": "Chaque attaque reçue a 25 % de chance d’augmenter son esquive de 3 % pendant 24h."},
        "image": "assets/personnage/Liora Venhal.png",
    },
    {
        "nom": "Maelis Dorné",
        "rarete": "Commun",
        "faction": "Gouvernement",
        "description": "Les souvenirs s'effacent. Les documents, eux, restent.",
        "passif": {"nom": "Mémoire d'État 📚", "effet": "+1 % de chance d’être purgé d’un effet toutes les heures."},
        "image": "assets/personnage/Maelis Dorné.png",
    },

    # Citoyens
    {
        "nom": "Lior Danen",
        "rarete": "Commun",
        "faction": "Citoyen",
        "description": "Tu veux que ça arrive vite, en silence, et sans poser de questions ? C’est moi.",
        "passif": {"nom": "Récompense fantôme 📦", "effet": "A 5% de chance de doubler les récompenses Daily."},
        "image": "assets/personnage/Lior Danen.png",
    },
    {
        "nom": "Nael Mirren",
        "rarete": "Commun",
        "faction": "Citoyen",
        "description": "Toujours souriant, toujours bien habillé — mais ne vous fiez pas à son apparence douce.",
        "passif": {"nom": "Écho de Grâce 🎁", "effet": "A 1% de chance d'augmenter la rareté de votre prochain tirage."},
        "image": "assets/personnage/Nael Mirren.png",
    },
    {
        "nom": "Niv Kress",
        "rarete": "Commun",
        "faction": "La Fracture",
        "description": "Si je te prends un truc… je te prends sûrement un autre sans que tu le saches.",
        "passif": {"nom": "Vol opportuniste 🪙", "effet": "Lorsqu’il utilise un objet de type \"vol\", Niv a 10 % de chance de voler un deuxième objet aléatoire dans l’inventaire de la cible."},
        "image": "assets/personnage/Niv Kress.png",
    },
    {
        "nom": "Lyss Tenra",
        "rarete": "Commun",
        "faction": "Citoyen",
        "description": "Je garde mes trésors ici… pas dans mes poches.",
        "passif": {"nom": "Intouchable 🛡", "effet": "Immunisée à tous les effets de vol."},
        "image": "assets/personnage/Lyss Tenra.png",
    },
    {
        "nom": "Mira Oskra",
        "rarete": "Commun",
        "faction": "Citoyen",
        "description": "Ce que les autres piétinent, je le transforme en lame.",
        "passif": {"nom": "Éclats recyclés 🔪", "effet": "Si elle subit une attaque mais reste en vie, elle a 3 % de chance de générer un objet entre « boule de neige, boule de feu ou trèfle »."},
        "image": "assets/personnage/Mira Oskra.png",
    },
    {
        "nom": "Sel Varnik",
        "rarete": "Commun",
        "faction": "Citoyen",
        "description": "Je vends des objets… et parfois des vérités, si t’as de quoi payer.",
        "passif": {"nom": "Vendeur rusé 💰", "effet": "Vend les objets 25 % plus cher."},
        "image": "assets/personnage/Sel Varnik.png",
    },

    # GotValis
    {
        "nom": "Cielya Morn",
        "rarete": "Commun",
        "faction": "GotValis",
        "description": "Vous êtes bien sur le réseau GotValis. Tout ce que vous dites sera traité... ou non.",
        "passif": {"nom": "Filtrage actif 🎧", "effet": "Tant que le porteur a un PB, les dégâts sont diminués de 25 %."},
        "image": "assets/personnage/Cielya Morn.png",
    },
    {
        "nom": "Kevar Rin",
        "rarete": "Commun",
        "faction": "GotValis",
        "description": "J’efface les traces. Peu importe ce qu’il y avait avant.",
        "passif": {"nom": "Zone propre 🧼", "effet": "Inflige 3 dégâts supplémentaires aux personnes infectées."},
        "image": "assets/personnage/Kevar Rin.png",
    },
    {
        "nom": "Lysha Varn",
        "rarete": "Commun",
        "faction": "GotValis",
        "description": "Si vous ne les entendez pas crier… c’est grâce à moi.",
        "passif": {"nom": "Champ brouillé 📡", "effet": "Dès que le porteur soigne quelqu’un, il gagne 1 PB."},
        "image": "assets/personnage/Lysha Varn.png",
    },
    {
        "nom": "Kerin Dross",
        "rarete": "Commun",
        "faction": "GotValis",
        "description": "Je n’interviens jamais. Je note.",
        "passif": {"nom": "Observation continue 📹", "effet": "A 5 % de chance de se faire soigner de 1 PV quand quelqu’un est soigné."},
        "image": "assets/personnage/Kerin Dross.png",
    },
    {
        "nom": "Nova Rell",
        "rarete": "Commun",
        "faction": "GotValis",
        "description": "Moteur prêt. Si t’arrives pas à me suivre… c’est pas mon problème.",
        "passif": {"nom": "Réflexes Accélérés 🚗💨", "effet": "+5 % de chance d’esquiver toutes les attaques."},
        "image": "assets/personnage/Nova Rell.png",
    },
    {
        "nom": "Raya Nys",
        "rarete": "Commun",
        "faction": "GotValis",
        "description": "J’augmente la tolérance. Vous encaissez le reste.",
        "passif": {"nom": "Cadence de surcharge 🛡", "effet": "Augmente la capacité maximale de PB à 25 au lieu de 20."},
        "image": "assets/personnage/Raya Nys.png",
    },
    {
        "nom": "Tessa Korrin",
        "rarete": "Commun",
        "faction": "GotValis",
        "description": "Les vivants coûtent moins cher que les morts. Alors je vous garde en vie.",
        "passif": {"nom": "Injection stabilisante 💉", "effet": "Les soins prodigués rendent +1 PV."},
        "image": "assets/personnage/Tessa Korrin.png",
    },

    # Hôtel Dormant
    {
        "nom": "Alen Drave",
        "rarete": "Commun",
        "faction": "Hôtel Dormant",
        "description": "Silencieux, rapide, toujours à l’heure. Alen transporte plus que les bagages… parfois, un soupçon de magie de l’Hôtel l’accompagne.",
        "passif": {"nom": "Bénédiction des Bagages 🧳", "effet": "5 % de chance de réduire de 50 % les dégâts subis."},
        "image": "assets/personnage/Alen Drave.png",
    },
    {
        "nom": "Veylor Cassian",
        "rarete": "Commun",
        "faction": "Hôtel Dormant",
        "description": "On ne sait ni pourquoi il est venu, ni pourquoi il reste. Mais dans cet Hôtel, Veylor Cassian est chez lui… et nul n’ose troubler son repos.",
        "passif": {"nom": "Faveur de l’Hôte 🌙", "effet": "Réduit les dégâts reçus de 1 PV, avec 50 % de chance de réduire de 2 PV supplémentaires."},
        "image": "assets/personnage/Veylor Cassian.png",
    },

    # La Fracture
    {
        "nom": "Darn Kol",
        "rarete": "Commun",
        "faction": "La Fracture",
        "description": "Ce qui ne t’a pas tué… me servira à te finir.",
        "passif": {"nom": "Éclats utiles ⚙️", "effet": "Lorsque Darn inflige des dégâts, il a 10 % de chance de gagner 1 PV."},
        "image": "assets/personnage/Darn Kol.png",
    },
    {
        "nom": "Kara Drel",
        "rarete": "Commun",
        "faction": "La Fracture",
        "description": "La lame est vieille. Moi aussi. Mais elle coupe encore.",
        "passif": {"nom": "Frappe discrète 🗡️", "effet": "Lorsqu’elle attaque une cible à moins de 25 PV, elle inflige +1 dégât bonus."},
        "image": "assets/personnage/Kara Drel.png",
    },
    {
        "nom": "Nehra Vask",
        "rarete": "Commun",
        "faction": "La Fracture",
        "description": "Je n’ai pas besoin de lame. Ton armure me suffit.",
        "passif": {"nom": "Fracture brute 🦴", "effet": "Les attaques de Nehra ignorent les effets de réduction des casques 1 fois sur 3 (≈ 33 %)."},
        "image": "assets/personnage/Nehra Vask.png",
    },
    {
        "nom": "Liane Rekk",
        "rarete": "Commun",
        "faction": "La Fracture",
        "description": "Si tout doit tomber… alors brûlons d'abord ce qui tient debout.",
        "passif": {"nom": "Tactique primitive 🔥", "effet": "Lorsque Liane attaque, les dégâts qu’il inflige ne peuvent jamais être réduits par un casque."},
        "image": "assets/personnage/Liane Rekk.png",
    },
    {
        "nom": "Sive Arden",
        "rarete": "Commun",
        "faction": "La Fracture",
        "description": "Tu crois que ce que tu laisses derrière est inutile ? Pas pour moi.",
        "passif": {"nom": "Trouvaille impromptue 🪙", "effet": "5 % de chance, après une attaque, de gagner +1 GotCoin."},
        "image": "assets/personnage/Sive Arden.png",
    },

    # ───── Rare
    # GotValis
    {
        "nom": "Dr Aelran Vex",
        "rarete": "Rare",
        "faction": "GotValis",
        "description": "Les soins ne sont efficaces que si vous survivez assez longtemps pour en bénéficier.",
        "passif": {"nom": "Amplificateur vital ⚙️", "effet": "Augmente tous les soins reçus de 50 %."},
        "image": "assets/personnage/Dr Aelran Vex.png",
    },
    {
        "nom": "Nyra Kell",
        "rarete": "Rare",
        "faction": "GotValis",
        "description": "J’passe inaperçue. C’est là que je bosse le mieux.",
        "passif": {"nom": "Connexion réinitialisée 🧷", "effet": "Divise par 2 le temps d’attente pour les Daily."},
        "image": "assets/personnage/Nyra Kell.png",
    },
    {
        "nom": "Kieran Vox",
        "rarete": "Rare",
        "faction": "GotValis",
        "description": "J'ouvre des boîtes. Et parfois, j'y glisse un petit extra.",
        "passif": {"nom": "Bonus de Coursier 📦", "effet": "Quand le joueur ouvre une /box, il obtient +1 objet supplémentaire."},
        "image": "assets/personnage/Kieran Vox.png",
    },
    {
        "nom": "Seren Iskar",
        "rarete": "Rare",
        "faction": "GotValis",
        "description": "Je ne soigne pas. Je réécris les seuils de rupture.",
        "passif": {"nom": "Rétro-projection vitale 🔁", "effet": "À chaque soin reçu (effet direct ou sur la durée), l’unité gagne autant de Points de Bouclier (PB) que de PV soignés, deux fois par jour."},
        "image": "assets/personnage/Seren Iskar.png",
    },

    # Gouvernement
    {
        "nom": "Silien Dorr",
        "rarete": "Rare",
        "faction": "Gouvernement",
        "description": "Une pièce ici, une pièce là... à la fin, c’est toujours moi qui gagne.",
        "passif": {"nom": "Marges invisibles 💰", "effet": "À chaque gain de pièces via système normal du bot (combat, box, loot...), le joueur gagne +1 pièce supplémentaire."},
        "image": "assets/personnage/Silien Dorr.png",
    },

    # Hôtel Dormant
    {
        "nom": "Neyra Velenis",
        "rarete": "Rare",
        "faction": "Hôtel Dormant",
        "description": "Toujours souriante derrière son comptoir, Neyra connaît chaque visage, chaque anomalie, chaque dette contractée. Un mot de sa part… et l’Hôtel lui-même vous refusera le passage.",
        "passif": {"nom": "Marque de l’Hôte 📜", "effet": "10 % de réduction des dégâts subis en permanence. Pour chaque attaque reçue, réduit les dégâts reçus de 5 % et augmente l’esquive de 3 % pendant 1h (cumulatif, propre à chaque attaque)."},
        "image": "assets/personnage/Neyra Velenis.png",
    },
    {
        "nom": "Rouven Mance",
        "rarete": "Rare",
        "faction": "Hôtel Dormant",
        "description": "Le jeu n’est truqué que si tu perds. Et tu vas perdre.",
        "passif": {"nom": "Roulette de minuit 🎲", "effet": "25 % de chance à chaque attaque de déclencher un effet parmi : 🎯 +10 dégâts infligés | 🕵️ Vol d’un objet à la cible | ❤️ Soigne la cible à hauteur des dégâts infligés |💰 +25 GotCoins | 🛡 Ajoute un bouclier à l’attaquant égal aux dégâts infligés | 🧨 Perd un objet aléatoire de son inventaire | ♻️ Ne consomme pas l’objet utilisé. (Effet tiré aléatoirement, bénéfique ou non — le joueur ne peut pas le choisir.)"},
        "image": "assets/personnage/Rouven Mance.png",
    },

    # Infection
    {
        "nom": "Anna Lereux - Hôte Brisé",
        "rarete": "Rare",
        "faction": "Infection",
        "description": "Son corps n’est plus que le vaisseau de ce qui le ronge.",
        "passif": {"nom": "Émanation Fétide 🦠", "effet": "Quand le porteur infecte quelqu’un, les dégâts du statut Infection augmentent de 1. Ce personnage est infecté de base, mais ne subit pas les dégâts d’infection."},
        "image": "assets/personnage/Anna Lereux - Hôte Brisé.png",
    },

    # La Fracture
    {
        "nom": "Kael Dris",
        "rarete": "Rare",
        "faction": "La Fracture",
        "description": "Chaque coup me nourrit. Chaque hurlement me renforce.",
        "passif": {"nom": "Rétribution organique 🩸", "effet": "Chaque fois que Kael inflige des dégâts, il récupère 50 % de ces dégâts en PV (ex. : il inflige 20 → il récupère 10 PV)."},
        "image": "assets/personnage/Kael Dris.png",
    },
    {
        "nom": "Marn Velk",
        "rarete": "Rare",
        "faction": "La Fracture",
        "description": "Rien ne se perd, tant que je m’en souviens.",
        "passif": {"nom": "Rémanence d’usage ♻️", "effet": "À chaque attaque, Marn a 5 % de chance de ne pas consommer l’objet utilisé."},
        "image": "assets/personnage/Marn Velk.png",
    },
    {
        "nom": "Yann Tann",
        "rarete": "Rare",
        "faction": "La Fracture",
        "description": "Je n’ai pas besoin de viser juste. Il suffit que tu continues à brûler.",
        "passif": {"nom": "Feu rampant 🔥", "effet": "À chaque attaque, 10 % de chance d’infliger un effet de brûlure. La brûlure inflige 1 dégât toutes les 1h pendant 3h."},
        "image": "assets/personnage/Yann Tann.png",
    },

    # ───── Épique
    # GotValis
    {
        "nom": "Dr. Elwin Kaas",
        "rarete": "Épique",
        "faction": "GotValis",
        "description": "Protéger, optimiser. Chaque heure compte.",
        "passif": {"nom": "Interface de Renforcement 🛡️", "effet": "Le porteur gagne +1 PB par heure (fonctionne passivement même hors combat). Immunisé contre le poison."},
        "image": "assets/personnage/Dr Elwin Kaas.png",
    },
    {
        "nom": "Dr. Selina Vorne",
        "rarete": "Épique",
        "faction": "GotValis",
        "description": "Le corps est une machine. Une machine qu'on peut rendre immortelle.",
        "passif": {"nom": "Régénérateur Cellulaire 🌿", "effet": "Le porteur récupère +2 PV par heure (fonctionne passivement même hors combat). Toutes les 30 min, a une chance de guérir des statuts néfastes."},
        "image": "assets/personnage/Dr Selina Vorne.png",
    },

    # Gouvernement
    {
        "nom": "Alphonse Kaedrin",
        "rarete": "Épique",
        "faction": "Gouvernement",
        "description": "Les crédits ne dorment jamais. Et moi non plus.",
        "passif": {"nom": "Dividende occulte 🧾", "effet": "À chaque gain de crédits (combat, box, loot...) → 10 % de chance de doubler le gain. Gagne aussi +10 % à l’unité supérieure des gains reçus par ses attaquants."},
        "image": "assets/personnage/Alphonse Kaedrin.png",
    },
    {
        "nom": "Nathaniel Raskov",
        "rarete": "Épique",
        "faction": "Gouvernement",
        "description": "La guerre contre GotValis ne se gagnera pas sur le terrain seul. Nathaniel Raskov manie les lois comme d’autres les armes… et sait quand il faut en briser certaines.",
        "passif": {"nom": "Aura d’Autorité Absolue 🏛️", "effet": "10 % de chance de réduire de moitié les dégâts reçus. Si déclenché, l’attaquant subit un malus de -10 % de dégâts pendant 1 heure. Bonus constant : +5 % de résistance aux statuts."},
        "image": "assets/personnage/Nathaniel Raskov.png",
    },

    # Hôtel Dormant
    {
        "nom": "Elira Veska",
        "rarete": "Épique",
        "faction": "Hôtel Dormant",
        "description": "Toujours présente, toujours souriante. On la voit avant même qu’elle arrive. Madame Elira Veska connaît chaque couloir, chaque clé, chaque client. Elle vous guidera avec grâce... sauf si vous troublez l’Hôtel.",
        "passif": {"nom": "Clé du Dédale Miroir 🗝️", "effet": "+10 % d’esquive. Si une attaque est esquivée : elle est redirigée vers un autre adversaire aléatoire (hors porteur), et le porteur regagne +5 PB."},
        "image": "assets/personnage/Elira Veska.png",
    },

    # Infection
    {
        "nom": "Abomination Rampante",
        "rarete": "Épique",
        "faction": "Infection",
        "description": "Elle n’a plus de nom. Plus de volonté. Plus que la faim.",
        "passif": {"nom": "Faim Dévorante 🧟‍♂️", "effet": "Chaque attaque infligée → +5 % de chance d’appliquer l’Infection à la cible. Si la cible est déjà infectée → +30 % dégâts supplémentaires. À chaque kill → régénère +3 PV. Est un infecté qui ne subit pas les dégâts."},
        "image": "assets/personnage/Abomination Rampante.png",
    },

    # La Fracture
    {
        "nom": "Varkhel Drayne",
        "rarete": "Épique",
        "faction": "La Fracture",
        "description": "Chaque goutte de sang me rapproche de l’équilibre parfait.",
        "passif": {"nom": "Intensification sanglante 🩸", "effet": "Tant que Varkhel est en vie, il inflige +1 dégât bonus pour chaque tranche de 10 PV qu’il a perdue. Exemple : à 80 PV → +2 dégâts bonus / à 30 PV → +7. Bonus valable pour toutes les attaques qu’il effectue."},
        "image": "assets/personnage/Varkhel Drayne.png",
    },
    {
        "nom": "Elya Varnis",
        "rarete": "Épique",
        "faction": "La Fracture",
        "description": "Chaque blessure affine ma trajectoire. Chaque coup devient plus pur.",
        "passif": {"nom": "Frénésie chirurgicale ✴️", "effet": "Pour chaque tranche de 10 PV perdue, Elya gagne +2 % de chance de coup critique. Exemple : à 80 PV → +4 % crit | à 30 PV → +14 % crit. Se cumule avec tous les autres effets critiques."},
        "image": "assets/personnage/Elya Varnis.png",
    },

    # ───── Légendaire
    # Monarchie
    {
        "nom": "Le Roi",
        "rarete": "Légendaire",
        "faction": "Monarchie",
        "description": "Il règne sur tous. Il les regarde tous se battre... et frappe quand le moment lui plaît.",
        "passif": {"nom": "Finisher Royal 👑⚔️", "effet": "Quand l’ennemi a 10 PV, n’importe quelle attaque le met KO avec un Gif Particulier. Si le coup achève l’adversaire → le porteur récupère +10 PV. Ne subit aucun malus si la cible a 10 PV (l’attaque ignore les PB, les réductions ou les malus)."},
        "image": "assets/personnage/Le Roi.png",
    },

    # GotValis
    {
        "nom": "Valen Drexar",
        "rarete": "Légendaire",
        "faction": "GotValis",
        "description": "Vous croyez jouer une partie... mais j’ai conçu le plateau.",
        "passif": {"nom": "Domaine de Contrôle Absolu 🧠", "effet": "Chaque attaque subie → 15 % de chance de réduire les dégâts de 75 %, l’adversaire 'rate' partiellement son action. Quand il passe sous 50 % PV, il gagne +5 PB et +10 % de réduction des dégâts pour chaque tranche de 10 PV perdue (40, 30, 20, 10) — cumulatif. Est immunisé contre tous les statuts."},
        "image": "assets/personnage/Valen Drexar.png",
    },

    # Hôtel Dormant
    {
        "nom": "Maître d’Hôtel",
        "rarete": "Légendaire",
        "faction": "Hôtel Dormant",
        "description": "Nul ne connaît son âge, ni l’étendue réelle de ses pouvoirs. Le Maître d’Hôtel veille sur l’Hôtel Dormant avec malice et une magie aussi élégante que redoutable. Une canne en main, un sourire en coin — ici, il est invincible.",
        "passif": {"nom": "Règle d’Or de l’Hospitalité 🎩✨", "effet": "30 % de chance d’annuler toute attaque reçue. 20 % de chance de contre-attaquer pour ¼ des dégâts reçus (arrondi à l’unité supérieure). +10 % de résistance passive aux dégâts (réduction de -1 tous les 10 dégâts reçus) et en cas d'esquive, renvoit l'attaque sur une cible aléatoire en récuperant les stats de dégats."},
        "image": "assets/personnage/Maitre d’Hotel.png",
    },

    # La Fracture
    {
        "nom": "Zeyra Kael",
        "rarete": "Légendaire",
        "faction": "La Fracture",
        "description": "Brisez son corps, elle avancera encore. Brisez son esprit… personne n’y est parvenu.",
        "passif": {"nom": "Volonté de Fracture 💥", "effet": "Ne peut jamais être mise KO : toute attaque qui devrait la passer sous 0 PV la laisse à 1 PV (1 fois par jour). Tant qu'elle a moins de PV, elle inflige jusqu'à +40 % de dégâts bonus (scalé). Les coups critiques sont divisés par 2. Réduit les dégâts subis de 1."},
        "image": "assets/personnage/Zeyra Kael.png",
    },
]

# Index par nom (copie shallow pour usage direct)
PERSONNAGES: Dict[str, Dict] = {p["nom"]: dict(p) for p in PERSONNAGES_LIST}


# ─────────────────────────────────────────────────────────────────────────────
# Utilitaires
# ─────────────────────────────────────────────────────────────────────────────

def _normalize(s: str) -> str:
    """Normalise une chaîne pour comparaison (insensible accents/majuscules)."""
    if not isinstance(s, str):
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return s.lower().strip()

def generer_slug(nom: str) -> str:
    """Crée un slug simple depuis le nom (utile pour URLs, clés, etc.)."""
    base = _normalize(nom).replace(" ", "-")
    # garde uniquement [a-z0-9-]
    return "".join(ch for ch in base if ch.isalnum() or ch == "-")

# Cache slug -> nom
_SLUG_INDEX: Dict[str, str] = {generer_slug(n): n for n in PERSONNAGES.keys()}

def get_par_nom(nom: str) -> Optional[Dict]:
    """Retourne le personnage par NOM exact (clé du dict)."""
    return PERSONNAGES.get(nom)

def get_par_slug(slug: str) -> Optional[Dict]:
    """Retourne le personnage par SLUG (insensible aux accents/majuscules)."""
    nom = _SLUG_INDEX.get(_normalize(slug))
    return PERSONNAGES.get(nom) if nom else None

def trouver(nom_ou_slug: str) -> Optional[Dict]:
    """Recherche conviviale : essaie d'abord le nom exact, puis le slug/approx."""
    if nom_ou_slug in PERSONNAGES:
        return PERSONNAGES[nom_ou_slug]
    p = get_par_slug(nom_ou_slug)
    if p:
        return p
    # fallback : recherche approx très simple
    target = _normalize(nom_ou_slug)
    for nom, p in PERSONNAGES.items():
        if _normalize(nom) == target:
            return p
    return None

def get_tous_les_noms() -> List[str]:
    return list(PERSONNAGES.keys())

def get_par_rarete(rarete: str) -> List[Dict]:
    """Liste triée par ordre de faction pour une rareté donnée."""
    r = [p for p in PERSONNAGES.values() if p.get("rarete") == rarete]
    r.sort(key=lambda p: FACTION_ORDER.index(p.get("faction", "")) if p.get("faction", "") in FACTION_ORDER else 999)
    return r

def get_par_faction(faction: str) -> List[Dict]:
    """Tous les personnages d'une faction (ordre par rareté puis nom)."""
    r = [p for p in PERSONNAGES.values() if p.get("faction") == faction]
    r.sort(key=lambda p: (RARETES.index(p.get("rarete", "Commun")) if p.get("rarete") in RARETES else 999, p.get("nom", "")))
    return r

def get_alea_par_rarete(rarete: str) -> Optional[Dict]:
    """Un personnage aléatoire dans une rareté donnée (ou None si vide)."""
    candidats = get_par_rarete(rarete)
    return random.choice(candidats) if candidats else None

def tirage_rarete_pondere() -> str:
    """Retourne une rareté selon RARETE_WEIGHTS (pour /tirage)."""
    population = list(RARETE_WEIGHTS.keys())
    poids = list(RARETE_WEIGHTS.values())
    return random.choices(population, weights=poids, k=1)[0]

def tirage_personnage() -> Tuple[str, Dict]:
    """Tirage complet : choisit une rareté pondérée, puis un perso dans cette rareté.
       Retourne (rarete, personnage)."""
    r = tirage_rarete_pondere()
    p = get_alea_par_rarete(r)
    return r, p

def valider_entree(p: Dict) -> List[str]:
    """Validation douce d’une entrée de personnage (pour log/debug)."""
    erreurs: List[str] = []
    if "nom" not in p or not p["nom"]:
        erreurs.append("nom manquant")
    if p.get("rarete") not in RARETES:
        erreurs.append(f"rarete invalide: {p.get('rarete')}")
    if p.get("faction") not in FACTION_ORDER:
        erreurs.append(f"faction invalide: {p.get('faction')}")
    if "passif" not in p or not isinstance(p["passif"], dict):
        erreurs.append("passif manquant ou invalide")
    else:
        if not p["passif"].get("nom"):
            erreurs.append("passif.nom manquant")
        if not p["passif"].get("effet"):
            erreurs.append("passif.effet manquant")
    if "image" not in p or not p["image"]:
        erreurs.append("image manquante")
    return erreurs

def valider_toutes_les_entrees() -> Dict[str, List[str]]:
    """Retourne un dict {nom: [erreurs]} pour les entrées problématiques (sinon vide)."""
    issues: Dict[str, List[str]] = {}
    for p in PERSONNAGES_LIST:
        errs = valider_entree(p)
        if errs:
            issues[p.get("nom", "<inconnu>")] = errs
    return issues

# Mappage facultatif : nom de passif -> code interne (utile pour passifs.py)
# (Tu pourras compléter ce mapping au fur et à mesure que tu implémentes
# les hooks dans passifs.py pour un routage propre.)
PASSIF_CODE_MAP: Dict[str, str] = {
    "Éloquence officielle 🕊️": "stack_resistance_par_attaque",
    "Volonté mal orientée 💼": "chance_reduc_moitie_degats",
    "Archivage parfait 📑": "vol_double_chance",
    "Protection implicite 👑": "buff_esquive_apres_coup",
    "Mémoire d'État 📚": "purge_chance_horaire",
    "Récompense fantôme 📦": "daily_double_chance",
    "Écho de Grâce 🎁": "boost_rarete_prochain_tirage",
    "Vol opportuniste 🪙": "double_vol_niv_kress",
    "Intouchable 🛡": "anti_vol_total",
    "Éclats recyclés 🔪": "loot_objet_survie",
    "Vendeur rusé 💰": "shop_sell_bonus",
    "Filtrage actif 🎧": "reduc_degats_si_pb",
    "Zone propre 🧼": "bonus_degats_vs_infectes",
    "Champ brouillé 📡": "gain_pb_quand_soigne",
    "Observation continue 📹": "chance_self_heal_si_soin_autrui",
    "Réflexes Accélérés 🚗💨": "bonus_esquive_constant",
    "Cadence de surcharge 🛡": "max_pb_25",
    "Injection stabilisante 💉": "soins_plus_un",
    "Bénédiction des Bagages 🧳": "chance_reduc_moitie_degats",
    "Faveur de l’Hôte 🌙": "reduc_degats_fixe_et_chance_sup",
    "Amplificateur vital ⚙️": "soin_recu_x1_5",
    "Connexion réinitialisée 🧷": "daily_cd_halved",
    "Bonus de Coursier 📦": "box_plus_un_objet",
    "Rétro-projection vitale 🔁": "pb_egal_soin_limite",
    "Marges invisibles 💰": "plus_un_coin_sur_gains",
    "Marque de l’Hôte 📜": "reduc_degats_perma_et_stacks",
    "Roulette de minuit 🎲": "proc_roulette_minuit",
    "Émanation Fétide 🦠": "infection_buff_source_pas_degats",
    "Rétribution organique 🩸": "vampirisme_50pct",
    "Rémanence d’usage ♻️": "chance_ne_pas_consommer_objet",
    "Feu rampant 🔥": "chance_brule_1h_x3",
    "Interface de Renforcement 🛡️": "pb_plus_un_par_heure_anti_poison",
    "Régénérateur Cellulaire 🌿": "pv_plus_deux_par_heure_purge_chance",
    "Dividende occulte 🧾": "chance_double_gain_et_leech",
    "Aura d’Autorité Absolue 🏛️": "chance_reduc_moitie_malus_attaquant_resist_status",
    "Clé du Dédale Miroir 🗝️": "redirect_si_esquive_et_gain_pb",
    "Faim Dévorante 🧟‍♂️": "infection_chance_et_bonus_vs_infecte_kill_heal",
    "Intensification sanglante 🩸": "bonus_degats_par_10pv_perdus",
    "Frénésie chirurgicale ✴️": "bonus_crit_par_10pv_perdus",
    "Finisher Royal 👑⚔️": "execute_a_10pv_ignores_et_heal",
    "Domaine de Contrôle Absolu 🧠": "drastique_reduc_chance_scaling_pb_dr_immune",
    "Règle d’Or de l’Hospitalité 🎩✨": "annule_ou_contrattaque_resist_esquive_redirect",
    "Volonté de Fracture 💥": "undying_1pv_jour_scaling_dmg_half_crit_flat_reduc",
}

def code_passif(p: Dict) -> Optional[str]:
    """Retourne un code interne de passif pour routage dans passifs.py (facultatif)."""
    if not p:
        return None
    nom_passif = p.get("passif", {}).get("nom")
    return PASSIF_CODE_MAP.get(nom_passif or "")

# ─────────────────────────────────────────────────────────────────────────────
# Fin du module
# ─────────────────────────────────────────────────────────────────────────────

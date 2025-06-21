from personnage import PERSONNAGES, RARETES, FACTION_ORDER
import os

def valider_personnages():
    erreurs = []
    noms_vus = set()

    for perso in PERSONNAGES:
        nom = perso.get("nom")
        rarete = perso.get("rarete")
        faction = perso.get("faction")
        passif = perso.get("passif", {})
        image = perso.get("image")

        # Vérifie que le nom existe et est unique
        if not nom:
            erreurs.append("❌ Un personnage n’a pas de nom.")
        elif nom in noms_vus:
            erreurs.append(f"❌ Doublon de nom : {nom}")
        else:
            noms_vus.add(nom)

        # Vérifie que la rareté est valide
        if rarete not in RARETES:
            erreurs.append(f"❌ Rareté invalide pour {nom} : {rarete}")

        # Vérifie que la faction est valide
        if faction not in FACTION_ORDER:
            erreurs.append(f"❌ Faction invalide pour {nom} : {faction}")

        # Vérifie que le passif contient bien nom + effet
        if not isinstance(passif, dict) or "nom" not in passif or "effet" not in passif:
            erreurs.append(f"❌ Passif incomplet ou invalide pour {nom}")

        # Vérifie que l’image est renseignée
        if not image:
            erreurs.append(f"❌ Image manquante pour {nom}")
        # Optionnel : vérifier que le fichier image existe
        elif not os.path.isfile(image):
            erreurs.append(f"❌ Image introuvable pour {nom} → {image}")

    # Résultat
    if erreurs:
        print("=== 🛑 ERREURS DÉTECTÉES ===")
        for err in erreurs:
            print(err)
    else:
        print("✅ Tous les personnages sont valides.")

if __name__ == "__main__":
    valider_personnages()

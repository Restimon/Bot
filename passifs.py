import time
import random
import math
from data import (
    personnages_equipés, resistance_bonus, esquive_bonus, shields,
    infection_status, hp, immunite_status, esquive_status,
    virus_status, poison_status, burn_status, malus_degat  # burn_status et malus_degat étaient manquants
)
from personnage import PERSONNAGES
from cooldowns import daily_limit
from economy import add_gotcoins
from storage import get_user_data
from utils import remove_random_item, give_random_item

zeyra_last_survive_time = {}
valen_seuils = {}
# 🔓 Fonction principale à importer
def appliquer_passif_utilisateur(guild_id, user_id, contexte, données):
    nom = personnages_equipés.get(str(guild_id), {}).get(str(user_id))
    if not nom:
        return None

    personnage = PERSONNAGES.get(nom)
    if not personnage:
        return None

    personnage["nom"] = nom
    return appliquer_passif(personnage, contexte, données)


# 🔁 Dispatcher interne
def appliquer_passif(personnage, contexte, données):
    nom = personnage.get("nom")

    if nom == "Cassiane Vale":
        return passif_cassiane_vale(contexte, données)
    elif nom == "Darin Venhal":
        return passif_darin_venhal(contexte, données)
    elif nom == "Elwin Jarr":
        return passif_elwin_jarr(contexte, données)
    elif nom == "Liora Venhal":
        return passif_liora_venhal(contexte, données)
    elif nom == "Maelis Dorné":
        return passif_maelis_dorne(contexte, données)
    elif nom == "Lior Danen":
        return passif_lior_danen(contexte, données)
    elif nom == "Nael Mirren":
        return passif_nael_mirren(contexte, données)
    elif nom == "Niv Kress":
        return passif_niv_kress(contexte, données)
    elif nom == "Lyss Tenra":
        return passif_lyss_tenra(contexte, données)
    elif nom == "Mira Oskra":
        return passif_mira_oskra(contexte, données)
    elif nom == "Sel Varnik":
        return passif_sel_varnik(contexte, données)
    elif nom == "Cielya Morn":
        return passif_cielya_morn(contexte, données)
    elif nom == "Kevar Rin":
        return passif_kevar_rin(contexte, données)
    elif nom == "Lysha Varn":
        return passif_lysha_varn(contexte, données)
    elif nom == "Kerin Dross":
        return passif_kerin_dross(contexte, données)
    elif nom == "Nova Rell":
        return passif_nova_rell(contexte, données)
    elif nom == "Raya Nys":
        return passif_raya_nys(contexte, données)
    elif nom == "Tessa Korrin":
        return passif_tessa_korrin(contexte, données)
    elif nom == "Alen Drave":
        return passif_alen_drave(contexte, données)
    elif nom == "Veylor Cassian":
        return passif_veylor_cassian(contexte, données)
    elif nom == "Darn Kol":
        return passif_darn_kol(contexte, données)
    elif nom == "Kara Drel":
        return passif_kara_drel(contexte, données)
    elif nom == "Nehra Vask":
        return passif_nehra_vask(contexte, données)
    elif nom == "Liane Rekk":
        return passif_liane_rekk(contexte, données)
    elif nom == "Sive Arden":
        return passif_sive_arden(contexte, données)
    elif nom == "Dr Aelran Vex":
        return passif_aelran_vex(contexte, données)
    elif nom == "Nyra Kell":
        return passif_nyra_kell(contexte, données)
    elif nom == "Kieran Vox":
        return passif_kieran_vox(contexte, données)
    elif nom == "Seren Iskar":
        return passif_seren_iskar(contexte, données)
    elif nom == "Silien Dorr":
        return passif_silien_dorr(contexte, données)
    elif nom == "Neyra Velenis":
        return passif_neyra_velenis(contexte, données)
    elif nom == "Rouven Mance":
        return passif_rouven_mance(contexte, données)
    elif nom == "Anna Lereux - Hôte Brisé":
        return passif_anna_lereux(contexte, données)
    elif nom == "Kael Dris":
        return passif_kael_dris(contexte, données)
    elif nom == "Marn Velk":
        return passif_marn_velk(contexte, données)
    elif nom == "Yann Tann":
        return passif_yann_tann(contexte, données)
    elif nom == "Dr. Elwin Kaas":
        return passif_elwin_kaas(contexte, données)
    elif nom == "Dr. Selina Vorne":
        return passif_selina_vorne(contexte, données)
    elif nom == "Alphonse Kaedrin":
        return passif_alphonse_kaedrin(contexte, données)
    elif nom == "Nathaniel Raskov":
        return passif_nathaniel_raskov(contexte, données)
    elif nom == "Elira Veska":
        return passif_elira_veska(contexte, données)
    elif nom == "Abomination Rampante":
        return passif_abomination_rampante(contexte, données)
    elif nom == "Varkhel Drayne":
        return passif_varkhel_drayne(contexte, données)
    elif nom == "Elya Varnis":
        return passif_elya_varnis(contexte, données)
    elif nom == "Le Roi":
        return passif_le_roi(contexte, données)
    elif nom == "Valen Drexar":
        return passif_valen_drexar(contexte, données)
    elif nom == "Maître d’Hôtel":
        return passif_maitre_hotel(contexte, données)
    elif nom == "Zeyra Kael":
        return passif_zeyra_kael(contexte, données)
    return None


# 🛡️ Passif de Cassiane Vale
def passif_cassiane_vale(contexte, données):
    if contexte == "defense":
        guild_id = données["guild_id"]
        user_id = données["defenseur"]
        now = time.time()

        bonus = resistance_bonus.setdefault(guild_id, {}).setdefault(user_id, {"valeur": 0, "timestamp": now})

        # Réinitialisation si plus de 24h
        if now - bonus["timestamp"] > 86400:
            bonus["valeur"] = 0
            bonus["timestamp"] = now

        bonus["valeur"] += 1  # +1% par attaque
        resistance_bonus[guild_id][user_id] = bonus

    elif contexte == "calcul_defense":
        guild_id = données["guild_id"]
        user_id = données["defenseur"]
        bonus = resistance_bonus.get(guild_id, {}).get(user_id)

        if bonus and time.time() - bonus["timestamp"] < 86400:
            return {"reduction_degats": bonus["valeur"] / 100}

    return None

def passif_darin_venhal(contexte, données):
    if contexte == "calcul_defense":
        # 🎲 10 % de chance de réduire les dégâts de moitié
        chance = random.random()
        if chance <= 0.10:
            return {"reduction_multiplicateur": 0.5}  # Multiplie les dégâts par 0.5
    return None

def passif_elwin_jarr(contexte, données):
    if contexte == "utilitaire_vol":
        chance = random.random()
        if chance <= 0.10:
            return {"double_vol": True}
    return None

def passif_liora_venhal(contexte, données):
    if contexte == "defense":
        guild_id = données["guild_id"]
        user_id = données["defenseur"]
        now = time.time()

        chance = random.random()
        if chance <= 0.25:
            bonus = esquive_bonus.setdefault(guild_id, {}).setdefault(user_id, {"valeur": 0, "timestamp": now})

            # Reset si expiré
            if now - bonus["timestamp"] > 86400:
                bonus["valeur"] = 0
                bonus["timestamp"] = now

            bonus["valeur"] += 3
            esquive_bonus[guild_id][user_id] = bonus

    elif contexte == "calcul_esquive":
        guild_id = données["guild_id"]
        user_id = données["defenseur"]
        bonus = esquive_bonus.get(guild_id, {}).get(user_id)

        if bonus and time.time() - bonus["timestamp"] < 86400:
            return {"bonus_esquive": bonus["valeur"]}

    return None

def passif_maelis_dorne(contexte, données):
    if contexte == "purge_auto":
        guild_id = données["guild_id"]
        user_id = données["user_id"]

        # 📅 Chance : 1 % par heure écoulée
        now = time.time()
        last = données.get("last_timestamp", now)
        heures = int((now - last) // 3600)
        if heures <= 0:
            return None

        chance = heures / 100  # 1% par heure
        if random.random() < chance:
            return {"purger_statut": True}

    return None

def passif_lior_danen(contexte, données):
    if contexte == "daily":
        chance = random.random()
        if chance <= 0.05:
            return {"double_daily": True}
    return None

def passif_nael_mirren(contexte, données):
    if contexte == "tirage_objet":
        chance = random.random()
        if chance <= 0.01:
            return {"bonus_rarite": True}
    return None

def passif_niv_kress(contexte, données):
    if contexte == "utilitaire_vol":
        chance = random.random()
        if chance <= 0.10:
            return {"conserver_objet_vol": True}
    return None

def passif_lyss_tenra(contexte, données):
    if contexte == "protection_vol":
        return {"immunise_contre_vol": True}
    return None

def passif_mira_oskra(contexte, données):
    if contexte == "defense_survie":
        chance = random.random()
        if chance <= 0.03:
            item = random.choice(["❄️", "🔥", "🍀"])
            return {"objet_bonus": item}
    return None
    
def passif_sel_varnik(contexte, données):
    if contexte == "vente_objet":
        return {"bonus_prix_vente": 1.25}  # 25% de plus
    return None

def passif_cielya_morn(contexte, données):
    if contexte == "calcul_defense":
        guild_id = données["guild_id"]
        user_id = données["defenseur"]

        if shields.get(guild_id, {}).get(user_id, 0) > 0:
            return {"reduction_multiplicateur": 0.75}  # réduit les dégâts à 75%
    return None

def passif_kevar_rin(contexte, données):
    if contexte == "attaque":
        guild_id = données["guild_id"]
        cible_id = données["cible_id"]

        if infection_status.get(guild_id, {}).get(cible_id):
            return {"bonus_degats": 3}
    return None

def passif_lysha_varn(contexte, données):
    if contexte == "soin":
        guild_id = données["guild_id"]
        soigneur = données["soigneur"]

        # Ajoute 1 PB à Lysha
        shields.setdefault(guild_id, {})
        shields[guild_id][soigneur] = shields[guild_id].get(soigneur, 0) + 1

    return None

def passif_kerin_dross(contexte, données):
    if contexte == "soin":
        guild_id = données["guild_id"]
        user_id = données["soigneur"]  # celui qui pourrait être Kerin
        tous_hp = hp.get(guild_id, {})

        # Vérifie si Kerin Dross est équipé
        for pid, nom in personnages_equipés.get(guild_id, {}).items():
            if nom == "Kerin Dross":
                chance = random.random()
                if chance <= 0.05:
                    pid = str(pid)
                    tous_hp[pid] = min(100, tous_hp.get(pid, 0) + 1)

    return None

def passif_nova_rell(contexte, données):
    if contexte == "calcul_esquive":
        return {"bonus_esquive": 5}  # +5% d’esquive
    return None
    
def passif_raya_nys(contexte, données):
    if contexte == "max_pb":
        return {"max_pb": 25}
    return None
    
def passif_tessa_korrin(contexte, données):
    if contexte == "bonus_soin":
        return {"bonus_pv_soin": 1}
    return None

def passif_alen_drave(contexte, données):
    if contexte == "defense":
        chance = random.random()
        if chance <= 0.05:
            return {"reduction_multiplicateur": 0.5}  # Réduction à 50 %
    return None

def passif_veylor_cassian(contexte, données):
    if contexte == "defense":
        reduction = 1
        if random.random() <= 0.5:
            reduction += 2
        return {"reduction_fixe": reduction}
    return None

def passif_darn_kol(contexte, données):
    if contexte == "attaque":
        if random.random() <= 0.10:
            guild_id = données["guild_id"]
            attaquant = données["attaquant"]
            hp.setdefault(guild_id, {})
            hp[guild_id][attaquant] = min(hp[guild_id].get(attaquant, 20), hp[guild_id].get(attaquant, 0) + 1)
    return None

def passif_kara_drel(contexte, données):
    if contexte == "attaque":
        guild_id = données["guild_id"]
        cible_id = données["cible_id"]
        cible_pv = hp.get(guild_id, {}).get(cible_id, 0)

        if cible_pv < 25:
            return {"bonus_degats": 1}
    return None

def passif_nehra_vask(contexte, données):
    if contexte == "attaque":
        if random.random() <= 1/3:
            return {"ignorer_reduction_casque": True}
    return None

def passif_liane_rekk(contexte, données):
    if contexte == "attaque":
        return {"ignorer_reduction_casque": True}
    return None

def passif_sive_arden(contexte, données):
    if contexte == "attaque":
        if random.random() <= 0.05:
            guild_id = données["guild_id"]
            user_id = données["attaquant"]
            add_gotcoins(guild_id, user_id, 1)
    return None

def passif_aelran_vex(contexte, données):
    if contexte == "soin_reçu":
        return {"multiplicateur_soin_recu": 1.5}
    return None

def passif_nyra_kell(contexte, données):
    if contexte == "daily_cooldown":
        return {"cooldown_multiplicateur": 0.5}
    return None

def passif_kieran_vox(contexte, données):
    if contexte == "box":
        return {"bonus_objets_box": 1}
    return None

def passif_seren_iskar(contexte, données):
    if contexte == "soin_reçu":
        guild_id = données["guild_id"]
        cible_id = données["cible"]
        soin = données.get("soin", 0)

        if daily_limit(guild_id, cible_id, "seren_pb_boost", limit=2):
            shields.setdefault(guild_id, {})
            shields[guild_id][cible_id] = shields[guild_id].get(cible_id, 0) + soin
    return None

def passif_silien_dorr(contexte, données):
    if contexte == "gain_gotcoins":
        guild_id = données["guild_id"]
        user_id = données["user_id"]
        add_gotcoins(guild_id, user_id, 1)
    return None

def passif_neyra_velenis(contexte, données):
    guild_id = données["guild_id"]
    user_id = données["defenseur"]

    if contexte == "defense":
        # ✅ Effet permanent : -10 % dégâts
        return {"reduction_multiplicateur": 0.9}

    if contexte == "attaque_reçue":
        # ✅ Buff cumulatif temporaire (1h)
        now = time.time()
        esquive_status.setdefault(guild_id, {}).setdefault(user_id, []).append({
            "bonus": 3,
            "expires": now + 3600
        })
        immunite_status.setdefault(guild_id, {}).setdefault(user_id, []).append({
            "reduction": 0.05,
            "expires": now + 3600
        })
    return None

def passif_rouven_mance(contexte, données):
    if contexte != "attaque":
        return None

    if random.random() > 0.25:
        return None  # 25% de chance de déclenchement

    effets_possibles = [
        "degats+",    # 🎯 +10 dégâts infligés
        "vol",        # 🕵️ Vol d’un objet
        "soin",       # ❤️ Soigne la cible
        "gotcoins",   # 💰 +25 GotCoins
        "bouclier",   # 🛡 Bouclier = dégâts infligés
        "perte",      # 🧨 Perd un objet
        "pas_de_conso", # ♻️ Objet pas consommé
        "revers"      # ❗ Attaquant prend 50% des dégâts
    ]
    effet = random.choice(effets_possibles)

    resultat = {"effet_roulette": effet}

    guild_id = données["guild_id"]
    attaquant = données["attaquant"]
    cible = données["cible_id"]
    degats = données.get("degats", 0)

    if effet == "degats+":
        resultat["bonus_degats"] = 10

    elif effet == "vol":
        give_random_item(guild_id, attaquant, remove_random_item(guild_id, cible))

    elif effet == "soin":
        hp.setdefault(guild_id, {})
        hp[guild_id][cible] = min(hp[guild_id].get(cible, 0) + degats, 20)

    elif effet == "gotcoins":
        add_gotcoins(guild_id, attaquant, 25)

    elif effet == "bouclier":
        shields.setdefault(guild_id, {})
        shields[guild_id][attaquant] = shields[guild_id].get(attaquant, 0) + degats

    elif effet == "perte":
        remove_random_item(guild_id, attaquant)

    elif effet == "pas_de_conso":
        resultat["pas_de_conso"] = True

    elif effet == "revers":
        hp.setdefault(guild_id, {})
        hp[guild_id][attaquant] = max(0, hp[guild_id].get(attaquant, 0) - int(degats / 2))

    return resultat

def passif_anna_lereux(contexte, données):
    guild_id = données["guild_id"]
    user_id = données["user_id"]

    if contexte == "infection_provoquee":
        cible_id = données["cible_id"]
        infection_status.setdefault(guild_id, {}).setdefault(cible_id, {}).setdefault("bonus_dgt", 0)
        infection_status[guild_id][cible_id]["bonus_dgt"] += 1

    elif contexte == "tick_infection":
        # Anna ne subit pas les dégâts d'infection même si elle est infectée
        if données["cible_id"] == user_id:
            return {"annuler_degats": True}

    elif contexte == "initialisation_personnage":
        # Infecter Anna dès le départ
        infection_status.setdefault(guild_id, {}).setdefault(user_id, {})["actif"] = True

    return None

def passif_kael_dris(contexte, données):
    if contexte != "degats_infliges":
        return None

    guild_id = données["guild_id"]
    user_id = données["attaquant"]
    degats = données.get("degats", 0)

    soin = int(degats * 0.5)
    hp.setdefault(guild_id, {})
    hp[guild_id][user_id] = min(hp[guild_id].get(user_id, 0) + soin, 20)

    return {"soin": soin}

def passif_marn_velk(contexte, données):
    if contexte != "attaque":
        return None

    if random.random() <= 0.05:  # 5 % de chance
        return {"pas_de_conso": True}

    return None

def passif_yann_tann(contexte, données):
    if contexte != "attaque":
        return None

    if random.random() > 0.10:
        return None  # 10 % de chance

    guild_id = données["guild_id"]
    cible_id = données["cible_id"]

    burn_status.setdefault(guild_id, {})
    burn_status[guild_id][cible_id] = {
        "actif": True,
        "start_time": time.time(),
        "ticks_restants": 3,
        "next_tick": time.time() + 3600,
        "source": donnees["attaquant_id"],  # 🟢 ajoute cette ligne
        "channel_id": donnees["channel_id"]  # 🟢 et celle-ci
    }

    return {"brulure": True}

def passif_elwin_kaas(contexte, données):
    guild_id = données["guild_id"]
    user_id = données["user_id"]

    if contexte == "tick_heures":
        shields.setdefault(guild_id, {})
        shields[guild_id][user_id] = min(shields[guild_id].get(user_id, 0) + 1, 25)  # cap à 25 PB ?

    elif contexte == "tentative_poison":
        return {"annuler_poison": True}

    return None

def passif_selina_vorne(contexte, données):
    guild_id = données["guild_id"]
    user_id = données["user_id"]

    if contexte == "tick_heures":
        hp.setdefault(guild_id, {})
        hp[guild_id][user_id] = min(hp[guild_id].get(user_id, 0) + 2, 20)

    elif contexte == "tick_30min":
        if random.random() <= 0.20:  # 20 % de chance de purge par tick 30min (ajustable)
            # Supprimer 1 effet néfaste (priorité : virus > poison > infection > brûlure)
            for status_dict in [virus_status, poison_status, infection_status, burn_status]:
                if user_id in status_dict.get(guild_id, {}):
                    del status_dict[guild_id][user_id]
                    return {"status_supprimé": True}

    return None

def passif_alphonse_kaedrin(contexte, données):
    guild_id = données["guild_id"]
    user_id = données["user_id"]

    if contexte == "gain_gotcoins":
        montant = données.get("montant", 0)

        # 🎲 10 % de chance de doubler le gain
        if random.random() <= 0.10:
            return {"gotcoins_bonus": montant}  # ajouter ce bonus ailleurs dans le code

    elif contexte == "gain_sur_attaque_alphonse":
        montant = données.get("montant", 0)
        attaquant = données["attaquant"]

        bonus = math.ceil(montant * 0.10)
        add_gotcoins(guild_id, user_id, bonus)
        return {"passif_alphonse_bonus": bonus}

    return None

def passif_nathaniel_raskov(contexte, données):
    guild_id = données["guild_id"]
    user_id = données["user_id"]

    if contexte == "defense":
        if random.random() <= 0.10:  # 10 % chance
            attaquant = données["attaquant"]

            malus_degat.setdefault(guild_id, {})
            malus_degat[guild_id][attaquant] = {
                "pourcentage": 10,
                "expiration": time.time() + 3600  # 1h
            }

            return {"moitie_degats": True}

    elif contexte == "resistance_statuts":
        return {"resistance_bonus": 5}  # 5 % en plus contre les statuts

    return None

def passif_elira_veska(contexte, données):
    guild_id = données["guild_id"]
    user_id = données["user_id"]

    if contexte == "passif_constant":
        return {"esquive_bonus": 10}

    elif contexte == "attaque_esquivee":
        # Rediriger attaque + +5 PB
        nouveau_cible = get_random_enemy(guild_id, exclude=[user_id, données["attaquant_id"]])
        if not nouveau_cible:
            return None

        shields.setdefault(guild_id, {})
        shields[guild_id][user_id] = min(shields[guild_id].get(user_id, 0) + 5, 25)

        return {
            "rediriger": True,
            "nouvelle_cible": nouveau_cible,
            "pb_bonus": 5
        }

    return None

def passif_abomination_rampante(contexte, données):
    guild_id = données["guild_id"]
    user_id = données["user_id"]

    if contexte == "attaque":
        cible_id = données["cible"]
        effet = {}

        # 5 % de chance d'infecter
        if random.random() <= 0.05:
            infection_status.setdefault(guild_id, {})
            infection_status[guild_id][cible_id] = time.time()

            effet["infection"] = True

        # +30 % dégâts si la cible est déjà infectée
        if cible_id in infection_status.get(guild_id, {}):
            effet["bonus_degats_percent"] = 30

        return effet if effet else None

    elif contexte == "kill":
        hp.setdefault(guild_id, {})
        hp[guild_id][user_id] = min(hp[guild_id].get(user_id, 0) + 3, 20)
        return {"pv_gagnes": 3}

    elif contexte == "tick_infection":
        return {"ignore_infection_damage": True}

    return None

def passif_varkhel_drayne(contexte, données):
    if contexte == "attaque":
        guild_id = données["guild_id"]
        user_id = données["user_id"]

        from data import hp
        hp_actuel = hp.get(guild_id, {}).get(user_id, 100)
        pv_manquants = max(0, 100 - hp_actuel)

        bonus = pv_manquants // 10  # 1 dégât tous les 10 PV perdus

        if bonus > 0:
            return {"bonus_degats_fixes": bonus}

    return None

def passif_elya_varnis(contexte, données):
    if contexte == "attaque":
        guild_id = données["guild_id"]
        user_id = données["user_id"]

        from data import hp
        hp_actuel = hp.get(guild_id, {}).get(user_id, 100)
        pv_manquants = max(0, 100 - hp_actuel)

        bonus_critique = (pv_manquants // 10) * 2  # +2 % par 10 PV perdus

        if bonus_critique > 0:
            return {"bonus_crit_chance": bonus_critique}

    return None

def passif_le_roi(contexte, données):
    if contexte == "attaque":
        guild_id = données["guild_id"]
        cible_id = données["cible"]

        from data import hp
        cible_hp = hp.get(guild_id, {}).get(cible_id, 100)

        if cible_hp == 10:
            return {
                "finisher_royal": True,
                "ignorer_pb": True,
                "ignorer_reduction": True
            }

    elif contexte == "kill":
        return {
            "pv_gagnes": 10,
            "gif_special": "https://media4.giphy.com/media/v1.Y2lkPTc5MGI3NjExNGNqdDg4dmJ1aDVsbno5bzhjZDVzMHR5dXplZzhsaGptZjd3ZDY4OSZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/uD9ys1HkUSbuMJciFe/giphy.gif"  # à adapter si besoin
        }

    return None

def passif_valen_drexar(contexte, données):
    guild_id = données["guild_id"]
    user_id = données["user_id"]

    if contexte == "defense":
        import random

        # 15 % chance de réduction des dégâts
        if random.random() < 0.15:
            return {"reduction_multiplicative": 0.25, "annonce": "L'attaque est partiellement détournée par Valen Drexar 🧠."}

        # Bonus si sous 50 PV
        current_hp = hp.get(guild_id, {}).get(user_id, 100)
        seuils = [40, 30, 20, 10]

        reductions = 0
        gains_pb = 0
        id_clef = f"{guild_id}:{user_id}"
        if id_clef not in valen_seuils:
            valen_seuils[id_clef] = set()

        for seuil in seuils:
            if current_hp <= seuil and seuil not in valen_seuils[id_clef]:
                valen_seuils[id_clef].add(seuil)
                reductions += 10
                gains_pb += 5

        if gains_pb > 0:
            shields.setdefault(guild_id, {})
            shields[guild_id][user_id] = shields[guild_id].get(user_id, 0) + gains_pb

        if reductions > 0:
            return {"reduction_percent": reductions, "annonce": f"🧠 Valen Drexar renforce son contrôle : +{reductions}% résistance & +{gains_pb} PB."}

    elif contexte == "tentative_statut":
        return {"annuler_statut": True}

def passif_maitre_hotel(contexte, données):
    if contexte == "defense":
        effet = {}

        if random.random() < 0.30:
            effet["annuler_degats"] = True
            effet["annonce"] = "🎩✨ Le Maître d’Hôtel esquive l’attaque avec élégance !"
            return effet

        reduction = math.floor(données["degats_initiaux"] * 0.10)
        effet["reduction_fixe"] = reduction
        effet["annonce"] = f"🎩✨ Résistance passive du Maître d’Hôtel : -{reduction} dégât(s)."

        if random.random() < 0.20:
            contre_dgt = math.ceil(données["degats_initiaux"] / 4)
            effet["contre_attaque"] = {
                "degats": contre_dgt,
                "source": données["attaquant"],
                "cible": données["attaquant"]
            }
            effet["annonce"] += f" Il contre-attaque pour {contre_dgt} dégâts !"

        return effet

    elif contexte == "esquive":
        # Renvoi de l’attaque vers une cible aléatoire
        return {"rediriger": True, "copier_degats": True}

    return None

def passif_zeyra_kael(contexte, données):
    guild_id = données["guild_id"]
    uid = données["user_id"]
    now = time.time()

    if contexte == "attaque":
        hp_actuel = données.get("pv_actuel", 100)
        bonus = 0

        if hp_actuel < 100:
            perte = 100 - hp_actuel
            bonus = round(0.4 * (perte / 100), 3)  # en décimal (ex: 0.24)

        return {
            "bonus_degats_pourcent": bonus,
            "crit_multiplier": 0.5
        }

    elif contexte == "defense":
        effet = {"reduction_fixe": 1}

        hp_actuel = données.get("pv_actuel", 100)
        degats = données.get("degats_initiaux", 0)

        if hp_actuel - degats <= 0:
            last = zeyra_last_survive_time.get(guild_id, {}).get(uid, 0)
            if now - last > 86400:  # 24h
                zeyra_last_survive_time.setdefault(guild_id, {})[uid] = now
                effet["anti_ko"] = True
                effet["annonce"] = "💥 Zeyra refuse de tomber ! Elle reste à 1 PV grâce à sa Volonté de Fracture !"
                return effet

        return effet

    return None
    return None

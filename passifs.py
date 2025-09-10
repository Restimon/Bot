# passifs.py
import time
import random
import math

from data import (
    personnages_equipés,
    resistance_bonus,
    esquive_bonus,
    shields,
    infection_status,
    immunite_status,
    esquive_status,
    virus_status,
    poison_status,
    burn_status,
    malus_degat,
)
from personnage import PERSONNAGES
from cooldowns import daily_limit
from economy import add_gotcoins
from storage import get_user_data, hp
from utils import remove_random_item, give_random_item, get_random_enemy

# États internes pour quelques passifs
zeyra_last_survive_time: dict[str, dict[str, float]] = {}
valen_seuils: dict[str, set[int]] = {}


# =========================
# API publique utilisée par le moteur
# =========================
def appliquer_passif_utilisateur(guild_id: str, user_id: str, contexte: str, donnees: dict | None):
    """
    Récupère le personnage équipé de l'utilisateur et applique son passif.
    - guild_id, user_id: str
    - contexte: ex. "attaque", "defense", "soin_reçu", etc.
    - donnees: payload libre selon le contexte
    """
    gid, uid = str(guild_id), str(user_id)
    nom = personnages_equipés.get(gid, {}).get(uid)
    if not nom:
        return None

    personnage = PERSONNAGES.get(nom)
    if not personnage:
        return None

    # petite annotation pour le dispatcher
    personnage = dict(personnage)
    personnage["nom"] = nom
    return appliquer_passif(personnage, contexte, donnees or {})


# =========================
# Dispatcher interne
# =========================
def appliquer_passif(personnage: dict, contexte: str, donnees: dict):
    nom = personnage.get("nom")

    # mapping "nom → fonction"
    table = {
        "Cassiane Vale": passif_cassiane_vale,
        "Darin Venhal": passif_darin_venhal,
        "Elwin Jarr": passif_elwin_jarr,
        "Liora Venhal": passif_liora_venhal,
        "Maelis Dorné": passif_maelis_dorne,
        "Lior Danen": passif_lior_danen,
        "Nael Mirren": passif_nael_mirren,
        "Niv Kress": passif_niv_kress,
        "Lyss Tenra": passif_lyss_tenra,
        "Mira Oskra": passif_mira_oskra,
        "Sel Varnik": passif_sel_varnik,
        "Cielya Morn": passif_cielya_morn,
        "Kevar Rin": passif_kevar_rin,
        "Lysha Varn": passif_lysha_varn,
        "Kerin Dross": passif_kerin_dross,
        "Nova Rell": passif_nova_rell,
        "Raya Nys": passif_raya_nys,
        "Tessa Korrin": passif_tessa_korrin,
        "Alen Drave": passif_alen_drave,
        "Veylor Cassian": passif_veylor_cassian,
        "Darn Kol": passif_darn_kol,
        "Kara Drel": passif_kara_drel,
        "Nehra Vask": passif_nehra_vask,
        "Liane Rekk": passif_liane_rekk,
        "Sive Arden": passif_sive_arden,
        "Dr Aelran Vex": passif_aelran_vex,
        "Nyra Kell": passif_nyra_kell,
        "Kieran Vox": passif_kieran_vox,
        "Seren Iskar": passif_seren_iskar,
        "Silien Dorr": passif_silien_dorr,
        "Neyra Velenis": passif_neyra_velenis,
        "Rouven Mance": passif_rouven_mance,
        "Anna Lereux - Hôte Brisé": passif_anna_lereux,
        "Kael Dris": passif_kael_dris,
        "Marn Velk": passif_marn_velk,
        "Yann Tann": passif_yann_tann,
        "Dr. Elwin Kaas": passif_elwin_kaas,
        "Dr. Selina Vorne": passif_selina_vorne,
        "Alphonse Kaedrin": passif_alphonse_kaedrin,
        "Nathaniel Raskov": passif_nathaniel_raskov,
        "Elira Veska": passif_elira_veska,
        "Abomination Rampante": passif_abomination_rampante,
        "Varkhel Drayne": passif_varkhel_drayne,
        "Elya Varnis": passif_elya_varnis,
        "Le Roi": passif_le_roi,
        "Valen Drexar": passif_valen_drexar,
        "Maître d’Hôtel": passif_maitre_hotel,
        "Zeyra Kael": passif_zeyra_kael,
    }

    fn = table.get(nom)
    return fn(contexte, donnees) if fn else None


# =========================
# Passifs (définition des effets)
# =========================
def passif_cassiane_vale(contexte, d):
    if contexte == "defense":
        gid = str(d["guild_id"]); uid = str(d["defenseur"])
        now = time.time()
        bonus = resistance_bonus.setdefault(gid, {}).setdefault(uid, {"valeur": 0, "timestamp": now})
        if now - bonus["timestamp"] > 86400:
            bonus["valeur"] = 0
            bonus["timestamp"] = now
        bonus["valeur"] += 1
    elif contexte == "calcul_defense":
        gid = str(d["guild_id"]); uid = str(d["defenseur"])
        bonus = resistance_bonus.get(gid, {}).get(uid)
        if bonus and time.time() - bonus["timestamp"] < 86400:
            return {"reduction_degats": bonus["valeur"] / 100}
    return None


def passif_darin_venhal(contexte, d):
    if contexte == "calcul_defense" and random.random() <= 0.10:
        return {"reduction_multiplicateur": 0.5}
    return None


def passif_elwin_jarr(contexte, d):
    if contexte == "utilitaire_vol" and random.random() <= 0.10:
        return {"double_vol": True}
    return None


def passif_liora_venhal(contexte, d):
    if contexte == "defense" and random.random() <= 0.25:
        gid = str(d["guild_id"]); uid = str(d["defenseur"]); now = time.time()
        bonus = esquive_bonus.setdefault(gid, {}).setdefault(uid, {"valeur": 0, "timestamp": now})
        if now - bonus["timestamp"] > 86400:
            bonus["valeur"] = 0; bonus["timestamp"] = now
        bonus["valeur"] += 3
    elif contexte == "calcul_esquive":
        gid = str(d["guild_id"]); uid = str(d["defenseur"])
        bonus = esquive_bonus.get(gid, {}).get(uid)
        if bonus and time.time() - bonus["timestamp"] < 86400:
            return {"bonus_esquive": bonus["valeur"]}
    return None


def passif_maelis_dorne(contexte, d):
    if contexte == "purge_auto":
        gid = str(d["guild_id"]); uid = str(d["user_id"])
        now = time.time(); last = float(d.get("last_timestamp", now))
        heures = int((now - last) // 3600)
        if heures > 0 and random.random() < (heures / 100):
            return {"purger_statut": True}
    return None


def passif_lior_danen(contexte, d):
    if contexte == "daily" and random.random() <= 0.05:
        return {"double_daily": True}
    return None


def passif_nael_mirren(contexte, d):
    if contexte == "tirage_objet" and random.random() <= 0.01:
        return {"bonus_rarite": True}
    return None


def passif_niv_kress(contexte, d):
    if contexte == "utilitaire_vol" and random.random() <= 0.10:
        return {"conserver_objet_vol": True}
    return None


def passif_lyss_tenra(contexte, d):
    if contexte == "protection_vol":
        return {"immunise_contre_vol": True}
    return None


def passif_mira_oskra(contexte, d):
    if contexte == "defense_survie" and random.random() <= 0.03:
        return {"objet_bonus": random.choice(["❄️", "🔥", "🍀"])}
    return None


def passif_sel_varnik(contexte, d):
    if contexte == "vente_objet":
        return {"bonus_prix_vente": 1.25}
    return None


def passif_cielya_morn(contexte, d):
    if contexte == "calcul_defense":
        gid = str(d["guild_id"]); uid = str(d["defenseur"])
        if shields.get(gid, {}).get(uid, 0) > 0:
            return {"reduction_multiplicateur": 0.75}
    return None


def passif_kevar_rin(contexte, d):
    if contexte == "attaque":
        gid = str(d["guild_id"]); cid = str(d["cible_id"])
        if infection_status.get(gid, {}).get(cid):
            return {"bonus_degats": 3}
    return None


def passif_lysha_varn(contexte, d):
    if contexte == "soin":
        gid = str(d["guild_id"]); soigneur = str(d["soigneur"])
        shields.setdefault(gid, {})
        shields[gid][soigneur] = shields[gid].get(soigneur, 0) + 1
    return None


def passif_kerin_dross(contexte, d):
    if contexte == "soin":
        gid = str(d["guild_id"])
        # +1 PV à Kerin Dross s'il existe sur le serveur (5 % de chance)
        for pid, nom in personnages_equipés.get(gid, {}).items():
            if nom == "Kerin Dross" and random.random() <= 0.05:
                pid = str(pid)
                hp.setdefault(gid, {})
                hp[gid][pid] = min(100, hp[gid].get(pid, 0) + 1)
    return None


def passif_nova_rell(contexte, d):
    if contexte == "calcul_esquive":
        return {"bonus_esquive": 5}
    return None


def passif_raya_nys(contexte, d):
    if contexte == "max_pb":
        return {"max_pb": 25}
    return None


def passif_tessa_korrin(contexte, d):
    if contexte == "bonus_soin":
        return {"bonus_pv_soin": 1}
    return None


def passif_alen_drave(contexte, d):
    if contexte == "defense" and random.random() <= 0.05:
        return {"reduction_multiplicateur": 0.5}
    return None


def passif_veylor_cassian(contexte, d):
    if contexte == "defense":
        reduction = 1 + (2 if random.random() <= 0.5 else 0)
        return {"reduction_fixe": reduction}
    return None


def passif_darn_kol(contexte, d):
    if contexte == "attaque" and random.random() <= 0.10:
        gid = str(d["guild_id"]); att = str(d.get("attaquant_id") or d.get("attaquant"))
        hp.setdefault(gid, {})
        hp[gid][att] = min(hp[gid].get(att, 100) + 1, 100)
        import discord
        return {"embeds": [discord.Embed(description=f"❤️ <@{att}> récupère **1 PV** grâce à sa rage de combattant.",
                                         color=discord.Color.green())]}
    return None


def passif_kara_drel(contexte, d):
    if contexte == "attaque":
        gid = str(d["guild_id"]); cid = str(d["cible_id"])
        cible_pv = hp.get(gid, {}).get(cid, 100)
        if cible_pv < 25:
            return {"bonus_degats": 1}
    return None


def passif_nehra_vask(contexte, d):
    if contexte == "attaque" and random.random() <= (1/3):
        return {"ignorer_reduction_casque": True}
    return None


def passif_liane_rekk(contexte, d):
    if contexte == "attaque":
        return {"ignorer_reduction_casque": True}
    return None


def passif_sive_arden(contexte, d):
    if contexte == "attaque" and random.random() <= 0.05:
        add_gotcoins(str(d["guild_id"]), str(d.get("attaquant_id") or d.get("attaquant")), 1)
    return None


def passif_aelran_vex(contexte, d):
    if contexte == "soin_reçu":
        return {"multiplicateur_soin_recu": 1.5}
    return None


def passif_nyra_kell(contexte, d):
    if contexte == "daily_cooldown":
        return {"cooldown_multiplicateur": 0.5}
    return None


def passif_kieran_vox(contexte, d):
    if contexte == "box":
        return {"bonus_objets_box": 1}
    return None


def passif_seren_iskar(contexte, d):
    if contexte == "soin_reçu":
        gid = str(d["guild_id"]); cible = str(d["cible"]); soin = int(d.get("soin", 0))
        if daily_limit(gid, cible, "seren_pb_boost", limit=2):
            shields.setdefault(gid, {})
            shields[gid][cible] = shields[gid].get(cible, 0) + soin
    return None


def passif_silien_dorr(contexte, d):
    if contexte == "gain_gotcoins":
        add_gotcoins(str(d["guild_id"]), str(d["user_id"]), 1)
    return None


def passif_neyra_velenis(contexte, d):
    gid = str(d["guild_id"]); uid = str(d["defenseur"])
    if contexte == "defense":
        return {"reduction_multiplicateur": 0.9}
    if contexte == "attaque_reçue":
        now = time.time()
        esquive_status.setdefault(gid, {}).setdefault(uid, []).append({"bonus": 3, "expires": now + 3600})
        immunite_status.setdefault(gid, {}).setdefault(uid, []).append({"reduction": 0.05, "expires": now + 3600})
    return None


def passif_rouven_mance(contexte, d):
    if contexte != "attaque" or random.random() > 0.25:
        return None

    gid = str(d["guild_id"])
    att = str(d.get("attaquant_id") or d.get("attaquant"))
    cid = str(d["cible_id"])
    degats = int(d.get("degats", 0))

    effet = random.choice([
        "degats+", "vol", "soin", "gotcoins", "bouclier",
        "perte", "pas_de_conso", "revers"
    ])

    res = {"effet_roulette": effet}

    if effet == "degats+":
        res["bonus_degats"] = 10
    elif effet == "vol":
        item = remove_random_item(gid, cid)
        if item:
            give_random_item(gid, att, item)
    elif effet == "soin":
        hp.setdefault(gid, {})
        hp[gid][cid] = min(100, hp[gid].get(cid, 100) + degats)
    elif effet == "gotcoins":
        add_gotcoins(gid, att, 25)
    elif effet == "bouclier":
        shields.setdefault(gid, {})
        shields[gid][att] = shields[gid].get(att, 0) + degats
    elif effet == "perte":
        remove_random_item(gid, att)
    elif effet == "pas_de_conso":
        res["pas_de_conso"] = True
    elif effet == "revers":
        hp.setdefault(gid, {})
        hp[gid][att] = max(0, hp[gid].get(att, 100) - degats // 2)

    return res


def passif_anna_lereux(contexte, d):
    gid = str(d["guild_id"]); uid = str(d["user_id"])
    if contexte == "infection_provoquee":
        cid = str(d["cible_id"])
        infection_status.setdefault(gid, {}).setdefault(cid, {}).setdefault("bonus_dgt", 0)
        infection_status[gid][cid]["bonus_dgt"] += 1
    elif contexte == "tick_infection":
        if str(d["cible_id"]) == uid:
            return {"annuler_degats": True}
    elif contexte == "initialisation_personnage":
        infection_status.setdefault(gid, {}).setdefault(uid, {})["actif"] = True
    return None


def passif_kael_dris(contexte, d):
    if contexte != "degats_infliges":
        return None
    gid = str(d["guild_id"]); att = str(d["attaquant"]); deg = int(d.get("degats", 0))
    soin = int(deg * 0.5)
    hp.setdefault(gid, {})
    hp[gid][att] = min(hp[gid].get(att, 0) + soin, 100)
    return {"soin": soin}


def passif_marn_velk(contexte, d):
    if contexte == "attaque" and random.random() <= 0.05:
        return {"pas_de_conso": True}
    return None


def passif_yann_tann(contexte, d):
    if contexte != "attaque" or random.random() > 0.10:
        return None
    gid = str(d["guild_id"]); cid = str(d["cible_id"])
    att = str(d.get("attaquant_id") or d.get("attaquant"))
    channel_id = d.get("channel_id")
    burn_status.setdefault(gid, {})
    burn_status[gid][cid] = {
        "actif": True,
        "start_time": time.time(),
        "ticks_restants": 3,
        "next_tick": time.time() + 3600,
        "source": att,
        "channel_id": channel_id,
    }
    return {"brulure": True}


def passif_elwin_kaas(contexte, d):
    gid = str(d["guild_id"]); uid = str(d["user_id"])
    if contexte == "tick_heures":
        shields.setdefault(gid, {})
        shields[gid][uid] = min(shields[gid].get(uid, 0) + 1, 25)
    elif contexte == "tentative_poison":
        return {"annuler_poison": True}
    return None


def passif_selina_vorne(contexte, d):
    gid = str(d["guild_id"]); uid = str(d["user_id"])
    if contexte == "tick_heures":
        hp.setdefault(gid, {})
        hp[gid][uid] = min(hp[gid].get(uid, 0) + 2, 100)
    elif contexte == "tick_30min" and random.random() <= 0.20:
        for status_dict in [virus_status, poison_status, infection_status, burn_status]:
            if uid in status_dict.get(gid, {}):
                del status_dict[gid][uid]
                return {"status_supprimé": True}
    return None


def passif_alphonse_kaedrin(contexte, d):
    gid = str(d["guild_id"]); uid = str(d["user_id"])
    if contexte == "gain_gotcoins":
        montant = int(d.get("montant", 0))
        if random.random() <= 0.10:
            return {"gotcoins_bonus": montant}
    elif contexte == "gain_sur_attaque_alphonse":
        montant = int(d.get("montant", 0)); att = str(d["attaquant"])
        bonus = math.ceil(montant * 0.10)
        add_gotcoins(gid, uid, bonus)
        return {"passif_alphonse_bonus": bonus, "de": att}
    return None


def passif_nathaniel_raskov(contexte, d):
    gid = str(d["guild_id"]); uid = str(d["user_id"])
    if contexte == "defense" and random.random() <= 0.10:
        att = str(d["attaquant"])
        malus_degat.setdefault(gid, {})
        malus_degat[gid][att] = {"pourcentage": 10, "expiration": time.time() + 3600}
        return {"moitie_degats": True}
    elif contexte == "resistance_statuts":
        return {"resistance_bonus": 5}
    return None


def passif_elira_veska(contexte, d):
    gid = str(d["guild_id"]); uid = str(d["user_id"])
    if contexte == "passif_constant":
        return {"esquive_bonus": 10}
    elif contexte == "attaque_esquivee":
        exclude = [uid, str(d.get("attaquant_id") or d.get("attaquant"))]
        nouvelle = get_random_enemy(gid, exclude=exclude)
        if not nouvelle:
            return None
        shields.setdefault(gid, {})
        shields[gid][uid] = min(shields[gid].get(uid, 0) + 5, 25)
        return {"rediriger": True, "nouvelle_cible": nouvelle, "pb_bonus": 5}
    return None


def passif_abomination_rampante(contexte, d):
    gid = str(d["guild_id"]); uid = str(d["user_id"])
    if contexte == "attaque":
        cid = str(d["cible_id"]); effet = {}
        if random.random() <= 0.05 and cid not in infection_status.get(gid, {}):
            infection_status.setdefault(gid, {})[cid] = {
                "start": time.time(),
                "duration": 3 * 3600,
                "last_tick": 0,
                "source": uid,
                "channel_id": d.get("channel_id"),
            }
            effet["infection"] = True
        if cid in infection_status.get(gid, {}):
            effet["bonus_degats_percent"] = 30
        return effet or None
    elif contexte == "kill":
        hp.setdefault(gid, {})
        hp[gid][uid] = min(hp[gid].get(uid, 0) + 3, 100)
        return {"pv_gagnes": 3}
    elif contexte == "tick_infection" and str(d["cible_id"]) == uid:
        return {"annuler_degats": True}
    return None


def passif_varkhel_drayne(contexte, d):
    if contexte == "attaque":
        gid = str(d["guild_id"]); uid = str(d["user_id"])
        hp_actuel = hp.get(gid, {}).get(uid, 100)
        bonus = max(0, 100 - hp_actuel) // 10
        if bonus > 0:
            return {"bonus_degats_fixes": bonus}
    return None


def passif_elya_varnis(contexte, d):
    if contexte == "attaque":
        gid = str(d["guild_id"]); uid = str(d["user_id"])
        hp_actuel = hp.get(gid, {}).get(uid, 100)
        bonus_crit = (max(0, 100 - hp_actuel) // 10) * 2
        if bonus_crit > 0:
            return {"bonus_crit_chance": bonus_crit}
    return None


def passif_le_roi(contexte, d):
    if contexte == "attaque":
        gid = str(d["guild_id"]); cid = str(d["cible_id"])
        cible_hp = hp.get(gid, {}).get(cid, 100)
        if cible_hp == 10:
            return {"finisher_royal": True, "ignorer_pb": True, "ignorer_reduction": True}
    elif contexte == "kill":
        return {
            "pv_gagnes": 10,
            "gif_special": "https://media4.giphy.com/media/v1.Y2lkPTc5MGI3NjExNGNqdDg4dmJ1aDVsbno5bzhjZDVzMHR5dXplZzhsaGptZjd3ZDY4OSZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/uD9ys1HkUSbuMJciFe/giphy.gif",
        }
    return None


def passif_valen_drexar(contexte, d):
    gid = str(d["guild_id"]); uid = str(d["user_id"])
    if contexte == "defense":
        if random.random() < 0.15:
            return {"reduction_multiplicative": 0.25, "annonce": "L'attaque est partiellement détournée par Valen Drexar 🧠."}
        current_hp = hp.get(gid, {}).get(uid, 100)
        seuils = [40, 30, 20, 10]
        reductions = 0; gains_pb = 0
        key = f"{gid}:{uid}"
        valen_seuils.setdefault(key, set())
        for s in seuils:
            if current_hp <= s and s not in valen_seuils[key]:
                valen_seuils[key].add(s)
                reductions += 10
                gains_pb += 5
        if gains_pb > 0:
            shields.setdefault(gid, {})
            shields[gid][uid] = shields[gid].get(uid, 0) + gains_pb
        if reductions > 0:
            return {"reduction_percent": reductions, "annonce": f"🧠 Valen Drexar renforce son contrôle : +{reductions}% résistance & +{gains_pb} PB."}
    elif contexte == "tentative_statut":
        return {"annuler_statut": True}
    return None


def passif_maitre_hotel(contexte, d):
    if contexte == "defense":
        effet = {}
        if random.random() < 0.30:
            effet["annuler_degats"] = True
            effet["annonce"] = "🎩✨ Le Maître d’Hôtel esquive l’attaque avec élégance !"
            return effet
        reduction = math.floor(int(d.get("degats_initiaux", 0)) * 0.10)
        effet["reduction_fixe"] = reduction
        effet["annonce"] = f"🎩✨ Résistance passive du Maître d’Hôtel : -{reduction} dégât(s)."
        if random.random() < 0.20:
            contre_dgt = math.ceil(int(d.get("degats_initiaux", 0)) / 4)
            effet["contre_attaque"] = {
                "degats": contre_dgt,
                "source": str(d["attaquant"]),
                "cible": str(d["attaquant"]),
            }
            effet["annonce"] += f" Il contre-attaque pour {contre_dgt} dégâts !"
        return effet
    elif contexte == "esquive":
        return {"rediriger": True, "copier_degats": True}
    return None


def passif_zeyra_kael(contexte, d):
    gid = str(d["guild_id"]); uid = str(d["user_id"])
    now = time.time()
    if contexte == "attaque":
        hp_actuel = int(d.get("pv_actuel", 100))
        bonus_pct = 0.0
        if hp_actuel < 100:
            perte = 100 - hp_actuel
            bonus_pct = round(0.4 * (perte / 100), 3)  # ex: 24 PV manquants -> +0.096
        return {"bonus_degats_pourcent": bonus_pct, "crit_multiplier": 0.5}
    elif contexte == "defense":
        effet = {"reduction_fixe": 1}
        hp_actuel = int(d.get("pv_actuel", 100))
        degats = int(d.get("degats_initiaux", 0))
        if hp_actuel - degats <= 0:
            last = zeyra_last_survive_time.get(gid, {}).get(uid, 0)
            if now - last > 86400:
                zeyra_last_survive_time.setdefault(gid, {})[uid] = now
                effet["anti_ko"] = True
                effet["annonce"] = "💥 Zeyra refuse de tomber ! Elle reste à 1 PV grâce à sa Volonté de Fracture !"
                return effet
        return effet
    return None

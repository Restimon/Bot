# combat.py
import random
import time
import math
import discord

# ⚙️ Données partagées
from data import (
    virus_status,
    poison_status,
    infection_status,
    immunite_status,
    shields,
    casque_status,
    sauvegarder,
)
from storage import hp, get_user_data
from utils import get_mention, get_evade_chance, handle_death
from statuts import (
    appliquer_poison,
    appliquer_infection,
    appliquer_virus,
)
from embeds import build_embed_from_item, build_embed_transmission_virale
from economy import add_gotcoins
from passifs import appliquer_passif


# ------------------------------ Helpers sûrs ------------------------------
def _as_dict(x):
    return x if isinstance(x, dict) else {}

def _as_list(x):
    return x if isinstance(x, list) else []

def safe_embed(item, description, **kwargs):
    """Empêche un .get() interne à build_embed_from_item de faire planter l’attaque."""
    try:
        return build_embed_from_item(item, description, **kwargs)
    except Exception:
        # Fallback simple : on répond quoi qu’il arrive
        return discord.Embed(description=str(description), color=discord.Color.dark_grey())


# ------------------------------ API d’attaque principale ------------------------------
async def apply_item_with_cooldown(ctx, user_id, target_id, item, action):
    guild_id = str(ctx.guild.id)

    # 🔒 Normalisation de l'action (évite 'str' has no attribute 'get')
    if isinstance(action, dict):
        act = dict(action)  # copie pour éviter effets de bord
    else:
        # Valeurs par défaut très sûres
        act = {"type": "attaque", "degats": 0, "crit": 0.0}

    action_type = str(act.get("type", "attaque"))
    degats = int(act.get("degats", 0) or 0)
    crit = float(act.get("crit", 0.0) or 0.0)

    # 🩹 SOIN
    if action_type == "soin":
        act["item"] = item
        embed = await appliquer_soin(ctx, user_id, target_id, act)
        return embed, True

    # 🔍 VOL
    if action_type == "vol":
        user_inv, _, _ = get_user_data(guild_id, user_id)
        inv_cible, _, _ = get_user_data(guild_id, target_id)

        # ❌ Immunité au vol
        immunite = _as_dict(appliquer_passif("protection_vol", {
            "guild_id": guild_id,
            "user_id": target_id,
            "item": item,
            "attacker_id": user_id
        }))
        if immunite.get("immunise_contre_vol"):
            if item in user_inv:
                user_inv.remove(item)
                sauvegarder()
            embed = safe_embed(item, f"🛡️ {get_mention(ctx.guild, target_id)} est **protégé contre le vol** !")
            await ctx.followup.send(embed=embed)
            return None, True

        # Aucun objet à voler
        if not inv_cible:
            res = _as_dict(appliquer_passif("utilitaire_vol", {
                "guild_id": guild_id,
                "user_id": user_id,
                "item": item,
                "target_id": target_id
            }))
            if not res.get("conserver_objet_vol") and item in user_inv:
                user_inv.remove(item)
                sauvegarder()
            embed = safe_embed(item, f"🔍 {get_mention(ctx.guild, target_id)} n'a aucun objet à voler.")
            await ctx.followup.send(embed=embed)
            return None, True

        # 🎯 Vol au moins 1 objet
        stolen_items = [random.choice(inv_cible)]
        inv_cible.remove(stolen_items[0])

        # Passifs: double vol / conserver l'objet
        res = _as_dict(appliquer_passif("utilitaire_vol", {
            "guild_id": guild_id,
            "user_id": user_id,
            "item": item,
            "target_id": target_id
        }))
        if res.get("double_vol") and inv_cible:
            second_item = random.choice(inv_cible)
            inv_cible.remove(second_item)
            stolen_items.append(second_item)
        if not res.get("conserver_objet_vol", False) and item in user_inv:
            user_inv.remove(item)

        # Ajoute au voleur
        user_inv.extend(stolen_items)
        sauvegarder()

        obj_text = "** et **".join([f"**{obj}**" for obj in stolen_items])
        embed = safe_embed(item, f"🔍 {get_mention(ctx.guild, user_id)} a volé {obj_text} à {get_mention(ctx.guild, target_id)} !")
        await ctx.followup.send(embed=embed)
        return None, True

    # ⭐ Immunité
    if is_immune(guild_id, target_id):
        description = f"⭐ {get_mention(ctx.guild, target_id)} est protégé par une **immunité**."
        embed = safe_embed(item, description, disable_gif=True)
        await ctx.followup.send(embed=embed)
        return None, False

    # 💨 Esquive
    if random.random() < get_evade_chance(guild_id, target_id):
        description = f"💨 {get_mention(ctx.guild, target_id)} esquive habilement l’attaque de {get_mention(ctx.guild, user_id)} !"
        embed = safe_embed("💨", description)
        await ctx.followup.send(embed=embed)
        return None, False

    # 🎯 Calcul des dégâts
    result = await calculer_degats_complets(
        ctx, guild_id, user_id, target_id,
        degats, action_type, crit, item
    )

    # Type pour l’affichage
    type_cible_affichage = action_type if action_type in {"virus", "poison", "infection"} else "attaque"

    description = afficher_degats(ctx, user_id, target_id, item, result, type_cible=type_cible_affichage)
    embed = safe_embed(
        item,
        description,
        is_heal_other=False,
        is_crit=("💥" in result["crit_txt"])
    )
    await ctx.followup.send(embed=embed)

    # 🎁 Passif « survie »
    if hp[guild_id].get(target_id, 0) > 0:
        result_passif = _as_dict(appliquer_passif("defense_survie", {
            "guild_id": guild_id,
            "user_id": target_id,
            "attaquant": user_id,
            "item_utilise": item
        }))
        if result_passif.get("objet_bonus"):
            objet_bonus = result_passif["objet_bonus"]
            inv_cible, _, _ = get_user_data(guild_id, target_id)
            inv_cible.append(objet_bonus)
            embed_bonus = discord.Embed(
                description=f"🎁 {get_mention(ctx.guild, target_id)} a reçu un objet bonus grâce à son sang-froid : **{objet_bonus}** !",
                color=discord.Color.teal()
            )
            await ctx.followup.send(embed=embed_bonus)

    # 🔄 Effets secondaires
    for effet_embed in result["effets_embeds"]:
        await ctx.followup.send(embed=effet_embed)

    # 🛡 Bouclier détruit
    if result["shield_broken"]:
        shield_embed = safe_embed("🛡", f"Le bouclier de {get_mention(ctx.guild, target_id)} a été **détruit**.",
                                  is_heal_other=False, is_crit=False)
        shield_embed.set_image(url=None)
        await ctx.followup.send(embed=shield_embed)

    # 🧪 Statut post-attaque
    await appliquer_statut_si_necessaire(ctx, guild_id, user_id, target_id, action_type, index=0)

    # Types autorisés
    if action_type not in {"attaque", "poison", "virus", "infection", "vol", "soin"}:
        await ctx.followup.send(f"⚠️ Type d’objet inconnu : `{action_type}` pour l’objet {item}.")
        return None, False

    sauvegarder()
    return None, True

# ------------------------------ Petites briques ------------------------------
def is_immune(guild_id, user_id):
    return user_id in immunite_status.get(guild_id, {})

def apply_crit(base_dmg, crit_chance):
    if random.random() < float(crit_chance or 0.0):
        return base_dmg * 2, " 💥 **Coup critique !**"
    return base_dmg, ""

def apply_casque_reduction(guild_id, user_id, dmg, ignore=False):
    if ignore or user_id not in casque_status.get(guild_id, {}):
        return dmg, False, 0
    reduced_dmg = math.ceil(dmg * 0.5)
    reduction_val = dmg - reduced_dmg
    return reduced_dmg, True, reduction_val

def apply_shield(guild_id, user_id, dmg):
    current_shield = shields.get(guild_id, {}).get(user_id, 0)
    if current_shield <= 0:
        return dmg, 0, False
    lost_pb = min(dmg, current_shield)
    remaining_dmg = dmg - lost_pb
    shields.setdefault(guild_id, {})[user_id] = max(0, current_shield - lost_pb)
    return remaining_dmg, lost_pb, shields[guild_id][user_id] <= 0


# ------------------------------ Bonus/Statuts annexes ------------------------------
def get_statut_bonus(guild_id, user_id, target_id, channel_id, action_type):
    bonus_dmg = 0
    bonus_info = []
    source_to_credit = None
    effets_embed = []

    # 🧪 Poison → -1 dmg infligé par l’attaquant
    if user_id in poison_status.get(guild_id, {}):
        bonus_dmg -= 1
        bonus_info.append("-1 🧪")

    # 🧟 Infection (chez l’attaquant)
    infection_data = infection_status.get(guild_id, {}).get(user_id)
    if infection_data:
        source = infection_data.get("source")
        target_already_infected = target_id in infection_status.get(guild_id, {})

        # Bonus +2 tant que la cible n'est pas déjà infectée
        if source != target_id and not target_already_infected:
            bonus_dmg += 2
            bonus_info.append("+2 🧟")
            if source != user_id:
                source_to_credit = source

        # Propagation (25 %)
        if not target_already_infected and random.random() < 0.25:
            infection_status.setdefault(guild_id, {})[target_id] = {
                "start": time.time(),
                "duration": 3 * 3600,
                "last_tick": 0,
                "source": source,
                "channel_id": channel_id,
            }

            # Dégâts immédiats (après casque/bouclier)
            start_hp = hp[guild_id].get(target_id, 100)
            dmg_after_helmet, _, _ = apply_casque_reduction(guild_id, target_id, 5)
            dmg_after_shield, lost_pb, _ = apply_shield(guild_id, target_id, dmg_after_helmet)

            end_hp = max(0, start_hp - dmg_after_shield)
            hp[guild_id][target_id] = end_hp
            pertes = start_hp - end_hp

            effets_embed.append(safe_embed(
                "🧟",
                f"**GotValis** signale une propagation.\n<@{target_id}> a été infecté et perd {pertes} PV.",
                disable_gif=True,
                custom_title="🧟 Propagation d'infection"
            ))

            if end_hp == 0:
                handle_death(guild_id, target_id, source)
                effets_embed.append(safe_embed(
                    "🧟",
                    f"<@{target_id}> a succombé à une infection.",
                    disable_gif=True
                ))

            if source and source != target_id:
                add_gotcoins(guild_id, source, max(0, pertes), category="degats")

    # 🦠 Virus → transfert lors d’une attaque
    if action_type == "attaque" and user_id in virus_status.get(guild_id, {}):
        virus_data = virus_status[guild_id][user_id]
        source = virus_data.get("source")

        if not is_immune(guild_id, target_id):
            # Transmission
            virus_status.setdefault(guild_id, {})[target_id] = {
                "start": time.time(),
                "duration": 3 * 3600,
                "last_tick": 0,
                "source": source,
                "channel_id": channel_id,
            }

            # Auto-dégâts de transfert : 2 PV (après casque/bouclier)
            start_hp = hp[guild_id].get(user_id, 100)
            dmg_after_helmet, _, _ = apply_casque_reduction(guild_id, user_id, 2)
            dmg_after_shield, lost_pb, _ = apply_shield(guild_id, user_id, dmg_after_helmet)

            end_hp = max(0, start_hp - dmg_after_shield)
            hp[guild_id][user_id] = end_hp
            pertes = start_hp - end_hp

            if source and source != user_id:
                add_gotcoins(guild_id, source, max(0, pertes), category="degats")

            # On retire le virus de l’attaquant
            virus_status[guild_id].pop(user_id, None)

            effets_embed.append(build_embed_transmission_virale(
                from_user_mention=f"<@{user_id}>",
                to_user_mention=f"<@{target_id}>",
                pv_avant=start_hp,
                pv_apres=end_hp
            ))

            if end_hp == 0:
                handle_death(guild_id, user_id, source)
                effets_embed.append(safe_embed(
                    "🦠",
                    f"**GotValis** confirme la fin de cycle infectieux de <@{user_id}>."
                ))

    return bonus_dmg, bonus_info, source_to_credit, effets_embed


# ------------------------------ SOINS ------------------------------
async def appliquer_soin(ctx, user_id, target_id, action):
    guild_id = str(ctx.guild.id)
    heal_amount = int(action.get("soin", 0))
    crit = float(action.get("crit", 0.0) or 0.0)

    # Bonus du soigneur
    bonus_result = _as_dict(appliquer_passif(user_id, "bonus_soin", {
        "guild_id": guild_id,
        "soigneur": user_id,
        "cible": target_id,
        "base_soin": heal_amount
    }))
    heal_amount += int(bonus_result.get("bonus_pv_soin", 0))

    # Multiplicateur sur la cible
    multiplicateur_result = _as_dict(appliquer_passif(target_id, "soin_reçu", {
        "guild_id": guild_id,
        "soigneur": user_id,
        "cible": target_id,
        "base_soin": heal_amount
    }))
    multiplicateur = float(multiplicateur_result.get("multiplicateur_soin_recu", 1.0))
    heal_amount = math.ceil(heal_amount * multiplicateur)

    # Critique
    final_heal, crit_txt = apply_crit(heal_amount, crit)

    start_hp = hp[guild_id].get(target_id, 100)
    new_hp = min(100, start_hp + final_heal)
    hp[guild_id][target_id] = new_hp
    real_heal = new_hp - start_hp

    mention_soigneur = get_mention(ctx.guild, user_id)
    mention_cible = get_mention(ctx.guild, target_id)
    item = action["item"]

    if real_heal == 0:
        if user_id == target_id:
            description = f"🩹 GotValis : {mention_soigneur} tente de se soigner avec {item}...\n❤️ Mais ses PV sont déjà au maximum."
        else:
            description = f"🩹 GotValis : {mention_soigneur} tente de soigner {mention_cible} avec {item}...\n❤️ Mais {mention_cible} a déjà tous ses PV."
        return safe_embed(item, description, is_heal_other=(user_id != target_id), is_crit=False)

    add_gotcoins(guild_id, user_id, real_heal, category="soin")

    if user_id == target_id:
        ligne_1 = f"{mention_soigneur} se soigne de **{real_heal} PV** avec {item}"
    else:
        ligne_1 = f"{mention_soigneur} soigne de **{real_heal} PV** {mention_cible} avec {item}"
    ligne_2 = f"❤️ {start_hp} PV + {real_heal} PV = ❤️ {new_hp} PV{crit_txt}"

    # Post-soin
    _ = appliquer_passif(user_id, "soin", {
        "guild_id": guild_id,
        "soigneur": user_id,
        "cible": target_id,
        "soin_reel": real_heal
    })

    return safe_embed(item, f"{ligne_1}\n{ligne_2}", is_heal_other=(user_id != target_id), is_crit=False)


# ------------------------------ DÉGÂTS ------------------------------
async def calculer_degats_complets(ctx, guild_id, user_id, target_id, base_dmg, action_type, crit_chance, item):
    user_mention = get_mention(ctx.guild, user_id)
    target_mention = get_mention(ctx.guild, target_id)
    start_hp = hp[guild_id].get(target_id, 100)
    before_pb = shields.get(guild_id, {}).get(target_id, 0)

    bonus_dmg, bonus_info, src_credit, effets = get_statut_bonus(
        guild_id, user_id, target_id, ctx.channel.id if hasattr(ctx, "channel") else None, action_type
    )
    base_dmg_after_crit, crit_txt = apply_crit(int(base_dmg or 0), float(crit_chance or 0.0))

    # Passifs offensifs
    donnees_passif = {
        "guild_id": guild_id,
        "attaquant_id": user_id,
        "cible_id": target_id,
        "ctx": ctx,
        "degats": base_dmg_after_crit + bonus_dmg,
        "objet": item,
        "pv_actuel": hp[guild_id].get(user_id, 100),
    }
    result_passif_attaquant = _as_dict(appliquer_passif(user_id, "attaque", donnees_passif))
    ignore_helmet = result_passif_attaquant.get("ignorer_reduction_casque", False)
    ignore_pb = result_passif_attaquant.get("ignorer_pb", False)
    ignore_reduction = result_passif_attaquant.get("ignorer_reduction", False)

    # Défense immédiate
    donnees_defense_calc = {
        "guild_id": guild_id,
        "defenseur": target_id,
        "attaquant": user_id,
        "degats_initiaux": base_dmg_after_crit + bonus_dmg,
        "pv_actuel": start_hp,
    }
    res_maitre = _as_dict(appliquer_passif(target_id, "defense", donnees_defense_calc))

    if res_maitre.get("annuler_degats"):
        total_dmg = 0
        casque_active, reduction_val = False, 0
        if res_maitre.get("annonce"):
            effets.append(discord.Embed(description=res_maitre["annonce"], color=discord.Color.orange()))
    else:
        total_dmg, casque_active, reduction_val = apply_casque_reduction(
            guild_id, target_id, base_dmg_after_crit + bonus_dmg, ignore=ignore_helmet
        )
        if "reduction_fixe" in res_maitre:
            total_dmg = max(0, total_dmg - int(res_maitre["reduction_fixe"]))
            if res_maitre.get("annonce"):
                effets.append(discord.Embed(description=res_maitre["annonce"], color=discord.Color.orange()))

        if "contre_attaque" in res_maitre:
            data = res_maitre["contre_attaque"]
            await calculer_degats_complets(ctx, guild_id, data["source"], data["cible"], data["degats"], action_type, 0.0, None)

    # Réductions supplémentaires
    if not ignore_reduction:
        res_def = _as_dict(appliquer_passif(target_id, "calcul_defense", donnees_defense_calc))
        if "reduction_multiplicateur" in res_def:
            total_dmg = math.ceil(total_dmg * float(res_def["reduction_multiplicateur"]))
        if "reduction_degats" in res_def:
            total_dmg = math.ceil(total_dmg * (1 - float(res_def["reduction_degats"])))

        res_veylor = _as_dict(appliquer_passif(target_id, "defense", donnees_defense_calc))
        if "reduction_fixe" in res_veylor:
            total_dmg = max(0, total_dmg - int(res_veylor["reduction_fixe"]))

    # Bouclier
    if ignore_pb:
        dmg_final = total_dmg
        lost_pb = 0
        shield_broken = False
        pb_after = before_pb
    else:
        dmg_final, lost_pb, shield_broken = apply_shield(guild_id, target_id, total_dmg)
        pb_after = shields.get(guild_id, {}).get(target_id, 0)

    # Application PV
    end_hp = max(0, start_hp - dmg_final)
    hp[guild_id][target_id] = end_hp
    real_dmg = start_hp - end_hp

    if real_dmg > 0:
        add_gotcoins(guild_id, user_id, real_dmg, category="degats")
    if src_credit and src_credit != target_id:
        add_gotcoins(guild_id, src_credit, max(0, bonus_dmg), category="degats")

    # Vampirisme / autres effets post-dégâts
    res_kael = _as_dict(appliquer_passif(user_id, "degats_infliges", {
        "guild_id": guild_id,
        "attaquant": user_id,
        "cible_id": target_id,
        "degats": real_dmg
    }))
    if "soin" in res_kael:
        effets.append(discord.Embed(
            description=f"🩸 {user_mention} récupère **{res_kael['soin']} PV** grâce à son pouvoir vampirique.",
            color=discord.Color.red()
        ))

    # KO
    ko_embed = None
    reset_txt = ""
    if end_hp == 0:
        handle_death(guild_id, target_id, user_id)
        reset_txt = f"\n💀 {target_mention} est tombé à 0 PV et revient à 100 PV."
        ko_embed = discord.Embed(
            title="☠️ KO",
            description=f"**GotValis** détecte une défaillance vitale chez {target_mention}.",
            color=discord.Color.red()
        )
        result_kill = _as_dict(appliquer_passif(user_id, "kill", {
            "guild_id": guild_id,
            "user_id": user_id,
            "cible_id": target_id
        }))
        if "pv_gagnes" in result_kill:
            hp[guild_id][user_id] = min(hp[guild_id].get(user_id, 0) + int(result_kill["pv_gagnes"]), 100)
        if "gif_special" in result_kill:
            effets.append(discord.Embed(
                title="🎬 Exécution Royale",
                description=f"{user_mention} a achevé {target_mention} avec panache !",
            ).set_image(url=result_kill["gif_special"]))

    # Embeds additionnels éventuels (attaquant & défenseur)
    for e in _as_list(result_passif_attaquant.get("embeds")):
        effets.append(e)
    result_passif_cible = _as_dict(appliquer_passif(target_id, "defense", donnees_passif))
    for e in _as_list(result_passif_cible.get("embeds")):
        effets.append(e)

    pv_taken_base = max(0, base_dmg_after_crit - lost_pb)
    pb_taken_base = min(base_dmg_after_crit, lost_pb) if lost_pb > 0 else 0

    return {
        "dmg_final": dmg_final,
        "real_dmg": real_dmg,
        "lost_pb": lost_pb,
        "shield_broken": shield_broken,
        "start_hp": start_hp,
        "end_hp": end_hp,
        "before_pb": before_pb,
        "after_pb": pb_after,
        "bonus_info": bonus_info,
        "crit_txt": crit_txt,
        "effets_embeds": effets + ([ko_embed] if ko_embed else []),
        "reset_txt": reset_txt,
        "dmg_total_apres_reduc": total_dmg,
        "base_dmg_after_crit": base_dmg_after_crit,
        "casque_active": casque_active,
        "reduction_val": reduction_val,
        "pv_avant_bonus": pv_taken_base,
        "pb_avant_bonus": pb_taken_base,
    }


async def appliquer_statut_si_necessaire(ctx, guild_id, user_id, target_id, action_type, index=0):
    channel_id = ctx.channel.id if hasattr(ctx, "channel") else None

    if action_type == "poison":
        appliquer_poison(guild_id, target_id, channel_id, user_id)
        embed = safe_embed(
            "🧪",
            "Le poison infligera **3 PV** toutes les 30 minutes pendant 3 heures.\n"
            "⚠️ Les attaques de la cible infligeront **1 dégât de moins**.",
            disable_gif=True,
            custom_title="🧪 Contamination toxique"
        )
        await ctx.followup.send(embed=embed)

    elif action_type == "infection":
        appliquer_infection(guild_id, target_id, channel_id, user_id)
        embed = safe_embed(
            "🧟",
            "L’infection infligera **2 PV** toutes les 30 minutes pendant 3 heures.\n"
            "⚠️ Chaque attaque inflige **+2 dégâts** et peut propager l'infection.",
            disable_gif=True,
            custom_title="🧟 Infection déclenchée"
        )
        await ctx.followup.send(embed=embed)

    elif action_type == "virus" and index == 0:
        appliquer_virus(guild_id, target_id, channel_id, user_id)
        embed = safe_embed(
            "🦠",
            "Le virus infligera **5 PV** toutes les 30 minutes pendant 3 heures.\n"
            "⚠️ L’attaquant perd immédiatement **2 PV** en transférant le virus après l’attaque.",
            disable_gif=True,
            custom_title="🦠 Contamination virale"
        )
        await ctx.followup.send(embed=embed)
        virus_status[guild_id].pop(user_id, None)


# ------------------------------ Affichage ------------------------------
def afficher_degats(ctx, user_id, target_id, item, result, type_cible="attaque"):
    user_mention = get_mention(ctx.guild, user_id)
    target_mention = get_mention(ctx.guild, target_id)

    bonus_str = ""
    if result["bonus_info"]:
        bonus_str = " " + " ".join(f"{b[0]} {b[1:].strip()}" for b in result["bonus_info"])

    reduction_txt = str(result.get("reduction_val", 0)) if result.get("casque_active") else ""

    emoji_effet = ""
    if type_cible == "virus":
        emoji_effet = "🦠 "
    elif type_cible == "poison":
        emoji_effet = "🧪 "
    elif type_cible == "infection":
        emoji_effet = "🧟 "

    if type_cible == "virus":
        ligne1 = f"{user_mention} a contaminé {target_mention} avec {item}."
    elif type_cible == "poison":
        ligne1 = f"{user_mention} a empoisonné {target_mention} avec {item}."
    elif type_cible == "infection":
        ligne1 = f"{user_mention} a infecté {target_mention} avec {item}."
    else:
        ligne1 = f"{user_mention} inflige {result['dmg_total_apres_reduc']} dégâts à {target_mention} avec {item} !"

    if result["lost_pb"] and result["real_dmg"] == 0:
        if result.get("casque_active", False):
            ligne2 = f"{target_mention} perd ({result['base_dmg_after_crit']} PB - {reduction_txt} 🪖{bonus_str})"
            ligne3 = f"🛡️ {result['before_pb']} PB - ({result['base_dmg_after_crit']} PB - {reduction_txt} 🪖{bonus_str}) = 🛡️ {result['after_pb']} PB"
        else:
            ligne2 = f"{target_mention} perd ({result['base_dmg_after_crit']} PB{bonus_str})"
            ligne3 = f"🛡️ {result['before_pb']} PB - ({result['base_dmg_after_crit']} PB{bonus_str}) = 🛡️ {result['after_pb']} PB"

    elif result["lost_pb"] and result["real_dmg"] > 0:
        if result.get("casque_active", False):
            ligne2 = f"{target_mention} perd ({result['pv_avant_bonus']} PV - {reduction_txt} 🪖{bonus_str}) et {result['pb_avant_bonus']} PB"
            ligne3 = (
                f"❤️ {result['start_hp']} PV - ({result['pv_avant_bonus']} PV - {reduction_txt} 🪖{bonus_str}) / "
                f"🛡️ {result['before_pb']} PB - {result['pb_avant_bonus']} PB = "
                f"❤️ {result['end_hp']} PV / 🛡️ {result['after_pb']} PB"
            )
        else:
            ligne2 = f"{target_mention} perd ({result['pv_avant_bonus']} PV{bonus_str}) et {result['pb_avant_bonus']} PB"
            ligne3 = (
                f"❤️ {result['start_hp']} PV - ({result['pv_avant_bonus']} PV{bonus_str}) / "
                f"🛡️ {result['before_pb']} PB - {result['pb_avant_bonus']} PB = "
                f"❤️ {result['end_hp']} PV / 🛡️ {result['after_pb']} PB"
            )
    else:
        if result.get("casque_active", False):
            ligne2 = f"{target_mention} perd ({result['base_dmg_after_crit']} PV - {reduction_txt} 🪖{bonus_str})"
            ligne3 = f"❤️ {result['start_hp']} PV - ({result['base_dmg_after_crit']} PV - {reduction_txt} 🪖{bonus_str}) = ❤️ {result['end_hp']} PV"
        else:
            ligne2 = f"{target_mention} perd ({emoji_effet}{result['pv_avant_bonus']} PV{bonus_str})"
            ligne3 = f"❤️ {result['start_hp']} PV - ({result['pv_avant_bonus']} PV{bonus_str}) = ❤️ {result['end_hp']} PV"

    return f"{ligne1}\n{ligne2}\n{ligne3}{result['crit_txt']}{result['reset_txt']}"


# ------------------------------ Attaque en chaîne ------------------------------
async def apply_attack_chain(ctx, user_id, target_id, item, action):
    guild_id = str(ctx.guild.id)
    user_mention = get_mention(ctx.guild, user_id)

    # cibles secondaires
    all_members = [m for m in ctx.guild.members if not m.bot and m.id != int(target_id) and m.id != int(user_id)]
    random.shuffle(all_members)
    secondary_targets = all_members[:2]

    cibles = [(target_id, "principale")] + [(str(m.id), "secondaire") for m in secondary_targets]

    for i, (victim_id, type_cible) in enumerate(cibles):
        victim_mention = get_mention(ctx.guild, victim_id)

        if is_immune(guild_id, victim_id):
            description = f"⭐ {victim_mention} est protégé par une immunité. Aucun effet."
            embed = safe_embed(item, description)
            await ctx.followup.send(embed=embed)
            continue

        if random.random() < get_evade_chance(guild_id, victim_id):
            description = f"💨 {victim_mention} esquive l’attaque de {user_mention} !"
            embed = safe_embed("💨", description)
            await ctx.followup.send(embed=embed)
            continue

        dmg = 24 if i == 0 else 12
        result = await calculer_degats_complets(
            ctx, guild_id, user_id, victim_id,
            dmg, "attaque",
            action.get("crit", 0), item
        )

        ligne_type = "Attaque principale" if i == 0 else "Attaque secondaire"
        desc = afficher_degats(ctx, user_id, victim_id, item, result, type_cible="attaque")

        embed = safe_embed(
            item,
            f"**{ligne_type}** : {desc}",
            is_crit=("💥" in result["crit_txt"])
        )

        if i > 0:
            embed.set_image(url=None)
            embed.color = discord.Color.orange()
            embed.title = "⚔️ Attaque secondaire"

        await ctx.followup.send(embed=embed)

        for effet_embed in result["effets_embeds"]:
            await ctx.followup.send(embed=effet_embed)

        if result["shield_broken"]:
            shield_embed = safe_embed("🛡", f"Le bouclier de {victim_mention} a été **détruit**.")
            shield_embed.set_image(url=None)
            await ctx.followup.send(embed=shield_embed)

        await appliquer_statut_si_necessaire(ctx, guild_id, user_id, victim_id, "attaque", index=i)

    return None, True


import random
import time
import discord
import math 

from data import hp, leaderboard, virus_status, poison_status, infection_status, immunite_status, shields, casque_status, sauvegarder, resistance_bonus
from utils import get_mention, get_evade_chance
from statuts import appliquer_poison, appliquer_infection, appliquer_virus, appliquer_regen, supprimer_tous_statuts
from embeds import build_embed_from_item, build_embed_transmission_virale
from cooldowns import is_on_cooldown, set_cooldown
from economy import gotcoins_stats, gotcoins_balance, add_gotcoins, init_gotcoins_stats
from passifs import appliquer_passif
### 🔧 UTILITAIRES GÉNÉRAUX

async def apply_item_with_cooldown(ctx, user_id, target_id, item, action):

    guild_id = str(ctx.guild.id)

    # 🩹 SOIN
    if action["type"] == "soin":
        action["item"] = item
        embed = await appliquer_soin(ctx, user_id, target_id, action)
        return embed, True

    # 🪙 VOL
    if action["type"] == "vol":
        inv, _, _ = get_user_data(guild_id, target_id)
    
        # ❌ Vérifie si la cible est immunisée contre le vol (Lyss Tenra)
        immunite = appliquer_passif("protection_vol", {
            "guild_id": guild_id,
            "user_id": target_id,
            "item": item,
            "attacker_id": user_id
        })
    
        if immunite and immunite.get("immunise_contre_vol"):
            user_inv.remove(item)  # Tu perds l'objet utilisé
            sauvegarder()
            embed = build_embed_from_item(item, f"🛡️ {get_mention(ctx.guild, target_id)} est **protégé contre le vol** !")
            await ctx.followup.send(embed=embed)
            return None, True
    
        if not inv:
            # 🔄 Vérifie si l'attaquant peut tout de même conserver l'objet utilisé grâce à un passif
            result = appliquer_passif("utilitaire_vol", {
                "guild_id": guild_id,
                "user_id": user_id,
                "item": item,
                "target_id": target_id
            })
            conserve = result.get("conserver_objet_vol") if result else False
    
            if not conserve:
                user_inv.remove(item)  # ❌ Pas de chance, on perd l'objet
            sauvegarder()
    
            embed = build_embed_from_item(item, f"🔍 {get_mention(ctx.guild, target_id)} n'a aucun objet à voler.")
            await ctx.followup.send(embed=embed)
            return None, True
    
        # 🎯 Vol réussi (au moins 1 objet)
        stolen_items = [random.choice(inv)]
        inv.remove(stolen_items[0])
    
        # 🧠 Vérifie le passif de double vol (Elwin Jarr) + Niv Kress
        result = appliquer_passif("utilitaire_vol", {
            "guild_id": guild_id,
            "user_id": user_id,
            "item": item,
            "target_id": target_id
        })
    
        double_vol = result.get("double_vol", False) if result else False
        if double_vol and inv:
            second_item = random.choice(inv)
            inv.remove(second_item)
            stolen_items.append(second_item)
    
        conserve = result.get("conserver_objet_vol", False) if result else False
        if not conserve:
            user_inv.remove(item)
    
        # Ajoute les objets volés à l’attaquant
        attacker_inv, _, _ = get_user_data(guild_id, user_id)
        attacker_inv.extend(stolen_items)
    
        sauvegarder()
    
        obj_text = "** et **".join([f"**{obj}**" for obj in stolen_items])
        embed = build_embed_from_item(item, f"🔍 {get_mention(ctx.guild, user_id)} a volé {obj_text} à {get_mention(ctx.guild, target_id)} !")
        await ctx.followup.send(embed=embed)
    
        return None, True
        
    # ⭐ Immunité
    if is_immune(guild_id, target_id):
        description = f"⭐ {get_mention(ctx.guild, target_id)} est protégé par une **immunité**."
        embed = build_embed_from_item(item, description, disable_gif=True)
        await ctx.followup.send(embed=embed)
        return None, False

    # 💨 Esquive
    if random.random() < get_evade_chance(guild_id, target_id):
        description = f"💨 {get_mention(ctx.guild, target_id)} esquive habilement l’attaque de {get_mention(ctx.guild, user_id)} !"
        embed = build_embed_from_item("💨", description)
        await ctx.followup.send(embed=embed)
        return None, False

    # 🎯 Calcul des dégâts
    result = await calculer_degats_complets(
        ctx, guild_id, user_id, target_id,
        action.get("degats", 0), action["type"],
        action.get("crit", 0), item
    )

    # Choix du type_cible pour l'affichage correct
    type_cible_affichage = action["type"] if action["type"] in ["virus", "poison", "infection"] else "attaque"

    description = afficher_degats(ctx, user_id, target_id, item, result, type_cible=type_cible_affichage)
    embed = build_embed_from_item(
        item,
        description,
        is_heal_other=False,
        is_crit=("💥" in result["crit_txt"])
    )
    await ctx.followup.send(embed=embed)

    # 🎁 Mira Oskra : 3% de chance de recevoir un objet si elle survit
    if hp[guild_id].get(target_id, 0) > 0:  # la cible a survécu
        result_passif = appliquer_passif("defense_survie", {
            "guild_id": guild_id,
            "user_id": target_id,
            "attaquant": user_id,
            "item_utilise": item
        })
        if result_passif and result_passif.get("objet_bonus"):
            objet_bonus = result_passif["objet_bonus"]
            inv_cible, _, _ = get_user_data(guild_id, target_id)
            inv_cible.append(objet_bonus)
    
            embed_bonus = discord.Embed(
                description=f"🎁 {get_mention(ctx.guild, target_id)} a reçu un objet bonus grâce à son sang-froid : **{objet_bonus}** !",
                color=discord.Color.teal()
            )
            await ctx.followup.send(embed=embed_bonus)

    # 🔄 Effets secondaires (virus, infection…)
    for effet_embed in result["effets_embeds"]:
        await ctx.followup.send(embed=effet_embed)

    # 💥 Bouclier détruit
    if result["shield_broken"]:
        shield_embed = build_embed_from_item("🛡", f"Le bouclier de {get_mention(ctx.guild, target_id)} a été **détruit**.", is_heal_other=False, is_crit=False)
        shield_embed.set_image(url=None)  # Supprime le GIF manuellement
        await ctx.followup.send(embed=shield_embed)

    # 🧪 Appliquer statut
    await appliquer_statut_si_necessaire(ctx, guild_id, user_id, target_id, action["type"], index=0)


    if action["type"] not in ["attaque", "poison", "virus", "infection", "vol", "soin"]:
        await ctx.followup.send(f"⚠️ Type d’objet inconnu : `{action['type']}` pour l’objet {item}.")
        return None, False

    sauvegarder()  # <— à ajouter ici si pas déjà fait

    return None, True
        
def is_immune(guild_id, user_id):
    return user_id in immunite_status.get(guild_id, {})

def apply_crit(base_dmg, crit_chance):
    if random.random() < crit_chance:
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
    return remaining_dmg, lost_pb, current_shield - lost_pb <= 0

### 🧪🦠🧟 STATUTS SECONDAIRES

def get_statut_bonus(guild_id, user_id, target_id, channel_id, action_type):
    bonus_dmg = 0
    bonus_info = []
    source_to_credit = None
    effets_embed = []

    # --- 🧪 Poison ---
    if user_id in poison_status.get(guild_id, {}):
        bonus_dmg -= 1
        bonus_info.append("-1 🧪")

    # --- 🧟 Infection ---
    infection_data = infection_status.get(guild_id, {}).get(user_id)
    if infection_data:
        source = infection_data.get("source")
        target_already_infected = target_id in infection_status.get(guild_id, {})

        # Appliquer le bonus infection uniquement si la cible N'EST PAS déjà infectée
        if source != target_id and not target_already_infected:
            bonus_dmg += 2
            bonus_info.append("+2 🧟")
            if source != user_id:
                source_to_credit = source

        # Transmission potentielle
        if not target_already_infected and random.random() < 0.25:
            infection_status.setdefault(guild_id, {})[target_id] = {
                "start": time.time(),
                "duration": 3 * 3600,
                "last_tick": 0,
                "source": source,
                "channel_id": channel_id,
            }

            # Dégâts immédiats
            dmg = apply_casque_reduction(guild_id, target_id, 5)
            start_hp = hp[guild_id].get(target_id, 100)
            end_hp = max(0, start_hp - dmg)
            hp[guild_id][target_id] = end_hp

            effets_embed.append(build_embed_from_item(
                "🧟",
                f"**GotValis** signale une propagation.\n<@{target_id}> a été infecté et perd {start_hp - end_hp} PV.",
                disable_gif=True,  # Pour respecter ta demande précédente → pas de gif sur la propagation
                custom_title="🧟 Propagation d'infection"
            ))

            if end_hp == 0:
                handle_death(guild_id, target_id, source)
                effets_embed.append(build_embed_from_item(
                    "🧟",
                    f"<@{target_id}> a succombé à une infection.",
                    disable_gif=True
                ))

            if source != target_id:
                add_gotcoins(guild_id, source, start_hp - end_hp, category="degats")


    # --- 🦠 Virus ---
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

            # Auto-dégâts
            start_hp = hp[guild_id].get(user_id, 100)
            end_hp = max(0, start_hp - 2)
            hp[guild_id][user_id] = end_hp
            pertes = start_hp - end_hp

            if source != user_id:
                add_gotcoins(guild_id, source, pertes, category="degats")

            del virus_status[guild_id][user_id]

            effets_embed.append(build_embed_transmission_virale(
                from_user_mention=get_mention(channel_id, user_id),
                to_user_mention=get_mention(channel_id, target_id),
                pv_avant=start_hp,
                pv_apres=end_hp
            ))

            if end_hp == 0:
                handle_death(guild_id, user_id, source)
                effets_embed.append(build_embed_from_item(
                    "🦠",
                    f"**GotValis** confirme la fin de cycle infectieux de <@{user_id}>."
                ))

    # --- ✅ Retour sécurisé ---
    return bonus_dmg, bonus_info, source_to_credit, effets_embed

### 🎯 SOINS

async def appliquer_soin(ctx, user_id, target_id, action):
    guild_id = str(ctx.guild.id)
    heal_amount = action.get("soin", 0)
    crit = action.get("crit", 0)

    # 🎯 Bonus de soin appliqué par le soigneur (ex : Tessa Korrin)
    bonus_result = appliquer_passif(user_id, "bonus_soin", {
        "guild_id": guild_id,
        "soigneur": user_id,
        "cible": target_id,
        "base_soin": heal_amount
    })
    bonus_soin = bonus_result.get("bonus_pv_soin", 0) if bonus_result else 0
    heal_amount += bonus_soin

    # 🎯 Multiplicateur de soin reçu appliqué sur la cible (ex : Aelran Vex)
    multiplicateur_result = appliquer_passif(target_id, "soin_reçu", {
        "guild_id": guild_id,
        "soigneur": user_id,
        "cible": target_id,
        "base_soin": heal_amount
    })
    multiplicateur = multiplicateur_result.get("multiplicateur_soin_recu", 1.0) if multiplicateur_result else 1.0
    heal_amount = math.ceil(heal_amount * multiplicateur)

    # 🎲 Critique après bonus
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
        return build_embed_from_item(
            item=item,
            description=description,
            is_heal_other=(user_id != target_id),
            is_crit=False
        )

    # 💰 Gain de GotCoins lié au soin réel
    add_gotcoins(guild_id, user_id, real_heal, category="soin")

    # 📝 Affichage du soin
    if user_id == target_id:
        ligne_1 = f"{mention_soigneur} se soigne de **{real_heal} PV** avec {item}"
    else:
        ligne_1 = f"{mention_soigneur} soigne de **{real_heal} PV** {mention_cible} avec {item}"
    ligne_2 = f"❤️ {start_hp} PV + {real_heal} PV = ❤️ {new_hp} PV"
    if crit_txt:
        ligne_2 += f" {crit_txt}"

    # 🎯 Appel d’autres passifs post-soin (ex : Lysha Varn)
    appliquer_passif(user_id, "soin", {
        "guild_id": guild_id,
        "soigneur": user_id,
        "cible": target_id,
        "soin_reel": real_heal
    })

    return build_embed_from_item(
        item=item,
        description=f"{ligne_1}\n{ligne_2}",
        is_heal_other=(user_id != target_id),
        is_crit=False
    )

### 🎯 CALCUL DES DÉGÂTS
async def calculer_degats_complets(ctx, guild_id, user_id, target_id, base_dmg, action_type, crit_chance, item):
    user_mention = get_mention(ctx.guild, user_id)
    target_mention = get_mention(ctx.guild, target_id)
    start_hp = hp[guild_id].get(target_id, 100)
    before_pb = shields.get(guild_id, {}).get(target_id, 0)

    bonus_dmg, bonus_info, src_credit, effets = get_statut_bonus(
        guild_id, user_id, target_id, ctx.channel.id, action_type
    )
    base_dmg_after_crit, crit_txt = apply_crit(base_dmg, crit_chance)

    # 🎯 Passifs offensifs
    contexte = "attaque"
    donnees_passif = {
        "guild_id": guild_id,
        "attaquant_id": user_id,
        "cible_id": target_id,
        "ctx": ctx,
        "degats": base_dmg_after_crit + bonus_dmg,
        "objet": item,
        "pv_actuel": hp[guild_id].get(user_id, 100)
    }
    result_passif_attaquant = appliquer_passif(user_id, contexte, donnees_passif)
    ignore_helmet = result_passif_attaquant.get("ignorer_reduction_casque", False) if result_passif_attaquant else False
    ignore_pb = result_passif_attaquant.get("ignorer_pb", False) if result_passif_attaquant else False
    ignore_reduction = result_passif_attaquant.get("ignorer_reduction", False) if result_passif_attaquant else False

    # 🧿 Passifs défensifs immédiats
    donnees_defense_calc = {
        "guild_id": guild_id,
        "defenseur": target_id,
        "attaquant": user_id,
        "degats_initiaux": base_dmg_after_crit + bonus_dmg,
        "pv_actuel": start_hp
    }
    res_maitre = appliquer_passif(target_id, "defense", donnees_defense_calc)

    if res_maitre and res_maitre.get("annuler_degats"):
        total_dmg = 0
        casque_active, reduction_val = False, 0
        effets.append(discord.Embed(description=res_maitre.get("annonce"), color=discord.Color.orange()))
    else:
        total_dmg, casque_active, reduction_val = apply_casque_reduction(
            guild_id, target_id, base_dmg_after_crit + bonus_dmg, ignore=ignore_helmet
        )

        if res_maitre and "reduction_fixe" in res_maitre:
            total_dmg = max(0, total_dmg - res_maitre["reduction_fixe"])
            effets.append(discord.Embed(description=res_maitre.get("annonce"), color=discord.Color.orange()))

        if res_maitre and "contre_attaque" in res_maitre:
            data = res_maitre["contre_attaque"]
            await calculer_degats_complets(ctx, guild_id, data["source"], data["cible"], data["degats"], action_type, 0.0, None)

    if not ignore_reduction:
        res_def = appliquer_passif(target_id, "calcul_defense", donnees_defense_calc)
        if res_def:
            if "reduction_multiplicateur" in res_def:
                total_dmg = math.ceil(total_dmg * res_def["reduction_multiplicateur"])
            if "reduction_degats" in res_def:
                total_dmg = math.ceil(total_dmg * (1 - res_def["reduction_degats"]))
        res_veylor = appliquer_passif(target_id, "defense", donnees_defense_calc)
        if res_veylor and "reduction_fixe" in res_veylor:
            total_dmg = max(0, total_dmg - res_veylor["reduction_fixe"])

    # 🛡 Bouclier
    if ignore_pb:
        dmg_final = total_dmg
        lost_pb = 0
        shield_broken = False
        pb_after = before_pb
    else:
        dmg_final, lost_pb, shield_broken = apply_shield(guild_id, target_id, total_dmg)
        pb_after = shields.get(guild_id, {}).get(target_id, 0)

    # 🔻 Appliquer dégâts
    end_hp = max(0, start_hp - dmg_final)
    hp[guild_id][target_id] = end_hp
    real_dmg = start_hp - end_hp

    if real_dmg > 0:
        add_gotcoins(guild_id, user_id, real_dmg, category="degats")
    if src_credit and src_credit != target_id:
        add_gotcoins(guild_id, src_credit, bonus_dmg, category="degats")

    # 🧛 Passif Kael Dris (soin vampirique)
    res_kael = appliquer_passif(user_id, "degats_infliges", {
        "guild_id": guild_id,
        "attaquant": user_id,
        "cible_id": target_id,
        "degats": real_dmg
    })
    if res_kael and "soin" in res_kael:
        effets.append(discord.Embed(
            description=f"🩸 {user_mention} récupère **{res_kael['soin']} PV** grâce à son pouvoir vampirique.",
            color=discord.Color.red()
        ))

    # 💀 KO
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
        result_kill = appliquer_passif(user_id, "kill", {
            "guild_id": guild_id,
            "user_id": user_id,
            "cible_id": target_id
        })
        if result_kill:
            if "pv_gagnes" in result_kill:
                hp[guild_id][user_id] = min(hp[guild_id].get(user_id, 0) + result_kill["pv_gagnes"], 100)
            if "gif_special" in result_kill:
                effets.append(discord.Embed(
                    title="🎬 Exécution Royale",
                    description=f"{user_mention} a achevé {target_mention} avec panache !",
                ).set_image(url=result_kill["gif_special"]))

    # Autres passifs défensifs
    result_passif_cible = appliquer_passif(target_id, "défense", donnees_passif)
    if result_passif_attaquant:
        effets.extend(result_passif_attaquant.get("embeds", []))
    if result_passif_cible:
        effets.extend(result_passif_cible.get("embeds", []))

    # Affichage
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
        "dmg_total_affiche": base_dmg_after_crit + bonus_dmg,
        "total_affiche_pour_ligne1": real_dmg + lost_pb,
        "dmg_total_apres_bonus_et_crit": base_dmg_after_crit + bonus_dmg,
        "base_dmg_after_crit": base_dmg_after_crit,
        "casque_active": casque_active,
        "total_ressenti": real_dmg + lost_pb,
        "total_dmg_apres_reduc": total_dmg,
        "reduction_val": reduction_val,
        "pv_avant_bonus": pv_taken_base,
        "pb_avant_bonus": pb_taken_base,
    }

    
async def appliquer_statut_si_necessaire(ctx, guild_id, user_id, target_id, action_type, index=0):
    """Applique les statuts appropriés après une attaque."""
    # Récupération sécurisée du channel_id
    channel_id = None
    if hasattr(ctx, "channel") and ctx.channel:
        channel_id = ctx.channel.id
    elif hasattr(ctx, "channel_id"):
        channel_id = ctx.channel_id

    # POISON
    if action_type == "poison":
        appliquer_poison(guild_id, target_id, channel_id, user_id)

        embed = build_embed_from_item(
            "🧪",
            f"Le poison infligera **3 PV** toutes les 30 minutes pendant 3 heures.\n"
            f"⚠️ Les attaques de la cible infligeront **1 dégât de moins**.",
            disable_gif=True,
            custom_title="🧪 Contamination toxique"
        )
        await ctx.followup.send(embed=embed)

    # INFECTION
    elif action_type == "infection":
        appliquer_infection(guild_id, target_id, channel_id, user_id)
        
        embed = build_embed_from_item(
            "🧟",
            f"L’infection infligera **2 PV** toutes les 30 minutes pendant 3 heures.\n"
            f"⚠️ Chaque attaque inflige **+2 dégâts** et peut propager l'infection.",
            disable_gif=True,
            custom_title="🧟 Infection déclenchée"
        )
        await ctx.followup.send(embed=embed)

    # VIRUS
    elif action_type == "virus" and index == 0:
        appliquer_virus(guild_id, target_id, channel_id, user_id)

        embed = build_embed_from_item(
            "🦠",
            f"Le virus infligera **5 PV** toutes les 30 minutes pendant 3 heures.\n"
            f"⚠️ L’attaquant perd immédiatement **2 PV** en transférant le virus après l’attaque.",
            disable_gif=True,
            custom_title="🦠 Contamination virale"
        )
        await ctx.followup.send(embed=embed)

        # Supprimer le virus de l’attaquant après transmission
        virus_status[guild_id].pop(user_id, None)

### 🎯 FORMATTEUR DE MESSAGE

def afficher_degats(ctx, user_id, target_id, item, result, type_cible="attaque"):
    user_mention = get_mention(ctx.guild, user_id)
    target_mention = get_mention(ctx.guild, target_id)

    # Format du bonus propre
    bonus_str = ""
    if result['bonus_info']:
        bonus_str = " " + " ".join(
            f"{b[0]} {b[1:].strip()}" for b in result['bonus_info']
        )
    else:
        bonus_str = ""

    # Texte de réduction (casque)
    if result.get("casque_active", False):
        reduction_txt = str(result.get("reduction_val", 0))
    else:
        reduction_txt = ""

    # Emoji selon type_cible
    emoji_effet = ""
    if type_cible == "virus":
        emoji_effet = "🦠 "
    elif type_cible == "poison":
        emoji_effet = "🧪 "
    elif type_cible == "infection":
        emoji_effet = "🧟 "

    # Ligne 1 adaptée selon type_cible
    if type_cible == "virus":
        ligne1 = f"{user_mention} a contaminé {target_mention} avec {item}."
    elif type_cible == "poison":
        ligne1 = f"{user_mention} a empoisonné {target_mention} avec {item}."
    elif type_cible == "infection":
        ligne1 = f"{user_mention} a infecté {target_mention} avec {item}."
    else:
        # ATTENTION : ici on affiche bien les dégâts "envoyés", pas les dégâts réellement subis
        ligne1 = f"{user_mention} inflige {result['total_dmg_apres_reduc']} dégâts à {target_mention} avec {item} !"

    # Ligne 2 + Ligne 3 selon cas
    if result["lost_pb"] and result["real_dmg"] == 0:
        # Bouclier uniquement
        if result.get("casque_active", False):
            ligne2 = f"{target_mention} perd ({result['base_dmg_after_crit']} PB - {reduction_txt} 🪖{bonus_str})"
            ligne3 = (
                f"🛡️ {result['before_pb']} PB - ({result['base_dmg_after_crit']} PB - {reduction_txt} 🪖{bonus_str}) = "
                f"🛡️ {result['after_pb']} PB"
            )
        else:
            ligne2 = f"{target_mention} perd ({result['base_dmg_after_crit']} PB{bonus_str})"
            ligne3 = f"🛡️ {result['before_pb']} PB - ({result['base_dmg_after_crit']} PB{bonus_str}) = 🛡️ {result['after_pb']} PB"

    elif result["lost_pb"] and result["real_dmg"] > 0:
        # Bouclier + PV
        if result.get("casque_active", False):
            ligne2 = (
                f"{target_mention} perd ({result['pv_avant_bonus']} PV - {reduction_txt} 🪖{bonus_str}) "
                f"et {result['pb_avant_bonus']} PB"
            )
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
        # PV uniquement
        if result.get("casque_active", False):
            ligne2 = f"{target_mention} perd ({result['base_dmg_after_crit']} PV - {reduction_txt} 🪖{bonus_str})"
            ligne3 = f"❤️ {result['start_hp']} PV - ({result['base_dmg_after_crit']} PV - {reduction_txt} 🪖{bonus_str}) = ❤️ {result['end_hp']} PV"
        else:
            ligne2 = f"{target_mention} perd ({emoji_effet}{result['pv_avant_bonus']} PV{bonus_str})"
            ligne3 = f"❤️ {result['start_hp']} PV - ({result['pv_avant_bonus']} PV{bonus_str}) = ❤️ {result['end_hp']} PV"

    # Retour complet
    return f"{ligne1}\n{ligne2}\n{ligne3}{result['crit_txt']}{result['reset_txt']}"

### ☠️ ATTAQUE EN CHAÎNE

async def apply_attack_chain(ctx, user_id, target_id, item, action):
    guild_id = str(ctx.guild.id)
    user_mention = get_mention(ctx.guild, user_id)

    # 🎯 Sélection des cibles secondaires
    all_members = [m for m in ctx.guild.members if not m.bot and m.id != target_id and m.id != user_id]
    random.shuffle(all_members)
    secondary_targets = all_members[:2]

    # 📦 Cibles complètes
    cibles = [(target_id, "principale")] + [(m.id, "secondaire") for m in secondary_targets]

    for i, (victim_id, type_cible) in enumerate(cibles):
        victim_mention = get_mention(ctx.guild, victim_id)

        # ⭐ Immunité
        if is_immune(guild_id, victim_id):
            description = f"⭐ {victim_mention} est protégé par une immunité. Aucun effet."
            embed = build_embed_from_item(item, description)
            await ctx.followup.send(embed=embed)
            continue

        # 💨 Esquive
        if random.random() < get_evade_chance(guild_id, victim_id):
            description = f"💨 {victim_mention} esquive l’attaque de {user_mention} !"
            embed = build_embed_from_item("💨", description)
            await ctx.followup.send(embed=embed)
            continue

        # 🎯 Dégâts
        dmg = 24 if i == 0 else 12
        result = await calculer_degats_complets(
            ctx, guild_id, user_id, victim_id,
            dmg, "attaque",  # toujours "attaque" pour l'effet
            action.get("crit", 0), item
        )

        # 📝 Message personnalisé
        ligne_type = "Attaque principale" if i == 0 else "Attaque secondaire"
        desc = afficher_degats(ctx, user_id, victim_id, item, result, type_cible=ligne_type.lower())

        # Construction de l'embed
        embed = build_embed_from_item(
            item,
            f"**{ligne_type}** : {desc}",
            is_crit=("💥" in result["crit_txt"])
        )

        # Si attaque secondaire : désactive le GIF et change la couleur
        if i > 0:
            embed.set_image(url=None)
            embed.color = discord.Color.orange()

            # Change aussi le titre
            embed.title = "⚔️ Attaque secondaire"

        # Envoi de l'embed
        await ctx.followup.send(embed=embed)

        # 📤 Effets secondaires
        for effet_embed in result["effets_embeds"]:
            await ctx.followup.send(embed=effet_embed)

        # 🛡 Bouclier détruit
        if result["shield_broken"]:
            shield_embed = build_embed_from_item("🛡", f"Le bouclier de {victim_mention} a été **détruit**.")
            shield_embed.set_image(url=None)  # désactive le GIF
            await ctx.followup.send(embed=shield_embed)

        # 🧪 Statuts à appliquer (uniquement sur première cible pour certains)
        await appliquer_statut_si_necessaire(ctx, guild_id, user_id, victim_id, "attaque", index=i)

    return None, True


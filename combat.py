import random
import time
import discord

from data import hp, leaderboard, virus_status, poison_status, infection_status, immunite_status, shields, casque_status, sauvegarder
from utils import get_mention, get_evade_chance
from statuts import appliquer_poison, appliquer_infection, appliquer_virus, appliquer_regen, supprimer_tous_statuts
from embeds import build_embed_from_item, build_embed_transmission_virale
from cooldowns import is_on_cooldown, set_cooldown

### 🔧 UTILITAIRES GÉNÉRAUX

async def apply_item_with_cooldown(ctx, user_id, target_id, item, action):
    pass  # ou rien
    guild_id = str(ctx.guild.id)

    # 🩹 SOIN
    if action["type"] == "soin":
        action["item"] = item
        embed = await appliquer_soin(ctx, user_id, target_id, action)
        return embed, True

    # ⭐ Immunité
    if is_immune(guild_id, target_id):
        description = f"⭐ {get_mention(ctx.guild, target_id)} est protégé par une **immunité**."
        embed = build_embed_from_item(item, description)
        await ctx.followup.send(embed=embed)
        return None, False

    # 💨 Esquive
    if random.random() < get_evade_chance(guild_id, target_id):
        description = f"💨 {get_mention(ctx.guild, target_id)} esquive habilement l’attaque de {get_mention(ctx.guild, user_id)} !"
        embed = build_embed_from_item("💨", description)
        await ctx.followup.send(embed=embed)
        return None, False

    if action["type"] == "vol":
        # Test d'esquive et immunité déjà passés
        from inventory import voler_objet
        vol_result = voler_objet(ctx.guild.id, target_id, user_id)
        if vol_result:
            description = f"🔍 {get_mention(ctx.guild, user_id)} a volé **{vol_result}** à {get_mention(ctx.guild, target_id)}."
        else:
            description = f"🔍 {get_mention(ctx.guild, user_id)} a tenté de voler {get_mention(ctx.guild, target_id)} mais n’a rien trouvé."
        embed = build_embed_from_item(item, description)
        await ctx.followup.send(embed=embed)
        return None, True

    # 🎯 Calcul des dégâts
    result = await calculer_degats_complets(
        ctx, guild_id, user_id, target_id,
        action.get("degats", 0), action["type"],
        action.get("crit", 0), item
    )

    # 📝 Message principal
    description = afficher_degats(ctx, user_id, target_id, item, result)
    embed = build_embed_from_item(
        item,
        description,
        is_heal_other=False,
        is_crit=("💥" in result["crit_txt"])
    )
    await ctx.followup.send(embed=embed)

    # 🔄 Effets secondaires (virus, infection…)
    for effet_embed in result["effets_embeds"]:
        await ctx.send(embed=effet_embed)

    # 💥 Bouclier détruit
    if result["shield_broken"]:
        shield_embed = build_embed_from_item("🛡", f"Le bouclier de {get_mention(ctx.guild, target_id)} a été **détruit**.", is_heal_other=False, is_crit=False)
        shield_embed.set_image(url=None)  # Supprime le GIF manuellement
        await ctx.followup.send(embed=shield_embed)

    # 🧪 Appliquer statut
    await appliquer_statut_si_necessaire(ctx, guild_id, user_id, target_id, action["type"], index=0)


    if action["type"] not in ["attaque", "poison", "virus", "infection", "vol", "soin"]:
        await ctx.send(f"⚠️ Type d’objet inconnu : `{action['type']}` pour l’objet {item}.")
        return None, False

    sauvegarder()  # <— à ajouter ici si pas déjà fait

    return None, True
        
def is_immune(guild_id, user_id):
    return user_id in immunite_status.get(guild_id, {})

def apply_crit(base_dmg, crit_chance):
    if random.random() < crit_chance:
        return base_dmg * 2, " 💥 **Coup critique !**"
    return base_dmg, ""

def apply_casque_reduction(guild_id, user_id, dmg):
    if user_id in casque_status.get(guild_id, {}):
        return int(dmg * 0.5)
    return dmg

def apply_shield(guild_id, user_id, dmg):
    current_shield = shields.get(guild_id, {}).get(user_id, 0)
    if current_shield <= 0:
        return dmg, 0, False
    lost_pb = min(dmg, current_shield)
    remaining_dmg = dmg - lost_pb
    shields.setdefault(guild_id, {})[user_id] = max(0, current_shield - lost_pb)
    return remaining_dmg, lost_pb, current_shield - lost_pb <= 0

def update_leaderboard_dmg(guild_id, source_id, dmg):
    leaderboard.setdefault(guild_id, {}).setdefault(source_id, {"degats": 0, "soin": 0, "kills": 0, "morts": 0})
    leaderboard[guild_id][source_id]["degats"] += dmg

### 🧪🦠🧟 STATUTS SECONDAIRES

def get_statut_bonus(guild_id, user_id, target_id, channel_id, action_type):
    bonus_dmg = 0
    bonus_info = []
    source_to_credit = None
    effets_embed = []

    # --- 🧪 Poison ---
    if target_id in poison_status.get(guild_id, {}):
        bonus_dmg -= 1
        bonus_info.append("-1 🧪")

    # --- 🧟 Infection ---
    infection_data = infection_status.get(guild_id, {}).get(user_id)
    if infection_data:
        source = infection_data.get("source")
        if source != target_id:
            bonus_dmg += 2
            bonus_info.append("+2 🧟")
            if source != user_id:
                source_to_credit = source

            # Transmission potentielle
            target_already_infected = target_id in infection_status.get(guild_id, {})
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
                    f"**GotValis** signale une propagation.\n<@{target_id}> a été infecté et perd {start_hp - end_hp} PV."
                ))

                if end_hp == 0:
                    handle_death(guild_id, target_id, source)
                    effets_embed.append(build_embed_from_item(
                        "🧟",
                        f"<@{target_id}> a succombé à une infection."
                    ))

                if source != target_id:
                    update_leaderboard_dmg(guild_id, source, start_hp - end_hp)

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
                update_leaderboard_dmg(guild_id, source, pertes)

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
    bonus_summary = " ".join(bonus_info)
    return bonus_dmg, bonus_summary, source_to_credit, effets_embed


### 🎯 SOINS

async def appliquer_soin(ctx, user_id, target_id, action):
    guild_id = str(ctx.guild.id)
    heal_amount = action.get("soin", 0)
    crit = action.get("crit", 0)
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

    leaderboard.setdefault(guild_id, {}).setdefault(user_id, {"degats": 0, "soin": 0, "kills": 0, "morts": 0})
    leaderboard[guild_id][user_id]["soin"] += real_heal

    # Ligne 1 : action de soin
    if user_id == target_id:
        ligne_1 = f"{mention_soigneur} se soigne de **{real_heal} PV** avec {item}"
    else:
        ligne_1 = f"{mention_soigneur} soigne de **{real_heal} PV** {mention_cible} avec {item}"
    if crit_txt:
        ligne_1 += f" {crit_txt}"

    # Ligne 2 : calcul des PV
    ligne_2 = f"❤️ {start_hp} PV + {real_heal} PV = {new_hp} PV"

    return build_embed_from_item(
        item=item,
        description=f"{ligne_1}\n{ligne_2}",
        is_heal_other=(user_id != target_id),
        is_crit=("💥" in crit_txt)
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

    base_dmg, crit_txt = apply_crit(base_dmg, crit_chance)
    total_dmg = apply_casque_reduction(guild_id, target_id, base_dmg + bonus_dmg)
    dmg_final, lost_pb, shield_broken = apply_shield(guild_id, target_id, total_dmg)
    pb_after = shields.get(guild_id, {}).get(target_id, 0)

    end_hp = max(0, start_hp - dmg_final)
    hp[guild_id][target_id] = end_hp
    real_dmg = start_hp - end_hp

    if real_dmg > 0:
        update_leaderboard_dmg(guild_id, user_id, real_dmg)
    if src_credit and src_credit != target_id:
        update_leaderboard_dmg(guild_id, src_credit, bonus_dmg)

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
        "dmg_total_affiche": base_dmg + bonus_dmg,
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
            f"🧪 **Contamination toxique**\n"
            f"{get_mention(ctx.guild, user_id)} a empoisonné {get_mention(ctx.guild, target_id)}.\n"
            f"Le poison infligera **3 PV** toutes les 30 minutes pendant 3 heures.\n"
            f"⚠️ Les attaques de la cible infligeront **1 dégât de moins**."
        )
        await ctx.followup.send(embed=embed)

    # INFECTION
    elif action_type == "infection":
        appliquer_infection(guild_id, target_id, channel_id, user_id)

        embed = build_embed_from_item(
            "🧟",
            f"🧟 **Infection déclenchée**\n"
            f"{get_mention(ctx.guild, user_id)} a infecté {get_mention(ctx.guild, target_id)}.\n"
            f"L’infection infligera **2 PV** toutes les 30 minutes pendant 3 heures.\n"
            f"⚠️ Chaque attaque inflige **+2 dégâts** et peut propager l'infection."
        )
        await ctx.followup.send(embed=embed)

    # VIRUS
    elif action_type == "virus" and index == 0:
        appliquer_virus(guild_id, target_id, channel_id, user_id)

        embed = build_embed_from_item(
            "🦠",
            f"🦠 **Contamination virale**\n"
            f"{get_mention(ctx.guild, user_id)} a infecté {get_mention(ctx.guild, target_id)}.\n"
            f"Le virus infligera **5 PV** toutes les 30 minutes pendant 3 heures.\n"
            f"⚠️ L’attaquant perd immédiatement **2 PV** en transférant le virus en cas d'attaque."
        )
        await ctx.followup.send(embed=embed)

        # Supprimer le virus de l’attaquant après transmission
        virus_status[guild_id].pop(user_id, None)

### 🎯 FORMATTEUR DE MESSAGE

def afficher_degats(ctx, user_id, target_id, item, result, type_cible="attaque"):
    user_mention = get_mention(ctx.guild, user_id)
    target_mention = get_mention(ctx.guild, target_id)
    bonus_str = f" (+{' '.join(result['bonus_info'])})" if result['bonus_info'] else ""

    ligne1 = f"{user_mention} inflige {result['dmg_total_affiche']} dégâts à {target_mention} avec {item} !"

    if result["lost_pb"] and result["real_dmg"] == 0:
        # Dégâts entièrement absorbés par le bouclier
        ligne2 = f"{target_mention} perd {result['lost_pb']} PB"
        ligne3 = f"🛡️ {result['before_pb']} PB - {result['lost_pb']} PB = ❤️ {result['end_hp']} PV / 🛡️ {result['after_pb']} PB"

    elif result["lost_pb"] and result["real_dmg"] > 0:
        # Bouclier cassé : dégâts restants infligés aux PV (avec bonus éventuel)
        ligne2 = f"{target_mention} perd {result['real_dmg']} PV{bonus_str} et {result['lost_pb']} PB"
        ligne3 = (
            f"❤️ {result['start_hp']} PV - {result['real_dmg']} PV{bonus_str} / "
            f"🛡️ {result['before_pb']} PB - {result['lost_pb']} PB = "
            f"❤️ {result['end_hp']} PV / 🛡️ {result['after_pb']} PB"
        )

    else:
        # Dégâts uniquement sur les PV
        ligne2 = f"{target_mention} perd {result['real_dmg']} PV{bonus_str}"
        ligne3 = f"❤️ {result['start_hp']} PV - {result['real_dmg']} PV{bonus_str} = ❤️ {result['end_hp']} PV"

    return f"**{type_cible.capitalize()}** : {ligne1}\n{ligne2}\n{ligne3}{result['crit_txt']}{result['reset_txt']}"

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
            dmg, action["type"], action.get("crit", 0), item
        )

        # 📝 Message personnalisé
        ligne_type = "Attaque principale" if i == 0 else "Attaque secondaire"
        desc = afficher_degats(ctx, user_id, victim_id, item, result, type_cible=ligne_type.lower())

        embed = build_embed_from_item(
            item,
            f"**{ligne_type}** : {desc}",
            is_crit=("💥" in result["crit_txt"])
        )
        await ctx.followup.send(embed=embed)

        # 📤 Effets secondaires
        for effet_embed in result["effets_embeds"]:
            await ctx.send(embed=effet_embed)

        # 🛡 Bouclier détruit
        if result["shield_broken"]:
            shield_embed = build_embed_from_item("🛡", f"Le bouclier de {victim_mention} a été **détruit**.")
            shield_embed.set_image(url=None)  # désactive le GIF
            await ctx.followup.send(embed=shield_embed)

        # 🧪 Statuts à appliquer (uniquement sur première cible pour certains)
        await appliquer_statut_si_necessaire(ctx, guild_id, user_id, victim_id, action["type"], index=i)

    return None, True

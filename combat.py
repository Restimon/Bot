import time
import math
import random
import discord

from discord import app_commands
from data import esquive_bonus, cooldowns, casque_bonus, shields, virus_status, poison_status, infection_status, immunite_status, hp, leaderboard
from utils import OBJETS, check_crit, handle_death
from storage import get_user_data
from embeds import build_embed_from_item
from cooldowns import is_on_cooldown
from leaderboard_utils import update_leaderboard
from effects import remove_status_effects

async def apply_item_with_cooldown(user_id, target_id, item, ctx):
    guild_id = str(ctx.guild.id)
    user_id = str(user_id)
    target_id = str(target_id)
    now = time.time()

    user_inv, user_hp, user_stats = get_user_data(guild_id, user_id)
    _, target_hp, target_stats = get_user_data(guild_id, target_id)

    user_obj = ctx.guild.get_member(int(user_id))
    target_obj = ctx.guild.get_member(int(target_id))
    user_mention = user_obj.mention if user_obj else f"<@{user_id}>"
    target_mention = target_obj.mention if target_obj else f"<@{target_id}>"

    if item not in OBJETS:
        return build_embed_from_item("❓", f"⚠️ L'objet `{item}` est inconnu."), False

    action = OBJETS[item]
    
    # Vérifie le cooldown si l'action est une attaque (et non un soin)
    if action["type"] in ["attaque", "virus", "poison", "infection"]:
        on_cooldown, remaining = is_on_cooldown(guild_id, (user_id, target_id), "attack")
        if on_cooldown:
            return build_embed_from_item(
                item,
                f"🕒 {user_mention}, vous devez patienter encore **{remaining} secondes** avant d'attaquer.",
            ), False
    elif action["type"] == "soin":
        on_cooldown, remaining = is_on_cooldown(guild_id, (user_id, target_id), "heal")
        if on_cooldown:
            return build_embed_from_item(
                item,
                f"🕒 {user_mention}, vous devez patienter encore **{remaining} secondes** avant de soigner {target_mention}.",
                is_heal_other=(user_id != target_id)
            ), False


    # Vérification de cooldown uniquement pour les actions offensives

    # Cible morte
    if target_hp <= 0 and action["type"] != "soin":
        return build_embed_from_item(item, f"⚠️ {target_mention} est déjà hors service."), False

    # Gestion de l'esquive uniquement pour les objets offensifs
    if action["type"] in ["attaque", "virus", "poison", "infection"]:
        evade_chance = 0.1
        esquive_data = esquive_bonus.get(guild_id, {}).get(target_id)
        if esquive_data:
            elapsed = now - esquive_data["start"]
            if elapsed < esquive_data["duration"]:
                evade_chance += 0.2
            else:
                del esquive_bonus[guild_id][target_id]
    
        if random.random() < evade_chance:
            return build_embed_from_item(
                item,
                f"💨 {target_mention} esquive habilement l’attaque de {user_mention} avec {item} ! Aucun dégât infligé."
            ), True

    # Dégâts initiaux uniquement pour les objets qui en ont besoin
    base_dmg = action.get("degats", 0) if "degats" in action else 0
    evade_chance = 0.1
    esquive_data = esquive_bonus.get(guild_id, {}).get(target_id)
    if esquive_data:
        # Vérifie si le bonus est encore actif
        elapsed = now - esquive_data["start"]
        if elapsed < esquive_data["duration"]:
            evade_chance += 0.2  # +20%
        else:
            # Bonus expiré
            del esquive_bonus[guild_id][target_id]

    if random.random() < evade_chance:
        return build_embed_from_item(
            item,
            f"💨 {target_mention} esquive habilement l’attaque de {user_mention} avec {item} ! Aucun dégât infligé.",
            is_heal_other=False,
            is_crit=False
        ), True

    base_dmg = action.get("degats", 0)
    crit_txt = ""
    modif_txt = ""
    
    # 🧪 Poison : -1 dégât
    if user_id in poison_status.get(guild_id, {}):
        base_dmg -= 1
        emoji_modif = "🧪"
        modif_txt = f"(-1 {emoji_modif})"

    # 🦠 Virus : +2 dégâts et -2 PV
    if user_id in virus_status.get(guild_id, {}):
        base_dmg += 2
        emoji_modif = "🦠"
        modif_txt = f"(+2 {emoji_modif})"
        hp[guild_id][user_id] = max(hp[guild_id].get(user_id, 100) - 2, 0)
        virus_src = virus_status[guild_id][user_id].get("source")
        if virus_src:
            leaderboard.setdefault(guild_id, {})
            leaderboard[guild_id].setdefault(virus_src, {"degats": 0, "soin": 0, "kills": 0, "morts": 0})
            leaderboard[guild_id][virus_src]["degats"] += 2
        virus_status[guild_id][target_id] = virus_status[guild_id][user_id].copy()
        del virus_status[guild_id][user_id]
        await ctx.channel.send(
            f"💉 {ctx.user.mention} a **transmis le virus** à {target_mention}.\n"
            f"🦠 Le statut viral a été **supprimé** de {ctx.user.mention}."
        )

    # 🧟 Infection : +2 dégâts + propagation 25%
    infect_stat = infection_status.get(guild_id, {}).get(user_id)
    if infect_stat and target_id not in infection_status.get(guild_id, {}):
        infect_source = infect_stat.get("source", user_id)
        bonus_dmg = 2
        base_dmg += bonus_dmg
        emoji_modif = "🧟"
        modif_txt = f"(+{bonus_dmg} {emoji_modif})"
        leaderboard.setdefault(guild_id, {})
        leaderboard[guild_id].setdefault(infect_source, {"degats": 0, "soin": 0, "kills": 0, "morts": 0})
        leaderboard[guild_id][infect_source]["degats"] += bonus_dmg

        if random.random() < 0.25:
            infection_status[guild_id][target_id] = {
                "start": now,
                "duration": 3 * 3600,
                "last_tick": 0,
                "source": infect_source,
                "channel_id": ctx.channel.id
            }
            infect_bonus = 5
            before_i = hp[guild_id].get(target_id, 100)
            after_i = max(before_i - infect_bonus, 0)
            hp[guild_id][target_id] = after_i
            leaderboard[guild_id][infect_source]["degats"] += infect_bonus

            if after_i == 0:
                hp[guild_id][target_id] = 100
                leaderboard.setdefault(guild_id, {})
                leaderboard[guild_id].setdefault(target_id, {"degats": 0, "soin": 0, "kills": 0, "morts": 0})
                leaderboard[guild_id][target_id]["degats"] = max(0, leaderboard[guild_id][target_id]["degats"] - 25)
                leaderboard[guild_id][infect_source]["degats"] += 50
                leaderboard[guild_id][infect_source]["kills"] += 1
                leaderboard[guild_id][target_id]["morts"] += 1
            modif_txt += " +5🧟 (infection transmise)"
    # ☠️ Attaque en chaîne
    if item == "☠️":
        # Liste des cibles secondaires
        others = [m for m in ctx.guild.members if m.id != int(user_id) and not m.bot]
        random.shuffle(others)
        secondaries = [m for m in others if str(m.id) != target_id][:2]

        results = []

        async def process_attack(victim_id, base, is_main):
            dmg = base
            modif = ""
            now = time.time()

            # Poison : -1
            if user_id in poison_status.get(guild_id, {}):
                dmg -= 1
                modif += " 🧪(-1)"

            # Virus : +2
            if user_id in virus_status.get(guild_id, {}):
                dmg += 2
                modif += " 🦠(+2)"
                hp[guild_id][user_id] = max(hp[guild_id][user_id] - 2, 0)
                virus_src = virus_status[guild_id][user_id].get("source")
                if virus_src:
                    leaderboard[guild_id].setdefault(virus_src, {"degats": 0, "soin": 0, "kills": 0, "morts": 0})
                    leaderboard[guild_id][virus_src]["degats"] += 2
                if is_main:
                    virus_status[guild_id][victim_id] = virus_status[guild_id][user_id].copy()
                    del virus_status[guild_id][user_id]
                    await ctx.channel.send(
                        f"💉 {ctx.user.mention} a **transmis le virus** à <@{victim_id}>.\n"
                        f"🦠 Le statut viral a été **supprimé** de {ctx.user.mention}."
                    )

            # Infection
            infect_stat = infection_status.get(guild_id, {}).get(user_id)
            if infect_stat and victim_id not in infection_status.get(guild_id, {}):
                source_inf = infect_stat.get("source", user_id)
                dmg += 2
                modif += " 🧟(+2)"
                leaderboard[guild_id].setdefault(source_inf, {"degats": 0, "soin": 0, "kills": 0, "morts": 0})
                leaderboard[guild_id][source_inf]["degats"] += 2

                if random.random() < 0.25:
                    infection_status[guild_id][victim_id] = {
                        "start": now,
                        "duration": 3 * 3600,
                        "last_tick": 0,
                        "source": source_inf,
                        "channel_id": ctx.channel.id
                    }
                    dmg += 5
                    modif += " +5🧟 (infection transmise)"
                    leaderboard[guild_id][source_inf]["degats"] += 5
                    
            # Gestion de l'esquive uniquement pour les objets offensifs (pas de soin)
            if action["type"] in ["attaque", "virus", "poison", "infection"]:
                evade_chance = 0.1
                esquive_data = esquive_bonus.get(guild_id, {}).get(target_id)
                if esquive_data:
                    elapsed = now - esquive_data["start"]
                    if elapsed < esquive_data["duration"]:
                        evade_chance += 0.2
                    else:
                        del esquive_bonus[guild_id][target_id]

                if random.random() < evade_chance:
                    return build_embed_from_item(
                        item,
                        f"💨 {target_mention} esquive habilement l’attaque de {user_mention} avec {item} ! Aucun dégât infligé."
                    ), True

            # Esquive
            esquive_data = esquive_bonus.get(guild_id, {}).get(victim_id)
            evade_chance = 0.1
            if esquive_data and now - esquive_data["start"] < esquive_data["duration"]:
                evade_chance += 0.2
            elif esquive_data:
                del esquive_bonus[guild_id][victim_id]
            if random.random() < evade_chance:
                return f"💨 <@{victim_id}> esquive l’attaque de {item} !"

            # Immunité
            if victim_id in immunite_status.get(guild_id, {}):
                if time.time() - immunite_status[guild_id][victim_id]["start"] < immunite_status[guild_id][victim_id]["duration"]:
                    return f"⭐️ <@{victim_id}> est **invulnérable**. Aucun dégât pris."
                else:
                    del immunite_status[guild_id][victim_id]

            # Casque : réduction x0.5 arrondi sup
            casque_data = casque_bonus.get(guild_id, {}).get(victim_id)
            if casque_data and now - casque_data["start"] < casque_data["duration"]:
                dmg = int(dmg * 0.5) if dmg * 0.5 == int(dmg * 0.5) else int(dmg * 0.5) + 1
                modif += " 🪖(x0.5)"
            elif casque_data:
                del casque_bonus[guild_id][victim_id]

            # Bouclier
            shield = shields.get(guild_id, {}).get(victim_id, 0)
            if shield > 0:
                if dmg <= shield:
                    shields[guild_id][victim_id] -= dmg
                    return f"🛡 <@{victim_id}> est protégé ! Aucun PV perdu ({dmg} absorbés)."
                else:
                    dmg -= shield
                    shields[guild_id][victim_id] = 0

            before = hp[guild_id].get(victim_id, 100)
            after = max(before - dmg, 0)
            hp[guild_id][victim_id] = after
            leaderboard[guild_id].setdefault(user_id, {"degats": 0, "soin": 0, "kills": 0, "morts": 0})
            leaderboard[guild_id][user_id]["degats"] += dmg

            reset = ""
            if after == 0:
                handle_death(guild_id, victim_id, user_id)
                reset = " 💀 (remis à 100 PV)"

            return f"☠️ {item} inflige {dmg} dégâts à <@{victim_id}> ({before} → {after}){modif}{reset}"

        # Attaque principale
        result_main = await process_attack(target_id, 24, is_main=True)
        results.append(result_main)

        # Cibles secondaires
        for sc in secondaries:
            result = await process_attack(str(sc.id), 12, is_main=False)
            results.append(result)

        # Embed final
        embed = discord.Embed(
            title="☠️ Attaque en chaîne",
            description="\n".join(results),
            color=discord.Color.red()
        )
        return embed, True
    # Appliquer le coup critique
    if check_crit(action.get("crit", 0)):
        base_dmg *= 2
        crit_txt = " **(Coup critique ! 💥)**"
    # ⭐️ Immunité : aucun dégât
    from data import immunite_status

    immune = immunite_status.get(guild_id, {}).get(target_id)
    if immune:
        elapsed = now - immune["start"]
        if elapsed < immune["duration"]:
            return build_embed_from_item(
                item,
                f"⭐️ {target_mention} est **invulnérable** grâce à l’immunité ! Aucun dégât infligé.",
                is_heal_other=False
            ), True
        else:
            del immunite_status[guild_id][target_id]

    dmg = max(0, base_dmg)
    # 🪖 Réduction de 50% avec arrondi supérieur si la cible porte un casque
    casque_data = casque_bonus.get(guild_id, {}).get(target_id)
    if casque_data:
        elapsed = now - casque_data["start"]
        if elapsed < casque_data["duration"]:
            reduced = dmg * 0.5
            dmg = math.ceil(reduced)  # Arrondi supérieur
            modif_txt += " 🪖(x0.5)"
        else:
            del casque_bonus[guild_id][target_id]

    before = target_hp
    # 💥 Gestion du bouclier
    shield_amt = shields.get(guild_id, {}).get(target_id, 0)
    if shield_amt > 0:
        if dmg <= shield_amt:
            shields[guild_id][target_id] -= dmg
            return build_embed_from_item(
                item,
                f"🛡 {target_mention} est protégé par un bouclier ! Aucun PV perdu ({dmg} absorbés)."
            ), True
        else:
            dmg -= shield_amt
            shields[guild_id][target_id] = 0

    before = hp[guild_id].get(target_id, 100)
    new_hp = max(before - dmg, 0)
    real_dmg = before - new_hp
    real_dmg = before - new_hp
    hp[guild_id][target_id] = new_hp

    if new_hp == 0:
        handle_death(guild_id, target_id, user_id)  # ou infecteur_id
    else:
        user_stats["degats"] += real_dmg

    cooldowns["attack"].setdefault(guild_id, {})[user_id] = now

    reset_txt = ""
    if new_hp == 0:
        handle_death(guild_id, target_id, user_id)
        reset_txt = f"\n💀 {target_mention} a été vaincu et revient à **100 PV**. (-25 pts | +50 pts)"

        # 🧟 Propagation de l'infection
        if user_id in infection_status.get(guild_id, {}):
            if random.random() < 0.25:
                infection_status.setdefault(guild_id, {})
                infection_status[guild_id][target_id] = {
                    "start": now,
                    "duration": 3 * 3600,
                    "last_tick": 0,
                    "source": infection_status[guild_id][user_id]["source"]
                }

        user_stats["degats"] += dmg
        cooldowns["attack"].setdefault(guild_id, {})[user_id] = now

        status_type = action.get("status")
        if status_type == "virus":
            virus_status.setdefault(guild_id, {})[target_id] = {
                "start": now,
                "duration": action.get("duree", 6 * 3600),
                "last_tick": 0
            }
        elif status_type == "poison":
            poison_status.setdefault(guild_id, {})[target_id] = {
                "start": now,
                "duration": action.get("duree", 3 * 3600),
                "last_tick": 0
            }

        return build_embed_from_item(
            item,
                f"{user_mention} inflige {dmg} dégâts à {target_mention} avec {item} !\n"
                f"**SomniCorp :** {target_mention} : {before} - {dmg}{modif_txt} = {new_hp} / 100 PV{crit_txt}"
            ), True

        heal = action["soin"]
        crit_txt = ""
        if check_crit(action.get("crit", 0)):
            heal *= 2
            crit_txt = " **(Soin critique ! ✨)**"

        before = target_hp
        new_hp = min(target_hp + heal, 100)
        hp[guild_id][target_id] = new_hp
        # 🛡 Bouclier : ajoute 20 points de protection
        if item == "🛡":
            shields.setdefault(guild_id, {})
            shields[guild_id][target_id] = shields[guild_id].get(target_id, 0) + 20
            return build_embed_from_item(item, f"🛡 {target_mention} est maintenant protégé par un **bouclier de 20 points** !"), True
        user_stats["soin"] += heal
        cooldowns["heal"].setdefault(guild_id, {})[(user_id, target_id)] = now

        return build_embed_from_item(item, f"{user_mention} soigne {target_mention} avec {item}, restaurant {heal} PV ({before} → {new_hp}){crit_txt}"), True

    elif action["type"] == "virus":
        virus_status.setdefault(guild_id, {})
        duration = action.get("duree", 6 * 3600)
        dmg = action.get("degats", 5)
        crit_txt = ""
        if check_crit(action.get("crit", 0)):
            dmg *= 2
            crit_txt = " **(Coup critique viral ! 🧬)**"
        before = hp[guild_id].get(target_id, 100)
        new_hp = max(before - dmg, 0)
        hp[guild_id][target_id] = new_hp
    
        reset_txt = ""
        if new_hp == 0:
            handle_death(guild_id, target_id, user_id)
            reset_txt = f"\n💀 {target_mention} a été vaincu et revient à **100 PV**. (-25 pts | +50 pts)"

        virus_status[guild_id][target_id] = {
            "start": now,
            "duration": duration,
            "last_tick": 0,
            "source": user_id,
            "channel_id": ctx.channel.id
        }

        effect_txt = (
            "\n🦠 Vous êtes **infecté par un virus** durant 6h | 5 dégâts toutes les heures."
            "\n⚔️ Lors d’une attaque : **vous perdez 2 PV** et **vous transmettez** le virus."
        )

        return build_embed_from_item(
            item,
            f"{user_mention} inflige {dmg} dégâts à {target_mention} avec {item} !\n"
            f"**SomniCorp :** {target_mention} : {before} - {dmg} = {new_hp} / 100 PV"
            f"{crit_txt}{reset_txt}{effect_txt}"
        ), True

    elif action["type"] == "poison":
        poison_status.setdefault(guild_id, {})
        duration = action.get("duree", 3 * 3600)
        dmg = action.get("degats", 3)
        crit_txt = ""
        if check_crit(action.get("crit", 0)):
            dmg *= 2
            crit_txt = " **(Poison critique ! ☠️)**"
        before = hp[guild_id].get(target_id, 100)
        new_hp = max(before - dmg, 0)
        hp[guild_id][target_id] = new_hp

        reset_txt = ""
        if new_hp == 0:
            handle_death(guild_id, target_id, user_id)
            reset_txt = f"\n💀 {target_mention} a été vaincu et revient à **100 PV**. (-25 pts | +50 pts)"

        poison_status[guild_id][target_id] = {
            "start": now,
            "duration": duration,
            "last_tick": 0,
            "source": user_id,
            "channel_id": ctx.channel.id
        }

        effect_txt = "\n🧪 Vous êtes **empoisonné** durant 3h | 3 dégâts toutes les 30 minutes."

        return build_embed_from_item(
            item,
            f"{user_mention} inflige {dmg} dégâts à {target_mention} avec {item} !\n"
            f"**SomniCorp :** {target_mention} : {before} - {dmg} = {new_hp} / 100 PV{crit_txt}"
            f"{reset_txt}{effect_txt}"
        ), True

    elif action["type"] == "vol":
        target_inv, _, _ = get_user_data(guild_id, target_id)
        volables = [i for i in target_inv if i != "🔍"]
        if not volables:
            return build_embed_from_item(item, f"🔍 {target_mention} n’a rien à voler !"), False
        stolen = random.choice(volables)
        target_inv.remove(stolen)
        user_inv.append(stolen)
        return build_embed_from_item(item, f"🔍 {user_mention} a volé **{stolen}** à {target_mention} !"), True

    elif action["type"] == "vaccin":
        return build_embed_from_item(
            item,
            f"⚠️ Le vaccin 💉 ne peut être utilisé que via la commande `/heal`."
        ), False   
        
    elif action["type"] == "infection":
        infection_status.setdefault(guild_id, {})
        dmg = action.get("degats", 5)
        duration = action.get("duree", 3 * 3600)

        before = hp[guild_id].get(target_id, 100)
        new_hp = max(before - dmg, 0)
        hp[guild_id][target_id] = new_hp

        infecteur_id = user_id  # L'infecteur initial

        leaderboard.setdefault(guild_id, {})
        leaderboard[guild_id].setdefault(infecteur_id, {"degats": 0, "soin": 0, "kills": 0, "morts": 0})
        leaderboard[guild_id][infecteur_id]["degats"] += dmg

        reset_txt = ""
        if new_hp == 0:
            handle_death(guild_id, target_id, infecteur_id)
            reset_txt = f"\n💀 {target_mention} a été vaincu et revient à **100 PV**. (-25 pts | +50 pts)"

        infection_status[guild_id][target_id] = {
            "start": now,
            "duration": duration,
            "last_tick": 0,
            "source": infecteur_id,
            "channel_id": ctx.channel.id
        }

        effect_txt = (
            "\n🧟 Vous êtes **infecté** durant 3h | 2 dégâts toutes les 30 minutes."
            "\n⚠️ En attaquant, vous avez **25% de chance** d’infecter votre cible."
        )

        return build_embed_from_item(
            item,
            f"{user_mention} inflige {dmg} dégâts à {target_mention} avec {item} !\n"
            f"**SomniCorp :** {target_mention} : {before} - {dmg} = {new_hp} / 100 PV"
            f"{reset_txt}{effect_txt}"
        ), True
        
    elif action["type"] == "attaque":
        crit_txt = ""
        if check_crit(action.get("crit", 0)):
            base_dmg *= 2
            crit_txt = " **(Coup critique ! 💥)**"

        before = hp[guild_id].get(target_id, 100)
        new_hp = max(before - base_dmg, 0)
        real_dmg = before - new_hp
        hp[guild_id][target_id] = new_hp
        user_stats["degats"] += real_dmg

        cooldowns["attack"].setdefault(guild_id, {})[user_id] = now

        reset_txt = ""
        if new_hp == 0:
            handle_death(guild_id, target_id, user_id)
            reset_txt = f"\n💀 {target_mention} a été vaincu et revient à **100 PV**. (-25 pts | +50 pts)"

        return build_embed_from_item(
            item,
            f"{user_mention} inflige {base_dmg} dégâts à {target_mention} avec {item} !\n"
            f"**SomniCorp :** {target_mention} : {before} - {base_dmg} = {new_hp} / 100 PV{crit_txt}{reset_txt}"
        ), True

    # ✅ Si aucun des `if` ou `elif` ci-dessus n'est pris en compte, retourne un embed d'erreur
    print(f"[apply_item_with_cooldown] Aucun traitement défini pour l’objet {item} de type {action.get('type')}")
    return build_embed_from_item(item, f"⚠️ Aucun effet appliqué pour l'objet `{item}` (type: {action.get('type')})."), False

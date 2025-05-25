import time
import math
import random
import discord

from discord import app_commands
from data import esquive_bonus, cooldowns, casque_bonus, shields, virus_status, poison_status, infection_status, immunite_status, hp, leaderboard
from utils import OBJETS, check_crit, handle_death
from storage import get_user_data
from embeds import build_embed_from_item
from cooldowns import is_on_cooldown, set_cooldown
from leaderboard_utils import update_leaderboard
from effects import remove_status_effects

async def apply_item_with_cooldown(user_id, target_id, item, ctx):
    guild_id = str(ctx.guild.id)
    user_id = str(user_id)
    target_id = str(target_id)
    now = time.time()

    # 📦 Données utilisateurs
    user_inv, user_hp, user_stats = get_user_data(guild_id, user_id)
    _, target_hp, target_stats = get_user_data(guild_id, target_id)

    # 👤 Mentions utilisateurs
    user_mention = get_mention(ctx, user_id)
    target_mention = get_mention(ctx, target_id)

    # ❓ L’objet est-il connu ?
    if item not in OBJETS:
        return build_embed_from_item("❓", f"⚠️ L'objet {item} est inconnu."), False

    action = OBJETS[item]
    
    if action["type"] in ["attaque", "virus", "poison", "infection", "attaque_chaine", "vol"]:
        on_cd, remain = is_on_cooldown(guild_id, (user_id, target_id), "attack")
        if on_cd:
            embed = discord.Embed(
                description=f"🕒 {user_mention}, vous devez attendre **{remain} sec** avant d'attaquer.",
                color=discord.Color.orange()
            )
            return embed, False

    if action["type"] == "soin":
        soin = action.get("soin", 0)
        soin, crit_txt = apply_crit(soin, action.get("crit", 0))

        before = hp.setdefault(guild_id, {}).get(target_id, 100)
        after = min(before + soin, 100)
        real_soin = after - before
        hp[guild_id][target_id] = after

        user_stats["soin"] += real_soin
        set_cooldown(guild_id, (user_id, target_id), "heal", action.get("cooldown", 30))

        # 📝 Message personnalisé selon la cible
        if user_id == target_id:
            description = (
                f"{user_mention} se soigne avec {item}.\n"
                f"{item} Il récupère **{real_soin} PV** | {before} + {real_soin} = {after}{crit_txt}"
            )
        else:
            description = (
                f"{user_mention} soigne {target_mention} avec {item}.\n"
                f"{item} {target_mention} récupère **{real_soin} PV** | {before} + {real_soin} = {after}{crit_txt}"
            )

        if real_soin == 0:
            description += "\n🛑 Aucun PV n’a été soigné."

        return build_embed_from_item(
            item,
            description,
            is_heal_other=(user_id != target_id)
        ), True

    # Si la cible est à 0 PV, on la remet à 100 automatiquement (fail-safe)
    if target_hp <= 0:
        hp[guild_id][target_id] = 100
        target_hp = 100

    # ⭐️ Immunité ?
    if is_immune(guild_id, target_id):
        return build_embed_from_item(
            item,
            f"⭐️ {target_mention} est **invulnérable**. Aucun effet."
        ), True

    # 💨 Esquive ?
    if random.random() < get_evade_chance(guild_id, target_id):
        return build_embed_from_item(
            "💨",  # emoji ou ID d’effet visuel d’esquive
            f"💨 {target_mention} esquive habilement l’attaque de {user_mention} avec {item} ! Aucun dégât."
        ), True

    # 🎯 Attaque
    if action["type"] == "attaque":
        base_dmg = action.get("degats", 0)
        bonus_dmg = 0
        bonus_info = ""
    
        # 🦠 Virus : auto-dégâts et transmission (pas de bonus dégâts à la cible)
        virus_stat = virus_status.get(guild_id, {}).get(user_id)
        if virus_stat:
            virus_source = virus_stat.get("source", user_id)

            before_self = hp[guild_id].get(user_id, 100)
            after_self = max(before_self - 2, 0)
            hp[guild_id][user_id] = after_self
            lost_hp = before_self - after_self

            if virus_source != user_id:
                leaderboard.setdefault(guild_id, {}).setdefault(virus_source, {"degats": 0, "soin": 0, "kills": 0, "morts": 0})
                leaderboard[guild_id][virus_source]["degats"] += lost_hp

            virus_status[guild_id][target_id] = virus_stat.copy()
            del virus_status[guild_id][user_id]

            embed_virus = discord.Embed(
                title="💉 Transmission virale",
                description=(
                    f"**GotValis** confirme une transmission virale : {target_mention} est désormais infecté.\n"
                    f"🦠 Le virus a été retiré de {user_mention}, qui perd **{lost_hp} PV** ({before_self} → {after_self})."
                ),
                color=0x2288FF
            )
            await ctx.channel.send(embed=embed_virus)

        # 🧠 Infection
        infect_stat = infection_status.get(guild_id, {}).get(user_id)
        if infect_stat and target_id not in infection_status.get(guild_id, {}):
            infect_source = infect_stat.get("source", user_id)
            bonus_dmg += 2
            bonus_info += "+2 🧟 "
            leaderboard.setdefault(guild_id, {}).setdefault(infect_source, {"degats": 0, "soin": 0, "kills": 0, "morts": 0})
            leaderboard[guild_id][infect_source]["degats"] += 2

            if random.random() < 0.25:
                infection_status[guild_id][target_id] = {
                    "start": now,
                    "duration": 3 * 3600,
                    "last_tick": 0,
                    "source": infect_source,
                    "channel_id": ctx.channel.id
                }

                inf_before = hp[guild_id].get(target_id, 100)
                inf_after = max(inf_before - 5, 0)
                hp[guild_id][target_id] = inf_after
                if target_id != infect_source:
                    leaderboard[guild_id][infect_source]["degats"] += 5
                if inf_after == 0:
                    handle_death(guild_id, target_id, infect_source)

                embed_info = discord.Embed(
                    title="🧬 Infection propagée",
                    description=(
                        f"**GotValis** détecte un nouveau infecté : {target_mention}.\n"
                        f"Il subit immédiatement **5 dégâts 🧟**."
                    ),
                    color=0x880088
                )
                await ctx.channel.send(embed=embed_info)

        # 🧪 Poison
        if poison_status.get(guild_id, {}).get(user_id):
            bonus_dmg -= 1
            bonus_info += "-1 🧪 "

        # Calcul des dégâts
        base_dmg, crit_txt = apply_crit(base_dmg, action.get("crit", 0))
        total_dmg = base_dmg + bonus_dmg
        total_dmg = apply_casque_reduction(guild_id, target_id, total_dmg)
        total_dmg = apply_shield(guild_id, target_id, total_dmg)

        before = hp[guild_id].get(target_id, 100)
        after = max(before - total_dmg, 0)
        hp[guild_id][target_id] = after

        real_dmg = before - after
        user_stats["degats"] += real_dmg

        if after == 0:
            handle_death(guild_id, target_id, user_id)
            reset_txt = f"\n💀 {target_mention} est tombé à 0 PV et revient à 100 PV."
        else:
            reset_txt = ""

        bonus_info_str = f" ({bonus_info.strip()})" if bonus_info else ""

        # ✅ Enregistrement du cooldown (important)
        set_cooldown(guild_id, (user_id, target_id), "attack", OBJETS[item].get("cooldown", 30))

        # 💥 Critique ?
        is_crit = "Coup critique" in crit_txt
        gif_url = "https://media.tenor.com/OUts7rGkfLMAAAAd/slash-critique.gif" if is_crit else OBJETS[item].get("gif")

        # 🔷 Embed personnalisé avec GIF adapté
        description = (
            f"{user_mention} inflige {real_dmg} dégâts à {target_mention} avec {item} !\n"
            f"{target_mention} perd {base_dmg} PV{bonus_info_str} | {before} - {real_dmg} = {after}{crit_txt}{reset_txt}"
        )

        return build_embed_from_item(item, description, is_crit=is_crit), True


    elif action["type"] == "poison":
        base_dmg = action.get("degats", 3)
        base_dmg, crit_txt = apply_crit(base_dmg, action.get("crit", 0))
        base_dmg = apply_casque_reduction(guild_id, target_id, base_dmg)
        dmg_final = apply_shield(guild_id, target_id, base_dmg)

        before = hp[guild_id].get(target_id, 100)
        after = max(before - dmg_final, 0)
        hp[guild_id][target_id] = after

        real_dmg = before - after
        user_stats["degats"] += real_dmg

        # Applique le statut de poison
        poison_status.setdefault(guild_id, {})[target_id] = {
            "start": now,
            "duration": action.get("duree", 3 * 3600) ,  # 3 heures par défaut
            "last_tick": 0,
            "source": user_id,
            "channel_id": ctx.channel.id
        }

        if after == 0:
            handle_death(guild_id, target_id, user_id)
            reset_txt = f"\n💀 {target_mention} est tombé à 0 PV et revient à 100 PV."
        else:
            reset_txt = ""

        effect_txt = "\n🧪 Un poison s'est propagé dans ton corps. 3 dégâts toutes les 30 minutes pendant 3h."

        return build_embed_from_item(
            item,
            f"{user_mention} inflige {real_dmg} dégâts à {target_mention} avec {item} !\n"
            f"**{before} → {after} PV**{crit_txt}{reset_txt}{effect_txt}"
        ), True
        
    elif action["type"] == "virus":
        base_dmg = action.get("degats", 5)
        base_dmg, crit_txt = apply_crit(base_dmg, action.get("crit", 0))
        base_dmg = apply_casque_reduction(guild_id, target_id, base_dmg)
        dmg_final = apply_shield(guild_id, target_id, base_dmg)

        before = hp[guild_id].get(target_id, 100)
        after = max(before - dmg_final, 0)
        hp[guild_id][target_id] = after

        real_dmg = before - after
        user_stats["degats"] += real_dmg

        # Applique le statut viral
        virus_status.setdefault(guild_id, {})[target_id] = {
            "start": now,
            "duration": action.get("duree", 6 * 3600) + 60,
            "last_tick": 0,
            "source": user_id,
            "channel_id": ctx.channel.id
        }

        # 💉 Auto-dégâts pour le porteur
        hp[guild_id][user_id] = max(hp[guild_id].get(user_id, 100) - 2, 0)

        # 🧠 Attribution des -2 PV au source initial (si défini)
        source_id = virus_status[guild_id].get(user_id, {}).get("source")
        if source_id:
            leaderboard.setdefault(guild_id, {})
            leaderboard[guild_id].setdefault(source_id, {"degats": 0, "soin": 0, "kills": 0, "morts": 0})
            leaderboard[guild_id][source_id]["degats"] += 2

        # ✅ Transfert automatique UNIQUEMENT si action = attaque
        if action["type"] == "attaque":
            virus_status[guild_id][target_id] = virus_status[guild_id][user_id].copy()
            del virus_status[guild_id][user_id]

            embed_virus = discord.Embed(
                title="💉 Transmission virale",
                description=(
                    f"**GotValis** confirme une transmission virale : {target_mention} est désormais infecté.\n"
                    f"🦠 Le virus a été retiré de {user_mention}."
                ),
                color=0x2288FF
            )
            await ctx.channel.send(embed=embed_virus)

        # 💀 KO
        if after == 0:
            handle_death(guild_id, target_id, user_id)
            reset_txt = f"\n💀 {target_mention} est tombé à 0 PV et revient à 100 PV."
        else:
            reset_txt = ""

        effect_txt = (
            "\n🦠 Le virus est en incubation. 5 dégâts toutes les heures pendant 6h."
            "\n⚔️ Lors d’une attaque : -2 PV et possible transmission."
        )

        return build_embed_from_item(
            item,
            f"{user_mention} inflige {real_dmg} dégâts à {target_mention} avec {item} !\n"
            f"**{before} → {after} PV**{crit_txt}{reset_txt}{effect_txt}"
        ), True
        
    elif action["type"].strip() == "infection":
        base_dmg = action.get("degats", 5)
        base_dmg, crit_txt = apply_crit(base_dmg, action.get("crit", 0))
        base_dmg = apply_casque_reduction(guild_id, target_id, base_dmg)
        dmg_final = apply_shield(guild_id, target_id, base_dmg)

        before = hp[guild_id].get(target_id, 100)
        after = max(before - dmg_final, 0)
        hp[guild_id][target_id] = after

        real_dmg = before - after

        # Applique le statut d'infection
        infection_status.setdefault(guild_id, {})[target_id] = {
            "start": now,
            "duration": action.get("duree", 3 * 3600) + 60,
            "last_tick": 0,
            "source": user_id,
            "channel_id": ctx.channel.id
        }

        # Attribution des points, sauf si self-infecté
        if target_id != user_id:
            leaderboard.setdefault(guild_id, {})
            leaderboard[guild_id].setdefault(user_id, {"degats": 0, "soin": 0, "kills": 0, "morts": 0})
            leaderboard[guild_id][user_id]["degats"] += real_dmg

        if after == 0:
            handle_death(guild_id, target_id, user_id)
            reset_txt = f"\n💀 {target_mention} est tombé à 0 PV et revient à 100 PV."
        else:
            reset_txt = ""

        effect_txt = (
            "\n🧟 L'infection se propage. 2 dégâts toutes les 30 minutes pendant 3h."
            "\n⚠️ En attaquant, 25% de chance de transmettre l’infection."
        )

        # Embed principal de l’attaque
        embed_attack = build_embed_from_item(
            item,
            f"{user_mention} inflige {real_dmg} dégâts à {target_mention} avec {item} !\n"
            f"**{before} → {after} PV**{crit_txt}{reset_txt}{effect_txt}"
        )

        # Embed secondaire pour le message d'infection
        embed_info = discord.Embed(
            title="🧬 Infection",
            description=(
                f"**GotValis** détecte un nouveau infecté : {target_mention}.\n"
                f"Il subit immédiatement **5 dégâts 🧟**."
            ),
            color=0x880088
        )
        await ctx.channel.send(embed=embed_info)

        return embed_attack, True

    elif action["type"] == "vol":
        attacker_inv, _, _ = get_user_data(guild_id, user_id)
        target_inv, _, _ = get_user_data(guild_id, target_id)

        if not target_inv:
            embed = discord.Embed(
                description=f"🔍 {target_mention} n’a **aucun objet** à se faire voler !",
                color=discord.Color.red()
            )
            return embed, False

        # Vol aléatoire
        stolen = random.choice(target_inv)
        target_inv.remove(stolen)
        attacker_inv.append(stolen)

        embed = discord.Embed(
            description=f"🔍 {user_mention} a volé **{stolen}** à {target_mention} !",
            color=discord.Color.gold()
        )
        return embed, True


        # Inventaire cible
        target_inv, _, _ = get_user_data(guild_id, target_id)
        volables = [obj for obj, qty in target_inv.items() if qty > 0]

        if not volables:
            return build_embed_from_item(
                item,
                f"🧳 {target_mention} n’a **aucun objet** à se faire voler !"
            ), True

        # Choix de l'objet à voler
        obj = random.choice(volables)
        target_inv[obj] -= 1
        user_inv[obj] = user_inv.get(obj, 0) + 1

        return build_embed_from_item(
            item,
            f"🔍 {user_mention} a **volé** {obj} à {target_mention} !"
        ), True
        
    elif action["type"] == "attaque_chaine":
        main_dmg = 24
        splash_dmg = 12
        all_targets = [target_id]
        extra_targets = [m.id for m in ctx.guild.members if str(m.id) != user_id and str(m.id) != target_id and not m.bot]

        random.shuffle(extra_targets)
        all_targets += extra_targets[:2]

        embed_lines = [f"{user_mention} a attaqué {target_mention} avec {item}"]

        for i, tid in enumerate(all_targets):
            is_main = i == 0
            base_dmg = main_dmg if is_main else splash_dmg
            bonus_dmg = 0
            bonus_info = []
            mention = get_mention(ctx, tid)
            start_hp = hp[guild_id].get(tid, 100)

            if is_immune(guild_id, tid):
                embed_lines.append(f"⭐ {mention} est **invulnérable**.")
                continue

            if random.random() < get_evade_chance(guild_id, tid):
                embed_lines.append(f"💨 {mention} esquive l’attaque !")
                continue

            infect_stat = infection_status.get(guild_id, {}).get(user_id)
            already_infected = tid in infection_status.get(guild_id, {})
            if infect_stat and not already_infected:
                infect_source = infect_stat.get("source", user_id)
                bonus_dmg += 2
                bonus_info.append("+2 🧟")
                leaderboard.setdefault(guild_id, {}).setdefault(infect_source, {"degats": 0, "soin": 0, "kills": 0, "morts": 0})
                leaderboard[guild_id][infect_source]["degats"] += 2

                if random.random() < 0.25:
                    infection_status[guild_id][target_id] = {
                        "start": now,
                        "duration": 3 * 3600,
                        "last_tick": 0,
                        "source": infect_source,
                        "channel_id": ctx.channel.id
                    }

                    inf_before = hp[guild_id].get(target_id, 100)
                    inf_after = max(inf_before - 5, 0)
                    hp[guild_id][target_id] = inf_after
                    if target_id != infect_source:
                        leaderboard[guild_id][infect_source]["degats"] += 5
                    if inf_after == 0:
                        handle_death(guild_id, target_id, infect_source)

                    embed_info = discord.Embed(
                        title="🧬 Infection propagée",
                        description=(
                            f"**GotValis** détecte un nouveau infecté : {target_mention}.\n"
                            f"Il subit immédiatement **5 dégâts 🧟**."
                        ),
                        color=0x880088
                    )
                    await ctx.channel.send(embed=embed_info)

            # 🦠 Virus : auto-dégâts et transmission (pas de bonus dégâts à la cible)
            virus_stat = virus_status.get(guild_id, {}).get(user_id)
            if virus_stat:
                virus_source = virus_stat.get("source", user_id)

                # 💉 Auto-dégâts
                before_self = hp[guild_id].get(user_id, 100)
                after_self = max(before_self - 2, 0)
                hp[guild_id][user_id] = after_self
                lost_hp = before_self - after_self

                # Attribution des points à la source du virus
                if virus_source != user_id:
                    leaderboard.setdefault(guild_id, {}).setdefault(virus_source, {"degats": 0, "soin": 0, "kills": 0, "morts": 0})
                    leaderboard[guild_id][virus_source]["degats"] += lost_hp

                # ✅ Transmission
                virus_status[guild_id][target_id] = virus_stat.copy()
                del virus_status[guild_id][user_id]

                embed_virus = discord.Embed(
                    title="💉 Transmission virale",
                    description=(
                        f"**GotValis** confirme une transmission virale : {target_mention} est désormais infecté.\n"
                        f"🦠 Le virus a été retiré de {user_mention}, qui perd **{lost_hp} PV** ({before_self} → {after_self})."
                    ),
                    color=0x2288FF
                )
                await ctx.channel.send(embed=embed_virus)

            base_dmg, crit_txt = apply_crit(base_dmg, action.get("crit", 0))
            dmg = base_dmg + bonus_dmg
            dmg = apply_casque_reduction(guild_id, tid, dmg)
            dmg = apply_shield(guild_id, tid, dmg)

            end_hp = max(start_hp - dmg, 0)
            hp[guild_id][tid] = end_hp
            real_dmg = start_hp - end_hp
            user_stats["degats"] += real_dmg

            if end_hp == 0:
                handle_death(guild_id, tid, user_id)
                reset_txt = " 💀 (KO)"
            else:
                reset_txt = ""

            bonus_str = f" (+{' '.join(bonus_info)})" if bonus_info else ""
            header = f"{mention} perd {real_dmg} PV{crit_txt} | {base_dmg} de base{bonus_str} ➝ {start_hp} → {end_hp}{reset_txt}"
            if is_main:
                embed_lines.insert(1, f"**GotValis** : {header}")
                embed_lines.append("L’attaque rebondit !")
            else:
                embed_lines.append(f"{header} (attaque secondaire)")

        # On sort de la boucle for et on retourne l'embed
        return build_embed_from_item(item, "\n".join(embed_lines)), True

    # Aucun type reconnu : fail-safe
    return build_embed_from_item("❓", f"⚠️ Type d'effet inconnu pour l’objet {item}."), False

def is_immune(guild_id, target_id):
    """Vérifie si la cible a une immunité active."""
    immune = immunite_status.get(guild_id, {}).get(target_id)
    if immune:
        if time.time() - immune["start"] < immune["duration"]:
            return True
        else:
            del immunite_status[guild_id][target_id]
    return False

def get_evade_chance(guild_id, target_id):
    """Retourne la probabilité d'esquive d'un utilisateur."""
    base = 0.05
    esquive = esquive_bonus.get(guild_id, {}).get(target_id)
    if esquive:
        if time.time() - esquive["start"] < esquive["duration"]:
            base += 0.2
        else:
            del esquive_bonus[guild_id][target_id]
    return base

def apply_casque_reduction(guild_id, target_id, dmg):
    """Applique le casque si actif, sinon retourne les dégâts normaux."""
    casque = casque_bonus.get(guild_id, {}).get(target_id)
    if casque:
        if time.time() - casque["start"] < casque["duration"]:
            reduced = dmg * 0.5
            return math.ceil(reduced)
        else:
            del casque_bonus[guild_id][target_id]
    return dmg

def apply_shield(guild_id, target_id, dmg):
    """Applique le bouclier et retourne le reste des dégâts (0 si tout absorbé)."""
    shield = shields.get(guild_id, {}).get(target_id, 0)
    if shield > 0:
        if dmg <= shield:
            shields[guild_id][target_id] -= dmg
            return 0
        else:
            shields[guild_id][target_id] = 0
            return dmg - shield
    return dmg

def apply_crit(dmg, crit_chance):
    """Applique un coup critique si applicable."""
    if check_crit(crit_chance):
        return dmg * 2, " **(Coup critique ! 💥)**"
    return dmg, ""

def get_mention(ctx, user_id):
    member = ctx.guild.get_member(int(user_id))
    return member.mention if member else f"<@{user_id}>"

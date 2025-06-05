import random
import time
import discord

from data import hp, leaderboard, inventaire
from data import virus_status, poison_status, infection_status, immunite_status, regeneration_status, shields, casque_status
from utils import get_mention, get_evade_chance
from embeds import build_embed_from_item
from storage import sauvegarder
from main import handle_death


### 🔧 UTILS GÉNÉRAUX

def is_immune(guild_id, user_id):
    return user_id in immunite_status.get(guild_id, {})

def apply_crit(base_dmg, crit_chance):
    if random.random() < crit_chance:
        return base_dmg * 2, " 💥 **Coup critique !**"
    return base_dmg, ""

def apply_casque_reduction(guild_id, user_id, dmg):
    if user_id in casque_status.get(guild_id, {}):
        return int(dmg * 0.5)  # réduit les dégâts de moitié
    return dmg


def apply_shield(guild_id, user_id, dmg):
    gid = str(guild_id)
    uid = str(user_id)

    current_shield = shields.get(gid, {}).get(uid, 0)
    if current_shield <= 0:
        return dmg, 0, False  # Aucun bouclier

    lost_pb = min(dmg, current_shield)
    remaining_dmg = dmg - lost_pb
    shields.setdefault(gid, {})[uid] = max(0, current_shield - lost_pb)
    shield_broken = current_shield - lost_pb <= 0

    return remaining_dmg, lost_pb, shield_broken

def update_leaderboard_dmg(guild_id, source_id, dmg):
    leaderboard.setdefault(guild_id, {}).setdefault(source_id, {"degats": 0, "soin": 0, "kills": 0, "morts": 0})
    leaderboard[guild_id][source_id]["degats"] += dmg


### 🧪🦠🧟 STATUTS SECONDAIRES

async def appliquer_poison(guild_id, target_id, channel_id, source_id):
    now = time.time()
    gid = str(guild_id)
    tid = str(target_id)

    if tid in poison_status.get(gid, {}):
        return  # Déjà empoisonné

    poison_status.setdefault(gid, {})[tid] = {
        "start": now,
        "duration": 3 * 3600,
        "last_tick": 0,
        "source": str(source_id),
        "channel_id": channel_id,
    }

    channel = discord.utils.get(discord.utils.get(discord.Client().guilds, id=int(gid)).text_channels, id=channel_id)
    if channel:
        await channel.send(embed=discord.Embed(
            title="🧪 Contamination toxique",
            description=f"**GotValis** signale une contamination chimique.\n<@{tid}> a été **empoisonné** !",
            color=0x55FF55
        ))

async def appliquer_virus(guild_id, attacker_id, target_id, channel_id):
    now = time.time()
    gid = str(guild_id)
    tid = str(target_id)

    # Déjà infecté ? Ne rien faire
    if tid in virus_status.get(gid, {}):
        return

    # Appliquer le statut
    virus_status.setdefault(gid, {})[tid] = {
        "start": now,
        "duration": 3 * 3600,
        "last_tick": 0,
        "source": str(attacker_id),
        "channel_id": channel_id,
    }

    # Message embed de contamination
    embed = discord.Embed(
        title="💉 Transmission virale",
        description=f"**GotValis** détecte un agent viral.\n<@{tid}> a été **infecté** par un virus !",
        color=0x00FFAA
    )

    channel = discord.utils.get(discord.utils.get(discord.Client().guilds, id=int(gid)).text_channels, id=channel_id)
    if channel:
        await channel.send(embed=embed)

async def appliquer_infection(guild_id, attacker_id, target_id, channel_id):
    now = time.time()
    gid = str(guild_id)
    tid = str(target_id)
    aid = str(attacker_id)

    # Vérifie si la cible est déjà infectée
    deja_infecte = tid in infection_status.get(gid, {})

    # Infection non transmise si déjà infecté → pas d’effet
    if deja_infecte:
        return

    # Appliquer le statut d'infection
    infection_status.setdefault(gid, {})[tid] = {
        "start": now,
        "duration": 3 * 3600,
        "last_tick": 0,
        "source": aid,
        "channel_id": channel_id,
    }

    # Dégâts immédiats : 5 PV
    start_hp = hp[gid].get(tid, 100)
    dmg = 5
    end_hp = max(start_hp - dmg, 0)
    hp[gid][tid] = end_hp

    # Attribution des points à la source sauf auto-infection
    if tid != aid:
        update_leaderboard_dmg(gid, aid, dmg)

    # Embed d’infection
    embed = discord.Embed(
        title="🧟 Infection détectée",
        description=f"**GotValis** a identifié un nouveau sujet infecté.\n<@{tid}> subit **5 dégâts** et devient **infecté**.",
        color=0xAA00FF
    )

    # Gestion de la mort éventuelle
    if end_hp == 0:
        handle_death(guild_id, tid, attacker_id)

    # Envoi dans le bon salon
    channel = discord.utils.get(discord.utils.get(discord.Client().guilds, id=int(gid)).text_channels, id=channel_id)
    if channel:
        await channel.send(embed=embed)

### 🎯 ATTAQUE NORMALE

async def apply_item_with_cooldown(ctx, user_id, target_id, item, action):
    guild_id = str(ctx.guild.id)
    user_mention = get_mention(ctx.guild, user_id)
    target_mention = get_mention(ctx.guild, target_id)

    # 🎯 Si c'est un objet de soin → traitement spécial
    if action["type"] == "soin":
        heal_amount = action.get("soin", 0)
        crit = action.get("crit", 0)
        final_heal, crit_txt = apply_crit(heal_amount, crit)

        start_hp = hp[guild_id].get(target_id, 100)
        new_hp = min(100, start_hp + final_heal)
        hp[guild_id][target_id] = new_hp
        real_heal = new_hp - start_hp

        leaderboard.setdefault(guild_id, {}).setdefault(user_id, {"degats": 0, "soin": 0, "kills": 0, "morts": 0})
        leaderboard[guild_id][user_id]["soin"] += real_heal

        embed = discord.Embed(
            title="💊 Soins administrés",
            description=f"<@{user_id}> soigne <@{target_id}> de **{real_heal} PV**.{crit_txt}",
            color=discord.Color.green()
        )
        return embed, True  # ✅ fin du bloc de soin

    # Immunité
    if is_immune(guild_id, target_id):
        await ctx.send(f"🛡 {target_mention} est protégé par une **immunité**. Aucun effet.")
        return None, False  # ✅ ici, parce qu'on n'attaque pas

    # Esquive
    if random.random() < get_evade_chance(guild_id, target_id):
        await ctx.send(f"🌀 {target_mention} esquive habilement l’attaque de {user_mention} !")
        return None, False  # ✅ ici aussi

    # ... [code de l’attaque : casque, shield, dmg, KO, messages, status, etc.] ...

    # ✅ À la toute fin, retour par défaut si aucun embed spécial n’est nécessaire
    return None, True  

    # Initialisation PV
    start_hp = hp[guild_id].get(target_id, 100)
    before_pb = shields.get(guild_id, {}).get(target_id, 0)

    base_dmg = action.get("degats", 0)
    bonus_info = []
    bonus_dmg = 0

    # Poison = -1 dégât
    if target_id in poison_status.get(guild_id, {}):
        bonus_dmg -= 1
        bonus_info.append("-1 🧪")

    # Infection = +2 dégâts
    if target_id in infection_status.get(guild_id, {}):
        src = infection_status[guild_id][target_id]["source"]
        if src != target_id:
            bonus_dmg += 2
            bonus_info.append("+2 🧟")

    # Virus = +2 dégâts et transfert
    if user_id in virus_status.get(guild_id, {}):
        bonus_dmg += 2
        bonus_info.append("+2 🦠")
        await appliquer_virus(guild_id, user_id, target_id, ctx.channel.id)

    # Critique
    base_dmg, crit_txt = apply_crit(base_dmg, action.get("crit", 0))

    # Casque
    dmg = apply_casque_reduction(guild_id, target_id, base_dmg + bonus_dmg)

    # Bouclier
    dmg_final, lost_pb, shield_broken = apply_shield(guild_id, target_id, dmg)
    pb_after = shields.get(guild_id, {}).get(target_id, 0)

    # Appliquer dégâts
    end_hp = max(start_hp - dmg_final, 0)
    hp[guild_id][target_id] = end_hp
    real_dmg = start_hp - end_hp

    # Leaderboard
    update_leaderboard_dmg(guild_id, user_id, real_dmg)

    # KO ?
    if end_hp == 0:
        handle_death(guild_id, target_id, user_id)
        reset_txt = f"\n💀 {target_mention} est tombé à 0 PV et revient à 100 PV."
    else:
        reset_txt = ""

    # Affichage
    bonus_str = f" ({' '.join(bonus_info)})" if bonus_info else ""
    if lost_pb and real_dmg == 0:
        desc = (
            f"@{user_mention} inflige {lost_pb} dégâts à {target_mention} avec {item} !\n"
            f"🛡️ {before_pb} - {lost_pb} PB{bonus_str} = 🛡️ {pb_after} PB"
        )
    elif lost_pb and real_dmg > 0:
        desc = (
            f"@{user_mention} inflige {real_dmg + lost_pb} dégâts à {target_mention} avec {item} !\n"
            f"❤️ {start_hp} - {real_dmg} PV{bonus_str} = ❤️ {end_hp} PV / "
            f"🛡️ {before_pb} - {lost_pb} = 🛡️ {pb_after} PB{crit_txt}"
        )
    else:
        desc = (
            f"@{user_mention} inflige {real_dmg} dégâts à {target_mention} avec {item} !\n"
            f"❤️ {start_hp} - {base_dmg} PV{bonus_str} = ❤️ {end_hp} PV{crit_txt}"
        )

    await ctx.send(desc + reset_txt)

    if shield_broken:
        await ctx.send(embed=discord.Embed(
            title="🛡 Bouclier détruit",
            description=f"Le bouclier de {target_mention} a été **détruit**.",
            color=discord.Color.dark_blue()
        ))

    # Statuts à appliquer
    if action.get("type") == "poison":
        await appliquer_poison(guild_id, target_id, ctx.channel.id, user_id)
    elif action.get("type") == "infection":
        await appliquer_infection(guild_id, user_id, target_id, ctx.channel.id)
        
    return None, True

### ☠️ ATTAQUE EN CHAÎNE

async def apply_attack_chain(ctx, user_id, target_id, item, action):
    guild_id = str(ctx.guild.id)
    user_mention = get_mention(ctx.guild, user_id)

    # Déterminer toutes les cibles (1 principale + 2 aléatoires)
    all_members = [m for m in ctx.guild.members if not m.bot and m.id != target_id and m.id != user_id]
    random.shuffle(all_members)
    secondary_targets = all_members[:2]
    all_targets = [(target_id, "principale")] + [(m.id, "secondaire") for m in secondary_targets]

    total_dmg = 0
    for idx, (target, typ) in enumerate(all_targets):
        target_mention = get_mention(ctx.guild, target)

        # Vérifier immunité ou esquive
        if is_immune(guild_id, target):
            await ctx.send(f"🛡 {target_mention} est protégé par une **immunité**. Aucun effet.")
            continue
        if random.random() < get_evade_chance(guild_id, target):
            await ctx.send(f"🌀 {target_mention} esquive l'attaque {typ} de {user_mention} !")
            continue

        # Déterminer les dégâts de base
        dmg_base = 24 if typ == "principale" else 12
        start_hp = hp[guild_id].get(target, 100)
        before_pb = shields.get(guild_id, {}).get(target, 0)

        # Bonus de statut
        bonus_info = []
        bonus_dmg = 0

        # Poison = -1
        if target in poison_status.get(guild_id, {}):
            bonus_dmg -= 1
            bonus_info.append("-1 🧪")

        # Infection = +2 si source différente
        if target in infection_status.get(guild_id, {}):
            src = infection_status[guild_id][target]["source"]
            if src != target:
                bonus_dmg += 2
                bonus_info.append("+2 🧟")
                if src != target and src != user_id:
                    update_leaderboard_dmg(guild_id, src, 2)

        # Virus = +2 uniquement pour la cible principale
        if idx == 0 and user_id in virus_status.get(guild_id, {}):
            bonus_dmg += 2
            bonus_info.append("+2 🦠")
            await appliquer_virus(guild_id, user_id, target, ctx.channel.id)

        # Critique
        dmg_base, crit_txt = apply_crit(dmg_base, action.get("crit", 0))

        # Casque
        dmg = apply_casque_reduction(guild_id, target, dmg_base + bonus_dmg)

        # Bouclier
        dmg_final, lost_pb, shield_broken = apply_shield(guild_id, target, dmg)
        pb_after = shields.get(guild_id, {}).get(target, 0)

        # Appliquer dégâts
        end_hp = max(start_hp - dmg_final, 0)
        hp[guild_id][target] = end_hp
        real_dmg = start_hp - end_hp
        total_dmg += real_dmg

        update_leaderboard_dmg(guild_id, user_id, real_dmg)

        if end_hp == 0:
            handle_death(guild_id, target, user_id)
            reset_txt = f"\n💀 {target_mention} est tombé à 0 PV et revient à 100 PV."
        else:
            reset_txt = ""

        # Message d’attaque
        bonus_str = f" (+{' '.join(bonus_info)})" if bonus_info else ""
        dmg_affiche = dmg_base + bonus_dmg  # dégâts totaux avant bouclier
        crit_str = f" {crit_txt}" if crit_txt else ""

        if lost_pb and real_dmg == 0:
            # 💥 Tout absorbé par le bouclier
            desc = (
                f"**{item}** : {user_mention} inflige {dmg_affiche} dégâts à {target_mention} !\n"
                f"🛡️ {before_pb} - {lost_pb} PB{bonus_str} = 🛡️ {pb_after} PB"
            )

        elif lost_pb and real_dmg > 0:
            # 💥 Partagé entre PV et PB
            desc = (
                f"**{item}** : {user_mention} inflige {dmg_affiche} dégâts à {target_mention} !\n"
                f"❤️ {start_hp} - {dmg_base} PV{bonus_str} = ❤️ {end_hp} PV / "
                f"🛡️ {before_pb} - {lost_pb} = 🛡️ {pb_after} PB{crit_str}"
            )

        else:
            # 💥 Aucun bouclier actif
            desc = (
                f"**{item}** : {user_mention} inflige {dmg_affiche} dégâts à {target_mention} !\n"
                f"❤️ {start_hp} - {dmg_base} PV{bonus_str} = ❤️ {end_hp} PV{crit_str}"
            )

        await ctx.send(desc + reset_txt)

        if shield_broken:
            await ctx.send(embed=discord.Embed(
                title="🛡 Bouclier détruit",
                description=f"Le bouclier de {target_mention} a été **détruit**.",
                color=discord.Color.dark_blue()
            ))

        # Appliquer statuts
        if action["type"] == "poison":
            await appliquer_poison(guild_id, target, ctx.channel.id, user_id)
        elif action["type"] == "infection":
            await appliquer_infection(guild_id, user_id, target, ctx.channel.id)

    # ✅ Pas d’embed spécial global, on a déjà tout affiché
    return None, True


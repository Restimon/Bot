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

    if is_immune(guild_id, target_id):
        await ctx.send(f"🛡 {target_mention} est protégé par une **immunité**. Aucun effet.")
        return

    # Esquive
    if random.random() < get_evade_chance(guild_id, target_id):
        await ctx.send(f"🌀 {target_mention} esquive habilement l’attaque de {user_mention} !")
        return

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

### ☠️ ATTAQUE EN CHAÎNE

async def apply_attack_chain(ctx, user_id, target_id, item, action):
    # TODO : Appliquer l'objet à 3 cibles (1 principale, 2 secondaires)
    pass

from utils import (
    OBJETS,
    GIFS,
    cooldowns,
    ATTACK_COOLDOWN,
    HEAL_COOLDOWN
)
from storage import get_user_data
from storage import hp
from data import virus_status, poison_status
import time
import discord
import random

def is_on_cooldown(guild_id, user_id, action_type):
    now = time.time()
    guild_cooldowns = cooldowns[action_type].setdefault(str(guild_id), {})
    last_used = guild_cooldowns.get(user_id, 0)
    duration = ATTACK_COOLDOWN if action_type == "attack" else HEAL_COOLDOWN
    remaining = duration - (now - last_used)
    return (remaining > 0), max(int(remaining), 0)

def build_embed_from_item(item, description, is_heal_other=False, is_crit=False):
    if is_crit:
        gif_url = GIFS.get("critique")  # <-- gif spécial critique
    else:
        gif_url = GIFS.get("soin_autre") if is_heal_other and OBJETS[item]["type"] == "soin" else GIFS.get(item, "")
    
    color = discord.Color.green() if OBJETS[item]["type"] == "soin" else discord.Color.red()
    embed = discord.Embed(title="📢 Action SomniCorp", description=description, color=color)
    if gif_url:
        embed.set_image(url=gif_url)
    return embed

def check_crit(chance):
    return random.random() < chance

def apply_item_with_cooldown(user_id, target_id, item, ctx):
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
        return None

    action = OBJETS[item]

    if action["type"] == "attaque":
        on_cooldown, remaining = is_on_cooldown(guild_id, user_id, "attack")
        if on_cooldown:
            return build_embed_from_item(item, f"{user_mention} doit attendre encore {remaining // 60} min avant d'attaquer."), False
        if target_hp <= 0:
            return build_embed_from_item(item, f"⚠️ {target_mention} est déjà hors service."), False
        
        evade_chance = 0.1
        if random.random() < evade_chance:
            return build_embed_from_item(
                item,
                f"💨 {target_mention} esquive habilement l’attaque de {user_mention} avec {item} ! Aucun dégât infligé."
            ), True

        base_dmg = action["degats"]
        crit_txt = ""
        if check_crit(action.get("crit", 0)):
            base_dmg *= 2
            crit_txt = " **(Coup critique ! 💥)**"

        emoji_modif = ""
        modif_txt = ""

        if user_id in poison_status.get(guild_id, {}):
            base_dmg -= 1
            emoji_modif = "🧪"
            modif_txt = f"(-1 {emoji_modif})"

        if user_id in virus_status.get(guild_id, {}):
            base_dmg += 2
            emoji_modif = "🦠"
            modif_txt = f"(+2 {emoji_modif})"
            hp[guild_id][user_id] = max(hp[guild_id].get(user_id, 100) - 2, 0)
            virus_status[guild_id][target_id] = virus_status[guild_id][user_id].copy()

        dmg = max(0, base_dmg)
        before = target_hp
        new_hp = max(target_hp - dmg, 0)
        hp[guild_id][target_id] = new_hp
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

    elif action["type"] == "soin":
        on_cooldown, remaining = is_on_cooldown(guild_id, user_id, "heal")
        if on_cooldown:
            return build_embed_from_item(item, f"{user_mention} doit attendre encore {remaining // 60} min pour se soigner."), False

        heal = action["soin"]
        crit_txt = ""
        if check_crit(action.get("crit", 0)):
            heal *= 2
            crit_txt = " **(Soin critique ! ✨)**"

        before = target_hp
        new_hp = min(target_hp + heal, 100)
        hp[guild_id][target_id] = new_hp
        user_stats["soin"] += heal
        cooldowns["heal"].setdefault(guild_id, {})[user_id] = now

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
        virus_status[guild_id][target_id] = {
            "start": now,
            "duration": duration,
            "last_tick": 0
        }
        return build_embed_from_item(
            item,
            f"🦠 {target_mention} est maintenant infecté par le virus ! Il subit {dmg} dégâts immédiats, puis 5 par heure pendant {duration // 3600}h.{crit_txt}"
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
        poison_status[guild_id][target_id] = {
            "start": now,
            "duration": duration,
            "last_tick": 0
        }
        return build_embed_from_item(
            item,
            f"🧪 {target_mention} est maintenant empoisonné ! Il subit {dmg} dégâts immédiats, puis 3 toutes les 30 minutes pendant {duration // 3600}h.{crit_txt}"
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

    else:
        return build_embed_from_item(item, f"⚠️ L'objet {item} est de type inconnu ou non pris en charge."), False

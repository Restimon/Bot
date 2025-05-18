import time
import discord
from utils import OBJETS, GIFS, cooldowns, ATTACK_COOLDOWN, HEAL_COOLDOWN, leaderboard, hp

def is_on_cooldown(user_id, action_type):
    now = time.time()
    last_used = cooldowns[action_type].get(user_id, 0)
    duration = ATTACK_COOLDOWN if action_type == "attack" else HEAL_COOLDOWN
    remaining = duration - (now - last_used)
    return (remaining > 0), max(int(remaining), 0)

def build_embed_from_item(item, description, is_heal_other=False):
    gif_url = GIFS.get("soin_autre") if is_heal_other and OBJETS[item]["type"] == "soin" else GIFS.get(item, "")
    color = discord.Color.green() if OBJETS[item]["type"] == "soin" else discord.Color.red()
    embed = discord.Embed(title="📢 Action SomniCorp", description=description, color=color)
    if gif_url:
        embed.set_image(url=gif_url)
    return embed

def apply_item_with_cooldown(user_id, target_id, item, ctx):
    action = OBJETS[item]
    now = time.time()

    if user_id not in hp:
        hp[user_id] = 100
    if target_id not in hp:
        hp[target_id] = 100
    if user_id not in leaderboard:
        leaderboard[user_id] = {"degats": 0, "soin": 0}

    user_obj = ctx.guild.get_member(int(user_id))
    user_mention = user_obj.mention if user_obj else f"<@{user_id}>"
    target_mention = ctx.guild.get_member(int(target_id)).mention

    if action["type"] == "attaque":
        on_cooldown, remaining = is_on_cooldown(user_id, "attack")
        if on_cooldown:
            return build_embed_from_item(item, f"{user_mention} doit attendre encore {remaining // 60} min avant d'attaquer.\n**Information SomniCorp !**")
        if hp[user_id] <= 0:
            return build_embed_from_item(item, f"⚠️ {user_mention} est temporairement hors service selon SomniCorp. Attaque refusée.")

        dmg = action["degats"]
        before = hp[target_id]
        hp[target_id] = max(hp[target_id] - dmg, 0)
        after = hp[target_id]
        leaderboard[user_id]["degats"] += dmg
        cooldowns["attack"][user_id] = now
        return build_embed_from_item(item, f"{user_mention} inflige {dmg} dégâts à {target_mention} avec {item} !\n**Information SomniCorp !** {target_mention} : {before} - {dmg} = {after} / 100 PV")

    elif action["type"] == "soin":
        on_cooldown, remaining = is_on_cooldown(user_id, "heal")
        if on_cooldown:
            return build_embed_from_item(item, f"⏳ {user_mention}, veuillez patienter {remaining // 60} min selon les protocoles de recharge SomniCorp.", user_id != target_id)

        heal = action["soin"]
        before = hp[target_id]
        hp[target_id] = min(hp[target_id] + heal, 100)
        after = hp[target_id]
        leaderboard[user_id]["soin"] += heal
        cooldowns["heal"][user_id] = now
        return build_embed_from_item(item, f"{user_mention} soigne {target_mention} de {heal} PV avec {item} !\n**Information SomniCorp !** {target_mention} : {before} + {heal} = {after} / 100 PV", user_id != target_id)

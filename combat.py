from utils import (
    OBJETS,
    GIFS,
    cooldowns,
    ATTACK_COOLDOWN,
    HEAL_COOLDOWN
)
from storage import get_user_data
from storage import hp
import time
import discord

def is_on_cooldown(guild_id, user_id, action_type):
    now = time.time()
    guild_cooldowns = cooldowns[action_type].setdefault(str(guild_id), {})
    last_used = guild_cooldowns.get(user_id, 0)
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
    guild_id = str(ctx.guild.id)
    user_id = str(user_id)
    target_id = str(target_id)
    now = time.time()

    user_inv, user_hp, user_stats = get_user_data(guild_id, user_id)
    _, target_hp, _ = get_user_data(guild_id, target_id)

    user_obj = ctx.guild.get_member(int(user_id))
    target_obj = ctx.guild.get_member(int(target_id))
    user_mention = user_obj.mention if user_obj else f"<@{user_id}>"
    target_mention = target_obj.mention if target_obj else f"<@{target_id}>"

    action = OBJETS[item]

    if action["type"] == "attaque":
        on_cooldown, remaining = is_on_cooldown(guild_id, user_id, "attack")
        if on_cooldown:
            return build_embed_from_item(
                item,
                f"{user_mention} doit attendre encore {remaining // 60} min avant d'attaquer.\n**Information SomniCorp !**"
            ), False

        if target_hp <= 0:
            return build_embed_from_item(
                item,
                f"⚠️ {target_mention} est déjà hors service. Attaque inutile."
            ), False

        dmg = action["degats"]
        before = target_hp
        new_hp = max(target_hp - dmg, 0)

        hp[guild_id][target_id] = new_hp
        user_stats["degats"] += dmg
        cooldowns["attack"].setdefault(guild_id, {})[user_id] = now

        return build_embed_from_item(
            item,
            f"{user_mention} inflige {dmg} dégâts à {target_mention} avec {item} !\n**SomniCorp :** {target_mention} : {before} - {dmg} = {new_hp} / 100 PV"
        ), True

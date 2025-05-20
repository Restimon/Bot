import random
import discord
from utils import OBJETS
from storage import get_user_data

def get_random_item():
    """Retourne un objet au hasard selon sa rareté."""
    pool = []
    for emoji, data in OBJETS.items():
        pool.extend([emoji] * (26 - data["rarete"]))
    return random.choice(pool)

def build_inventory_embed(user_id: str, bot: discord.Client, guild_id: str) -> discord.Embed:
    user_items, _, _ = get_user_data(guild_id, user_id)

    # Compte les objets
    item_counts = {}
    for item in user_items:
        item_counts[item] = item_counts.get(item, 0) + 1

    embed = discord.Embed(color=discord.Color.blurple())

    if not item_counts:
        embed.description = "📦 SomniCorp ne détecte aucun objet dans l'inventaire."
    else:
        # Affiche chaque emoji avec la quantité
        rows = [
            f"{emoji} × **{count}** — "
            f"{'🗡️' if OBJETS[emoji]['type'] == 'attaque' else '💚'} {OBJETS[emoji].get('degats') or OBJETS[emoji].get('soin')} "
            f"{'dégâts' if OBJETS[emoji]['type'] == 'attaque' else 'soins'}"
            for emoji, count in sorted(item_counts.items(), key=lambda x: -x[1])
        ]
        embed.description = "\n".join(rows)

    guild = bot.get_guild(int(guild_id))
    user = guild.get_member(int(user_id)) if guild else None
    name = user.display_name if user else f"ID {user_id}"
    embed.set_author(name=f"Inventaire SomniCorp de {name}")

    return embed


import random
import discord
from utils import OBJETS, inventaire

def get_random_item():
    """Retourne un objet au hasard selon sa rareté."""
    pool = []
    for emoji, data in OBJETS.items():
        pool.extend([emoji] * (26 - data["rarete"]))
    return random.choice(pool)

def build_inventory_embed(user_id: str, bot: discord.Client) -> discord.Embed:
    """Construit un embed Discord affichant l'inventaire d'un utilisateur."""
    user_items = inventaire.get(user_id, [])
    item_counts = {}

    for item in user_items:
        item_counts[item] = item_counts.get(item, 0) + 1

    embed = discord.Embed(color=discord.Color.blurple())
    if not item_counts:
        embed.description = "📦 SomniCorp détecte aucun objet dans l'inventaire."
    else:
        rows = [f"{emoji} : **{count}**" for emoji, count in sorted(item_counts.items())]
        embed.description = "\n".join(rows)

    user = bot.get_user(int(user_id))
    name = user.name if user else f"ID {user_id}"
    embed.set_author(name=f"Inventaire SomniCorp de {name}")
    return embed

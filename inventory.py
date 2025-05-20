import random
import discord
from utils import OBJETS, get_user_data

def get_random_item():
    """Retourne un objet au hasard selon sa rareté."""
    pool = []
    for emoji, data in OBJETS.items():
        pool.extend([emoji] * (26 - data["rarete"]))
    return random.choice(pool)

def build_inventory_embed(user_id: str, bot: discord.Client, guild_id: str) -> discord.Embed:
    """
    Construit un embed Discord affichant l'inventaire d’un utilisateur dans un serveur spécifique.
    """
    user_items, _, _ = get_user_data(guild_id, user_id)
    item_counts = {}

    # Assurer que c'est bien une liste
    if isinstance(user_items, str):
        user_items = [user_items]

    for item in user_items:
        item_counts[item] = item_counts.get(item, 0) + 1

    embed = discord.Embed(color=discord.Color.blurple())
    if not item_counts:
        embed.description = "📦 Aucun objet détecté dans l’inventaire SomniCorp."
    else:
        rows = [f"{emoji} : **{count}**" for emoji, count in sorted(item_counts.items())]
        embed.description = "\n".join(rows)

    # Tentative de récupération du nom d'affichage
    guild = bot.get_guild(int(guild_id))
    member = guild.get_member(int(user_id)) if guild else None
    name = member.display_name if member else f"Utilisateur inconnu ({user_id})"

    embed.set_author(name=f"Inventaire SomniCorp de {name}")
    return embed

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
        rows = []
        for emoji, count in sorted(item_counts.items(), key=lambda x: -x[1]):
            obj = OBJETS[emoji]
            if obj["type"] == "attaque":
                effet = ""
                if emoji == "🦠":
                    effet = " (+2🦠)"
                elif emoji == "🧪":
                    effet = " (-1🧪)"
                rows.append(f"{emoji} × **{count}** — 🗡️ {obj['degats']} dégâts{effet}")
            elif obj["type"] == "soin":
                rows.append(f"{emoji} × **{count}** — 💚 {obj['soin']} soins")
            elif obj["type"] == "virus":
                rows.append(f"{emoji} × **{count}** — 🦠 Infecte (5 dégâts/h pendant 6h)")
            elif obj["type"] == "poison":
                rows.append(f"{emoji} × **{count}** — 🧪 Empoisonne (3 dégâts/30min pendant 3h)")
            elif obj["type"] == "vol":
                rows.append(f"{emoji} × **{count}** — 🔍 Vole un objet à un joueur")
            elif obj["type"] == "mysterybox":
                rows.append(f"{emoji} × **{count}** — 📦 Donne 1 à 3 objets aléatoires")
            else:
                rows.append(f"{emoji} × **{count}** — Objet inconnu")

        embed.description = "\n".join(rows)

    guild = bot.get_guild(int(guild_id))
    user = guild.get_member(int(user_id)) if guild else None
    name = user.display_name if user else f"ID {user_id}"
    embed.set_author(name=f"Inventaire SomniCorp de {name}")

    return embed

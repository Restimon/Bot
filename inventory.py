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
            t = obj["type"]

            if t == "attaque":
                effet = ""
                if emoji == "🦠":
                    effet = " (+2🦠 si porteur)"
                elif emoji == "🧪":
                    effet = " (-1🧪 si porteur)"
                rows.append(f"{emoji} × **{count}** — 🗡️ {obj['degats']} dégâts{effet}")

            elif t == "soin":
                rows.append(f"{emoji} × **{count}** — 💚 Restaure {obj['soin']} PV")

            elif t == "virus":
                rows.append(f"{emoji} × **{count}** — 🦠 Infection virale : 5 dégâts initiaux, puis 5 dégâts/heure pendant 6h\n💥 -2 PV par attaque + propagation automatique.")

            elif t == "poison":
                rows.append(f"{emoji} × **{count}** — 🧪 Empoisonnement : 3 dégâts initiaux, puis 3 dégâts/30min pendant 3h\n🩸 Attaques infligent -1 dégât.")
    
            elif t == "infection":
                rows.append(f"{emoji} × **{count}** — 🧟 Infection : 5 dégâts initiaux, puis 2 dégâts/30min pendant 3h\n🧬 25% de chance de contaminer la cible lors d’une attaque.")

            elif t == "vol":
                rows.append(f"{emoji} × **{count}** — 🔍 Vole un objet au hasard dans l’inventaire d’un joueur.")

            elif t == "mysterybox":
                rows.append(f"{emoji} × **{count}** — 📦 Boîte surprise SomniCorp : contient 1 à 3 objets aléatoires.")

            elif t == "vaccin":
                rows.append(f"{emoji} × **{count}** — 💉 Vaccin : Immunise contre virus, poison et infection (via `/heal`).")

            else:
                rows.append(f"{emoji} × **{count}** — ❓ Type d’objet inconnu.")


        embed.description = "\n".join(rows)

    guild = bot.get_guild(int(guild_id))
    user = guild.get_member(int(user_id)) if guild else None
    name = user.display_name if user else f"ID {user_id}"
    embed.set_author(name=f"Inventaire SomniCorp de {name}")

    return embed

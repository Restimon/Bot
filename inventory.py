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
            obj = OBJETS.get(emoji, {})
            obj_type = obj.get("type", "inconnu")

            if obj_type == "attaque":
                degats = obj.get("degats", "?")
                crit = obj.get("crit", 0)
                rows.append(f"{emoji} × **{count}** — 🗡️ {degats} dégâts (🎯 {int(crit * 100)}% crit)")
            elif emoji == "☠️":
                d1 = obj.get("degats_principal", "?")
                d2 = obj.get("degats_secondaire", "?")
                crit = obj.get("crit", 0)
                rows.append(f"{emoji} × **{count}** — ☠️ Attaque en chaîne : {d1} dégâts à 1 cible, {d2} à 2 autres (🎯 {int(crit * 100)}%)")
            elif obj_type == "virus":
                dmg = obj.get("degats", "?")
                duree = obj.get("duree", 0)
                crit = obj.get("crit", 0)
                rows.append(f"{emoji} × **{count}** — 🦠 Virus : {dmg} dégâts initiaux + 5/h pendant {duree // 3600}h (🎯 {int(crit * 100)}%)")
            elif obj_type == "poison":
                dmg = obj.get("degats", "?")
                interval = obj.get("intervalle", 1800)
                duree = obj.get("duree", 0)
                crit = obj.get("crit", 0)
                rows.append(f"{emoji} × **{count}** — 🧪 Poison : {dmg} initiaux + 3 toutes les {interval // 60} min pendant {duree // 3600}h (🎯 {int(crit * 100)}%)")
            elif obj_type == "infection":
                dmg = obj.get("degats", "?")
                interval = obj.get("intervalle", 1800)
                duree = obj.get("duree", 0)
                rows.append(f"{emoji} × **{count}** — 🧟 Infection : {dmg} initiaux + 2 toutes les {interval // 60} min pendant {duree // 3600}h ⚠️ Propagation possible")
            elif obj_type == "soin":
                soin = obj.get("soin", "?")
                crit = obj.get("crit", 0)
                rows.append(f"{emoji} × **{count}** — 💚 Soigne {soin} PV (✨ {int(crit * 100)}% crit)")
            elif obj_type == "regen":
                val = obj.get("valeur", "?")
                interval = obj.get("intervalle", 1800)
                duree = obj.get("duree", 0)
                rows.append(f"{emoji} × **{count}** — 💕 Régénère {val} PV toutes les {interval // 60} min pendant {duree // 3600}h")
            elif obj_type == "vol":
                rows.append(f"{emoji} × **{count}** — 🔍 Vole un objet aléatoire à la cible")
            elif obj_type == "mysterybox":
                rows.append(f"{emoji} × **{count}** — 📦 Boîte surprise : donne 1 à 3 objets aléatoires")
            elif obj_type == "vaccin":
                rows.append(f"{emoji} × **{count}** — 💉 Utilisable uniquement via `/heal`, soigne virus et poison")
            elif obj_type == "bouclier":
                val = obj.get("valeur", 20)
                rows.append(f"{emoji} × **{count}** — 🛡 Donne un bouclier de {val} points absorbant les dégâts")
            elif obj_type == "reduction":
                pourcent = int(obj.get("valeur", 0.5) * 100)
                duree = obj.get("duree", 0)
                rows.append(f"{emoji} × **{count}** — 🪖 Casque : réduit les dégâts de {pourcent}% pendant {duree // 3600}h")
            elif obj_type == "esquive+":
                bonus = int(obj.get("valeur", 0.2) * 100)
                duree = obj.get("duree", 0)
                rows.append(f"{emoji} × **{count}** — 👟 Esquive +{bonus}% pendant {duree // 3600}h")
            elif obj_type == "immunite":
                duree = obj.get("duree", 0)
                rows.append(f"{emoji} × **{count}** — ⭐️ Immunité : aucun dégât reçu pendant {duree // 3600}h")
            else:
                rows.append(f"{emoji} × **{count}** — Objet inconnu")

        embed.description = "\n".join(rows)

    guild = bot.get_guild(int(guild_id))
    user = guild.get_member(int(user_id)) if guild else None
    name = user.display_name if user else f"ID {user_id}"
    embed.set_author(name=f"Inventaire SomniCorp de {name}")

    return embed

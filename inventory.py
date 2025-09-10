# inventory.py
import random
import discord
from utils import OBJETS
from storage import get_user_data

# même emoji que tirage.py / shop.py
TICKET_EMOJI = "🎟️"

# === RANDOM ITEM (fallback utilitaire) ===
def get_random_item(debug: bool = False):
    """Retourne un objet au hasard selon sa rareté."""
    pool = []
    for emoji, data in OBJETS.items():
        poids = max(1, 26 - data.get("rarete", 13))  # au moins 1
        pool.extend([emoji] * poids)

    if debug:
        print(f"[inventory.get_random_item] pool={pool}")

    return random.choice(pool) if pool else None


# === BUILD INVENTORY EMBED ===
def build_inventory_embed(user_id: str, bot: discord.Client, guild_id: str) -> discord.Embed:
    """
    Construit un embed d'inventaire :
      - Affiche d'abord le nombre de tickets 🎟️
      - Puis liste les autres objets (hors 🎟️) avec une description lisible
    """
    user_items, _, _ = get_user_data(guild_id, user_id)

    # Compter les items (str uniquement)
    item_counts = {}
    for item in user_items:
        if isinstance(item, str):
            item_counts[item] = item_counts.get(item, 0) + 1

    ticket_count = item_counts.get(TICKET_EMOJI, 0)

    embed = discord.Embed(color=discord.Color.blurple())

    # En-tête Tickets
    if ticket_count > 0:
        tickets_line = f"🎟️ **Tickets de tirage** : **{ticket_count}**"
    else:
        tickets_line = "🎟️ **Tickets de tirage** : aucun"

    # Corps (hors 🎟️)
    rows = []
    autres = {e: c for e, c in item_counts.items() if e != TICKET_EMOJI}
    if not autres:
        rows.append("📦 Aucun autre objet détecté.")
    else:
        for emoji, count in sorted(autres.items(), key=lambda x: (-x[1], x[0])):
            obj = OBJETS.get(emoji, {})
            typ = obj.get("type", "inconnu")

            if typ == "attaque":
                degats = obj.get("degats", "?")
                crit = int(obj.get("crit", 0) * 100)
                rows.append(f"{emoji} × **{count}** — 🗡️ {degats} dégâts (🎯 {crit}% crit)")

            elif emoji == "☠️":
                d1 = obj.get("degats_principal", "?")
                d2 = obj.get("degats_secondaire", "?")
                crit = int(obj.get("crit", 0) * 100)
                rows.append(f"{emoji} × **{count}** — ☠️ Attaque en chaîne : {d1} / {d2} / {d2} (🎯 {crit}%)")

            elif typ == "virus":
                dmg = obj.get("degats", "?")
                duree_h = obj.get("duree", 0) // 3600
                rows.append(f"{emoji} × **{count}** — 🦠 Virus : {dmg} initiaux + 5/h pendant {duree_h}h")

            elif typ == "poison":
                dmg = obj.get("degats", "?")
                interval = obj.get("intervalle", 1800) // 60
                duree_h = obj.get("duree", 0) // 3600
                rows.append(f"{emoji} × **{count}** — 🧪 Poison : {dmg} initiaux + 3 / {interval} min ({duree_h}h)")

            elif typ == "infection":
                dmg = obj.get("degats", "?")
                interval = obj.get("intervalle", 1800) // 60
                duree_h = obj.get("duree", 0) // 3600
                rows.append(f"{emoji} × **{count}** — 🧟 Infection : {dmg} initiaux + 2 / {interval} min ({duree_h}h) ⚠️ Propagation")

            elif typ == "soin":
                soin = obj.get("soin", "?")
                crit = int(obj.get("crit", 0) * 100)
                rows.append(f"{emoji} × **{count}** — 💚 Soigne {soin} PV (✨ {crit}% crit)")

            elif typ == "regen":
                val = obj.get("valeur", "?")
                interval = obj.get("intervalle", 1800) // 60
                duree_h = obj.get("duree", 0) // 3600
                rows.append(f"{emoji} × **{count}** — 💕 Régénère {val} PV / {interval} min pendant {duree_h}h")

            elif typ == "vol":
                rows.append(f"{emoji} × **{count}** — 🔍 Vole un objet aléatoire à la cible")

            elif typ == "mysterybox":
                rows.append(f"{emoji} × **{count}** — 📦 Boîte surprise : donne 1 à 3 objets aléatoires")

            elif typ == "vaccin":
                rows.append(f"{emoji} × **{count}** — 💉 Utilisable via `/heal` : soigne virus/poison")

            elif typ == "bouclier":
                val = obj.get("valeur", 20)
                rows.append(f"{emoji} × **{count}** — 🛡 Bouclier de {val} PB")

            elif typ == "reduction":
                pourcent = int(obj.get("valeur", 0.5) * 100)
                duree_h = obj.get("duree", 0) // 3600
                rows.append(f"{emoji} × **{count}** — 🪖 Réduction dégâts {pourcent}% pendant {duree_h}h")

            elif typ == "esquive+":
                bonus = int(obj.get("valeur", 0.2) * 100)
                duree_h = obj.get("duree", 0) // 3600
                rows.append(f"{emoji} × **{count}** — 👟 Esquive +{bonus}% pendant {duree_h}h")

            elif typ == "immunite":
                duree_h = obj.get("duree", 0) // 3600
                rows.append(f"{emoji} × **{count}** — ⭐️ Immunité pendant {duree_h}h")

            else:
                rows.append(f"{emoji} × **{count}** — Objet non référencé")

    embed.description = tickets_line + "\n\n" + ("\n".join(rows) if rows else "")

    # Auteur / avatar
    guild = bot.get_guild(int(guild_id))
    user = guild.get_member(int(user_id)) if guild else None
    name = user.display_name if user else f"ID {user_id}"
    if user:
        embed.set_author(name=f"Inventaire GotValis de {name}", icon_url=user.display_avatar.url)
    else:
        embed.set_author(name=f"Inventaire GotValis de {name}")

    return embed


# (optionnel) petite commande pour afficher l’inventaire
async def register_inventory_command(bot: discord.Client):
    @bot.tree.command(name="inventory", description="Affiche ton inventaire GotValis.")
    async def inventory_cmd(interaction: discord.Interaction, user: discord.Member | None = None):
        await interaction.response.defer(ephemeral=True)
        m = user or interaction.user
        embed = build_inventory_embed(str(m.id), interaction.client, str(interaction.guild_id))
        await interaction.followup.send(embed=embed, ephemeral=True)

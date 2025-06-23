import random
import discord
from discord import app_commands
from storage import get_user_data
from utils import OBJETS
from embeds import build_embed_from_item
from passifs import appliquer_passif  # ✅ Pour Kieran Vox

# Fonction pour décrire un objet
def describe_item(emoji):
    obj = OBJETS.get(emoji, {})
    t = obj.get("type")
    if t == "attaque":
        return f"🗡️ Inflige {obj['degats']} dégâts. (Crit {int(obj.get('crit', 0) * 100)}%)"
    if t == "virus":
        return "🦠 5 dégâts initiaux + 5/h pendant 6h."
    if t == "poison":
        return "🧪 3 dégâts initiaux + 3/30min pendant 3h."
    if t == "infection":
        return "🧟 5 dégâts initiaux + 2/30min pendant 3h (25% de propagation)."
    if t == "soin":
        return f"💚 Restaure {obj['soin']} PV. (Crit {int(obj.get('crit', 0) * 100)}%)"
    if t == "regen":
        return "✨ Régénère 3 PV toutes les 30min pendant 3h."
    if t == "mysterybox":
        return "📦 Boîte surprise : objets aléatoires."
    if t == "vol":
        return "🔍 Vole un objet à un autre joueur."
    if t == "vaccin":
        return "💉 Soigne le virus via /heal."
    if t == "bouclier":
        return "🛡 +20 points de bouclier."
    if t == "esquive+":
        return "👟 Augmente les chances d’esquive pendant 3h."
    if t == "reduction":
        return "🪖 Réduction de dégâts x0.5 pendant 4h."
    if t == "immunite":
        return "⭐️ Immunité totale pendant 2h."
    return "❓ Effet inconnu."

# Commande box
def register_box_command(bot):
    @bot.tree.command(name="box", description="Ouvre une boîte 📦 et reçois des objets aléatoires.")
    async def box_slash(interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)

        guild_id = str(interaction.guild.id)
        user_id = str(interaction.user.id)

        user_inv, _, _ = get_user_data(guild_id, user_id)

        if "📦" not in user_inv:
            await interaction.followup.send("❌ Tu n’as pas de 📦 à ouvrir.", ephemeral=True)
            return

        # Retire une boîte
        user_inv.remove("📦")

        # Prépare la liste pondérée par rareté
        rarete_pool = []
        for emoji, data in OBJETS.items():
            if emoji == "📦":
                continue
            rarete = data.get("rarete", 1)
            rarete_pool.extend([emoji] * rarete)

        # 🔮 Passif Kieran Vox : +1 objet bonus
        result_passif = appliquer_passif(user_id, "box", {
            "guild_id": guild_id,
            "user_id": user_id
        })
        bonus = result_passif.get("bonus_objets_box", 0) if result_passif else 0

        # Nombre d'objets à looter
        nb_objets = random.randint(1, 3) + bonus

        # Loot des objets
        loot = [random.choice(rarete_pool) for _ in range(nb_objets)]

        # Ajout au joueur
        user_inv.extend(loot)

        # Format du résultat
        counts = {}
        for item in loot:
            counts[item] = counts.get(item, 0) + 1

        loot_display = "\n".join(
            f"{emoji} × {count} — {describe_item(emoji)}"
            for emoji, count in counts.items()
        )

        embed = discord.Embed(
            title="📦 Boîte ouverte !",
            description=f"Voici ce que tu as reçu :\n\n{loot_display}",
            color=discord.Color.gold()
        )

        await interaction.followup.send(embed=embed)

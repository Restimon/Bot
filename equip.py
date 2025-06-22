import discord
import os
from discord import app_commands
from data import personnages_equipés
from personnage import PERSONNAGES
from storage import get_collection

# 🎨 Couleurs selon la rareté
RARETE_COULEURS = {
    "Commun": discord.Color.light_gray(),
    "Rare": discord.Color.blue(),
    "Épique": discord.Color.purple(),
    "Légendaire": discord.Color.gold()
}

def register_equip_command(bot):
    @bot.tree.command(name="équipé", description="Affiche le personnage actuellement actif.")
    async def equip_slash(interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)

        guild_id = str(interaction.guild.id)
        user_id = str(interaction.user.id)

        perso_nom = personnages_equipés.get(guild_id, {}).get(user_id)
        if not perso_nom or perso_nom not in PERSONNAGES:
            embed = discord.Embed(
                title="🎭 Personnage actif",
                description="Aucun personnage n’est actuellement équipé.",
                color=discord.Color.dark_grey()
            )
            await interaction.followup.send(embed=embed)
            return

        collection = get_collection(guild_id, user_id)
        if perso_nom not in collection:
            embed = discord.Embed(
                title="🎭 Personnage actif",
                description="Personnage non présent dans ta collection.",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)
            return

        perso_data = PERSONNAGES[perso_nom]
        rarete = perso_data.get("rarete", "Commun")
        color = RARETE_COULEURS.get(rarete, discord.Color.default())
        faction = perso_data.get("faction", "Inconnu")
        image_path = perso_data.get("image")
        image_name = os.path.basename(image_path) if image_path else None

        # Tri pour position dans collection
        sorted_names = sorted(
            collection.keys(),
            key=lambda nom: (
                {"Commun": 0, "Rare": 1, "Épique": 2, "Légendaire": 3}.get(PERSONNAGES[nom]["rarete"], 99),
                PERSONNAGES[nom]["faction"],
                nom
            )
        )
        index = sorted_names.index(perso_nom) + 1

        # Embed
        embed = discord.Embed(
            title="🎭 Personnage actif",
            description=(
                f"**#{index} – {perso_nom}**\n"
                f"🎁 **{perso_data['passif']['nom']}**\n"
                f"> {perso_data['passif']['effet']}"
            ),
            color=color
        )
        embed.add_field(name="Rareté", value=rarete, inline=True)
        embed.add_field(name="Faction", value=faction, inline=True)
        embed.set_footer(text="Ce personnage est actif en permanence.")

        # Image
        if image_path and os.path.exists(image_path):
            file = discord.File(image_path, filename=image_name)
            embed.set_image(url=f"attachment://{image_name}")
            await interaction.followup.send(embed=embed, file=file)
        else:
            await interaction.followup.send(embed=embed)

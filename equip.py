import discord
import os
from discord import app_commands
from data import personnages_equipés
from personnage import PERSONNAGES
from storage import get_collection

def register_equip_command(bot):
    @bot.tree.command(name="équipé", description="Affiche le personnage actuellement actif.")
    async def equip_slash(interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)

        guild_id = str(interaction.guild.id)
        uid = str(interaction.user.id)

        perso_nom = personnages_equipés.get(guild_id, {}).get(uid)
        if not perso_nom or perso_nom not in PERSONNAGES:
            embed = discord.Embed(
                title="🎭 Personnage actif",
                description="Aucun personnage n’est actuellement équipé.",
                color=discord.Color.dark_grey()
            )
            await interaction.followup.send(embed=embed)
            return

        collection = get_collection(guild_id, uid)
        if perso_nom not in collection:
            embed = discord.Embed(
                title="🎭 Personnage actif",
                description="Personnage non présent dans votre collection.",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)
            return

        perso_data = PERSONNAGES[perso_nom]
        sorted_names = sorted(
            collection.keys(),
            key=lambda nom: (
                {"Commun": 0, "Rare": 1, "Epique": 2, "Legendaire": 3}.get(PERSONNAGES[nom]["rarete"], 99),
                PERSONNAGES[nom]["faction"],
                nom
            )
        )
        index = sorted_names.index(perso_nom) + 1
        image_path = perso_data.get("image")
        image_name = os.path.basename(image_path) if image_path else None

        embed = discord.Embed(
            title="🎭 Personnage actif",
            description=(
                f"**#{index} – {perso_nom}**\n"
                f"🎁 {perso_data['passif_nom']} {perso_data['emoji']}\n"
                f"> {perso_data['passif_desc']}"
            ),
            color=discord.Color.gold()
        )
        embed.set_footer(text="Ce personnage est actif en permanence.")

        if image_path and os.path.exists(image_path):
            file = discord.File(image_path, filename=image_name)
            embed.set_image(url=f"attachment://{image_name}")
            await interaction.followup.send(embed=embed, file=file)
        else:
            await interaction.followup.send(embed=embed)

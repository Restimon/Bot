import discord
from discord import app_commands
from discord.ext import commands
from personnage import get_personnages_trie_par_rarete_et_faction
from storage import get_collection
from embeds import build_personnage_embed
import os

class Perso(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="perso", description="Affiche un personnage de ta collection ou celle d’un autre joueur.")
    @app_commands.describe(index="Numéro du personnage (voir /collection)", user="Joueur cible (optionnel)")
    async def perso(self, interaction: discord.Interaction, index: int, user: discord.Member = None):
        await interaction.response.defer()

        target = user or interaction.user
        user_id = str(target.id)
        guild_id = str(interaction.guild_id)

        collection = get_collection(guild_id, user_id)
        if not collection:
            await interaction.followup.send("❌ Ce joueur n’a aucun personnage dans sa collection.", ephemeral=True)
            return

        # Liste complète en fonction de la collection
        full_list = []
        for perso in get_personnages_trie_par_rarete_et_faction():
            nom = perso["nom"]
            nb = collection.get(nom, 0)
            full_list.extend([perso] * nb)

        if index < 1 or index > len(full_list):
            await interaction.followup.send(f"❌ Numéro invalide. {target.display_name} possède {len(full_list)} personnage(s).", ephemeral=True)
            return

        perso = full_list[index - 1]
        embed = build_personnage_embed(perso, user=target)

        # Image locale si dispo
        try:
            image_path = perso.get("image")
            image_filename = os.path.basename(image_path)
            file = discord.File(image_path, filename=image_filename)
            embed.set_image(url=f"attachment://{image_filename}")
            await interaction.followup.send(embed=embed, file=file)
        except Exception:
            await interaction.followup.send(embed=embed)

    # Autocomplétion dynamique
    @perso.autocomplete("index")
    async def index_autocomplete(self, interaction: discord.Interaction, current: str):
        target = interaction.namespace.user or interaction.user
        user_id = str(target.id)
        guild_id = str(interaction.guild_id)

        collection = get_collection(guild_id, user_id)
        if not collection:
            return []

        full_list = []
        for perso in get_personnages_trie_par_rarete_et_faction():
            nom = perso["nom"]
            nb = collection.get(nom, 0)
            full_list.extend([nom] * nb)

        current = current.strip()
        return [
            app_commands.Choice(name=f"{i+1}. {nom}", value=i+1)
            for i, nom in enumerate(full_list[:25])
            if current in str(i + 1)
        ]

async def setup(bot):
    await bot.add_cog(Perso(bot))

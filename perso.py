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

    @app_commands.command(name="perso", description="Affiche un personnage de ta collection par son numéro (/collection).")
    @app_commands.describe(index="Numéro du personnage dans ta collection (voir /collection)")
    async def perso(self, interaction: discord.Interaction, index: int):
        await interaction.response.defer()

        user_id = str(interaction.user.id)
        guild_id = str(interaction.guild_id)

        # Récupère la collection complète du joueur
        collection = get_collection(guild_id, user_id)

        if not collection:
            await interaction.followup.send("❌ Tu n’as aucun personnage dans ta collection.", ephemeral=True)
            return

        # 🔁 On recrée une liste complète avec doublons (ex : si x3 → 3 fois dans la liste)
        liste_complete = []
        for perso in get_personnages_trie_par_rarete_et_faction():
            nom = perso["nom"]
            nb = collection.get(nom, 0)
            liste_complete.extend([perso] * nb)

        if index < 1 or index > len(liste_complete):
            await interaction.followup.send(f"❌ Numéro invalide. Tu as {len(liste_complete)} personnage(s).", ephemeral=True)
            return

        perso = liste_complete[index - 1]
        embed = build_personnage_embed(perso, user=interaction.user)

        # Envoie avec image locale si dispo
        try:
            image_path = perso["image"]
            image_filename = os.path.basename(image_path)
            with open(image_path, "rb") as f:
                file = discord.File(f, filename=image_filename)
                await interaction.followup.send(embed=embed, file=file)
        except Exception as e:
            await interaction.followup.send(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(Perso(bot))

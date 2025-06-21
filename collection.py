import discord
from discord import app_commands
from discord.ext import commands
from collections import Counter

from personnage import get_par_rarete, RARETES
from storage import get_inventaire

class Collection(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="collection", description="Affiche ta collection complète de personnages.")
    async def collection(self, interaction: discord.Interaction):
        await interaction.response.defer()
        user = interaction.user
        guild_id = interaction.guild.id
        user_id = user.id

        # Obtenir les personnages possédés
        inventaire = get_inventaire(guild_id, user_id)
        perso_possedes = inventaire.get("personnages", [])
        compteur = Counter(perso_possedes)

        index = 0

        def build_embed(rarete: str) -> discord.Embed:
            personnages = get_par_rarete(rarete)
            lignes = []

            for i, perso in enumerate(personnages, 1):
                nom = perso["nom"]
                quantite = compteur.get(nom, 0)
                affichage = f"{i}. {nom} x{quantite}" if quantite > 0 else f"{i}. Inconnu"
                lignes.append(affichage)

            # Double colonne
            moitié = (len(lignes) + 1) // 2
            gauche = lignes[:moitié]
            droite = lignes[moitié:]
            texte = ""

            for i in range(len(gauche)):
                g = gauche[i]
                d = droite[i] if i < len(droite) else ""
                texte += f"{g:<40} {d}\n"

            embed = discord.Embed(
                title=f"📚 Collection de {user.display_name} — {rarete}",
                description=f"```{texte}```",
                color=discord.Color.blue()
            )
            return embed

        message = await interaction.followup.send(embed=build_embed(RARETES[index]))

        class CollectionView(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=60)

            @discord.ui.button(label="◀️", style=discord.ButtonStyle.secondary)
            async def back(self, interaction_button: discord.Interaction, button: discord.ui.Button):
                nonlocal index
                index = (index - 1) % len(RARETES)
                await message.edit(embed=build_embed(RARETES[index]))
                await interaction_button.response.defer()

            @discord.ui.button(label="▶️", style=discord.ButtonStyle.secondary)
            async def forward(self, interaction_button: discord.Interaction, button: discord.ui.Button):
                nonlocal index
                index = (index + 1) % len(RARETES)
                await message.edit(embed=build_embed(RARETES[index]))
                await interaction_button.response.defer()

        await message.edit(view=CollectionView())

async def setup(bot):
    await bot.add_cog(Collection(bot))

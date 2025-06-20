import discord
from discord import app_commands
from discord.ext import commands

class Shop(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="shop", description="Affiche la boutique de GotValis (actuellement vide).")
    async def shop(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            embed=discord.Embed(
                title="🛒 Boutique de GotValis",
                description="La boutique est actuellement en préparation.\nRevenez plus tard pour consulter les offres disponibles.",
                color=discord.Color.dark_red()
            ),
            ephemeral=True
        )

async def setup(bot):
    await bot.add_cog(Shop(bot))

import discord
import random
from discord import app_commands
from discord.ext import commands

class Kiss(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.kiss_gifs = [
            "https://media.tenor.com/xyz1.gif",
            "https://media.tenor.com/xyz2.gif",
            "https://media.tenor.com/xyz3.gif"
            # ➕ Tu pourras ajouter autant de GIFs que tu veux ici
        ]

    @app_commands.command(name="kiss", description="Embrasse un autre utilisateur 💋")
    async def kiss(self, interaction: discord.Interaction, membre: discord.Member):
        if membre.bot:
            await interaction.response.send_message("🤖 Les protocoles GotValis interdisent les interactions affectueuses avec les unités synthétiques.", ephemeral=True)
            return

        gif = random.choice(self.kiss_gifs)
        embed = discord.Embed(
            title="💋 GotValis : transfert d'amour détecté",
            description=f"{interaction.user.mention} embrasse {membre.mention}... protocole affectif enclenché.",
            color=discord.Color.pink()
        )
        embed.set_image(url=gif)

        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(Kiss(bot))

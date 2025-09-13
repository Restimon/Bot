# cogs/social/pat.py
import discord
import random
from discord import app_commands
from discord.ext import commands

PAT_GIFS = [
    "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExdGlyYWx0ZHFkbWlwbWMwM25uN2hhMzAxOGMycWljeXU4bndybzhtNyZlcD12MV9naWZzX3NlYXJjaCZjdD1n/L2z7dnOduqEow/giphy.gif",
    "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExdGlyYWx0ZHFkbWlwbWMwM25uN2hhMzAxOGMycWljeXU4bndybzhtNyZlcD12MV9naWZzX3NlYXJjaCZjdD1n/5tmRHwTlHAA9WkVxTU/giphy.gif",
    "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExdGlyYWx0ZHFkbWlwbWMwM25uN2hhMzAxOGMycWljeXU4bndybzhtNyZlcD12MV9naWZzX3NlYXJjaCZjdD1n/L2z7dnOduqEow/giphy.gif",
    "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExdGlyYWx0ZHFkbWlwbWMwM25uN2hhMzAxOGMycWljeXU4bndybzhtNyZlcD12MV9naWZzX3NlYXJjaCZjdD1n/ye7OTQgwmVuVy/giphy.gif",
    "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExdGlyYWx0ZHFkbWlwbWMwM25uN2hhMzAxOGMycWljeXU4bndybzhtNyZlcD12MV9naWZzX3NlYXJjaCZjdD1n/109ltuoSQT212w/giphy.gif",
    "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExdGlyYWx0ZHFkbWlwbWMwM25uN2hhMzAxOGMycWljeXU4bndybzhtNyZlcD12MV9naWZzX3NlYXJjaCZjdD1n/HuGyHR9KnLU4M/giphy.gif",
    "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExdGlyYWx0ZHFkbWlwbWMwM25uN2hhMzAxOGMycWljeXU4bndybzhtNyZlcD12MV9naWZzX3NlYXJjaCZjdD1n/X12bFJrWSGTqlhlztZ/giphy.gif",
    "https://media.giphy.com/media/v1.Y2lkPWVjZjA1ZTQ3b2Ixamlkc3ZveDQ5Y2lvNnZzbXp5c3Qwb3d2bjVwdGhjMnk3bjZodiZlcD12MV9naWZzX3NlYXJjaCZjdD1n/osYdfUptPqV0s/giphy.gif",
    "https://media.giphy.com/media/v1.Y2lkPWVjZjA1ZTQ3b2Ixamlkc3ZveDQ5Y2lvNnZzbXp5c3Qwb3d2bjVwdGhjMnk3bjZodiZlcD12MV9naWZzX3NlYXJjaCZjdD1n/QdL3gdDPyEVISx6Hxf/giphy.gif",
    "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExdGlyYWx0ZHFkbWlwbWMwM25uN2hhMzAxOGMycWljeXU4bndybzhtNyZlcD12MV9naWZzX3NlYXJjaCZjdD1n/wsUtKcUSHEhhBCyqtM/giphy.gif",
]

class PatCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="pat", description="Caresse gentiment quelqu’un")
    @app_commands.describe(target="La personne que tu veux tapoter")
    async def pat(self, interaction: discord.Interaction, target: discord.Member):
        if target.bot:
            await interaction.response.send_message("🤖 Les bots n’ont pas besoin de caresses... mais merci ?", ephemeral=True)
            return
        embed = discord.Embed(
            title="GotValis : interaction douce détectée 🖐️",
            description=f"{interaction.user.mention} caresse {target.mention} avec bienveillance.",
            color=discord.Color.blurple(),
        )
        embed.set_image(url=random.choice(PAT_GIFS))
        await interaction.response.send_message(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(PatCog(bot))

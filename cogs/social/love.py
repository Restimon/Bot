# cogs/social/love.py
import discord
import random
from discord import app_commands
from discord.ext import commands

LOVE_GIFS = [
    "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExOG5keGR3ZzI1dm1zOWo5eW1iYWgwdGE1ajZ6dGI0MjVva2M2b3ZoeiZlcD12MV9naWZzX3NlYXJjaCZjdD1n/c76IJLufpNwSULPk77/giphy.gif",
    "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExOG5keGR3ZzI1dm1zOWo5eW1iYWgwdGE1ajZ6dGI0MjVva2M2b3ZoeiZlcD12MV9naWZzX3NlYXJjaCZjdD1n/sh11BmCf8HY8F0c5GN/giphy.gif",
    "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExOG5keGR3ZzI1dm1zOWo5eW1iYWgwdGE1ajZ6dGI0MjVva2M2b3ZoeiZlcD12MV9naWZzX3NlYXJjaCZjdD1n/l4pTdcifPZLpDjL1e/giphy.gif",
    "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExOG5keGR3ZzI1dm1zOWo5eW1iYWgwdGE1ajZ6dGI0MjVva2M2b3ZoeiZlcD12MV9naWZzX3NlYXJjaCZjdD1n/3CCXHZWV6F6O9VQ7FL/giphy.gif",
    "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExOG5keGR3ZzI1dm1zOWo5eW1iYWgwdGE1ajZ6dGI0MjVva2M2b3ZoeiZlcD12MV9naWZzX3NlYXJjaCZjdD1n/xYGnFm4mVcMxYIVq3v/giphy.gif",
    "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExOG5keGR3ZzI1dm1zOWo5eW1iYWgwdGE1ajZ6dGI0MjVva2M2b3ZoeiZlcD12MV9naWZzX3NlYXJjaCZjdD1n/M90mJvfWfd5mbUuULX/giphy.gif",
    "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExOG5keGR3ZzI1dm1zOWo5eW1iYWgwdGE1ajZ6dGI0MjVva2M2b3ZoeiZlcD12MV9naWZzX3NlYXJjaCZjdD1n/gDfteqLchLcRTtjAD7/giphy.gif",
    "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExOG5keGR3ZzI1dm1zOWo5eW1iYWgwdGE1ajZ6dGI0MjVva2M2b3ZoeiZlcD12MV9naWZzX3NlYXJjaCZjdD1n/7y4Nc95399hsr24oYc/giphy.gif",
    "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExOG5keGR3ZzI1dm1zOWo5eW1iYWgwdGE1ajZ6dGI0MjVva2M2b3ZoeiZlcD12MV9naWZzX3NlYXJjaCZjdD1n/1hqb8LwPS2xCNCpWH8/giphy.gif",
    "https://media.giphy.com/media/v1.Y2lkPWVjZjA1ZTQ3MWk1M2thOXE4eWp3b2s2cHlmYWl6bHI0eDBjeG5zOGR2Mjd6cDdkNiZlcD12MV9naWZzX3NlYXJjaCZjdD1n/iGqP4DYXe4zVJbCY5N/giphy.gif",
    "https://media.giphy.com/media/v1.Y2lkPWVjZjA1ZTQ3dWMxdmlheTAwbjF6N3JxbmY5MmlhZGcyYXpxM3h3ZG5jd2wzcnJxOCZlcD12MV9naWZzX3NlYXJjaCZjdD1n/l6b1QYVQ8qLhefyLeg/giphy.gif",
    "https://media.giphy.com/media/v1.Y2lkPWVjZjA1ZTQ3MGp3d3gyc3BmNnI3ZWR1cHh0dDMzODI2bTFuMmVhNHFkcm5xdmZrZiZlcD12MV9naWZzX3NlYXJjaCZjdD1n/eocJr1HAyDbTDGgyFG/giphy.gif",
]

class LoveCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="love", description="Envoie de l’amour à un membre ❤️.")
    @app_commands.describe(user="Le membre que vous voulez couvrir d’amour.")
    async def love(self, interaction: discord.Interaction, user: discord.Member):
        await interaction.response.defer(thinking=True)
        embed = discord.Embed(
            title="GotValis : transfert d’amour détecté ❤️",
            description=f"{interaction.user.mention} envoie tout son amour à {user.mention} ❤️",
            color=discord.Color.magenta(),
        )
        embed.set_image(url=random.choice(LOVE_GIFS))
        await interaction.followup.send(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(LoveCog(bot))

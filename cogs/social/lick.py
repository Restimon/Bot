# cogs/social/lick.py
import discord
import random
from discord import app_commands
from discord.ext import commands

LICK_GIFS = [
    "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExcWM1ZXZ6cnUxdHlwcmY2ZGhndm5nNThkYTV4Z3E5YW91cHp4b2N3OCZlcD12MV9naWZzX3NlYXJjaCZjdD1n/26gspipWnu59srmM0/giphy.gif",
    "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExbzNjM2FjeWxwMXdiOTE3OHRvdThhcjkwMHNhZ2Jzdm10anJ4c2xpdCZlcD12MV9naWZzX3NlYXJjaCZjdD1n/8tWFiyF4thmIqgDD0q/giphy.gif",
    "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExbzNjM2FjeWxwMXdiOTE3OHRvdThhcjkwMHNhZ2Jzdm10anJ4c2xpdCZlcD12MV9naWZzX3NlYXJjaCZjdD1n/JxvQxRIHGZyDK/giphy.gif",
    "https://media.giphy.com/media/v1.Y2lkPWVjZjA1ZTQ3aDBkMDdmMGN6dzR5bzJhenA3d2U3NGhya3RiaXd5NGs5ZTVhdGtkeCZlcD12MV9naWZzX3NlYXJjaCZjdD1n/MuAlxQqMaB7D8p8aDn/giphy.gif",
    "https://media.giphy.com/media/v1.Y2lkPWVjZjA1ZTQ3NHlnZGFzajVka3BuanU5ZDN5dzYxZDlnajA2Y3N2eW4weW50Zm5oZCZlcD12MV9naWZzX3NlYXJjaCZjdD1n/q8TEi7UTxas92/giphy.gif",
    "https://media.giphy.com/media/v1.Y2lkPWVjZjA1ZTQ3bGNnMmxoYzltM3lrNzJsaXdrbWFsbWxod29mbHhocmN1Zm1kajFlbiZlcD12MV9naWZzX3NlYXJjaCZjdD1n/LQHCGkKx2dhHW/giphy.gif",
    "https://media.giphy.com/media/v1.Y2lkPWVjZjA1ZTQ3OXFoazdnaGp6MDdjcmVkbDQ0bHY4OHg0YXl0ajZzeHRtZjRlZHVtbCZlcD12MV9naWZzX3NlYXJjaCZjdD1n/A8ReUjJdMCNOM/giphy.gif",
    "https://media.giphy.com/media/v1.Y2lkPWVjZjA1ZTQ3ZWg5dDNtMWxxM2VmdXdxMmg4MmU2eTFteDgxbXJvbzhsbXM1dHNreCZlcD12MV9naWZzX3NlYXJjaCZjdD1n/BvW6ozGG1jrYzTtKmy/giphy.gif",
    "https://media.giphy.com/media/v1.Y2lkPWVjZjA1ZTQ3cm9oNHdpMjh5bWgybWliZTd3dWFlZGlpM29xcTQxbGJ1OGR6dGR4byZlcD12MV9naWZzX3NlYXJjaCZjdD1n/jMGR2w5bYmO9dBZMtz/giphy.gif",
]

class LickCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="lick", description="Lèche un membre.")
    @app_commands.describe(user="Le membre que vous voulez lécher.")
    async def lick(self, interaction: discord.Interaction, user: discord.Member):
        await interaction.response.defer(thinking=True)
        embed = discord.Embed(
            title="GotValis : impact d'une léchouille 👅",
            description=f"{interaction.user.mention} fais une léchouille {user.mention}... 🍭",
            color=discord.Color.pink(),
        )
        embed.set_image(url=random.choice(LICK_GIFS))
        await interaction.followup.send(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(LickCog(bot))

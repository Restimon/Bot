import discord
import random
from discord import app_commands
from discord.ext import commands

# GIFs en variable globale (hors classe)
KISS_GIFS = [
    "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExaHEwNmh0OW5zZjd4bzRocDdtb244anBzNWdyN3RqaGd3aTN2aThnMSZlcD12MV9naWZzX3NlYXJjaCZjdD1n/G3va31oEEnIkM/giphy.gif",
    "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExaHEwNmh0OW5zZjd4bzRocDdtb244anBzNWdyN3RqaGd3aTN2aThnMSZlcD12MV9naWZzX3NlYXJjaCZjdD1n/wOtkVwroA6yzK/giphy.gif",
    "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExaHEwNmh0OW5zZjd4bzRocDdtb244anBzNWdyN3RqaGd3aTN2aThnMSZlcD12MV9naWZzX3NlYXJjaCZjdD1n/MQVpBqASxSlFu/giphy.gif",
    "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExaHEwNmh0OW5zZjd4bzRocDdtb244anBzNWdyN3RqaGd3aTN2aThnMSZlcD12MV9naWZzX3NlYXJjaCZjdD1n/f82EqBTeCEgcU/giphy.gif",
    "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExaHEwNmh0OW5zZjd4bzRocDdtb244anBzNWdyN3RqaGd3aTN2aThnMSZlcD12MV9naWZzX3NlYXJjaCZjdD1n/nyGFcsP0kAobm/giphy.gif",
    "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExaHEwNmh0OW5zZjd4bzRocDdtb244anBzNWdyN3RqaGd3aTN2aThnMSZlcD12MV9naWZzX3NlYXJjaCZjdD1n/FqBTvSNjNzeZG/giphy.gif",
    "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExaHEwNmh0OW5zZjd4bzRocDdtb244anBzNWdyN3RqaGd3aTN2aThnMSZlcD12MV9naWZzX3NlYXJjaCZjdD1n/Ka2NAhphLdqXC/giphy.gif",
    "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExaHEwNmh0OW5zZjd4bzRocDdtb244anBzNWdyN3RqaGd3aTN2aThnMSZlcD12MV9naWZzX3NlYXJjaCZjdD1n/kU586ictpGb0Q/giphy.gif",
    "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExaHEwNmh0OW5zZjd4bzRocDdtb244anBzNWdyN3RqaGd3aTN2aThnMSZlcD12MV9naWZzX3NlYXJjaCZjdD1n/QGc8RgRvMonFm/giphy.gif",
    "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExaHEwNmh0OW5zZjd4bzRocDdtb244anBzNWdyN3RqaGd3aTN2aThnMSZlcD12MV9naWZzX3NlYXJjaCZjdD1n/11rWoZNpAKw8w/giphy.gif",
    "https://media.giphy.com/media/v1.Y2lkPWVjZjA1ZTQ3MWJmazF6djBzNnN0dHJlcmpvYWpybXVkcjNubWowb2loeDNyOXExMiZlcD12MV9naWZzX3NlYXJjaCZjdD1n/pwZ2TLSTouCQw/giphy.gif",
    "https://media.giphy.com/media/v1.Y2lkPWVjZjA1ZTQ3dWhlemMwMjNhMnVvOGp4M2htNHN5Z2VrZG9lajA2MDlkZmoyaWE0MSZlcD12MV9naWZzX3NlYXJjaCZjdD1n/ZL0G3c9BDX9ja/giphy.gif",
    "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExaGJubzRqcnV4ZTJwNDY5Z3NheGg2Y3g0cTNtNHhxbXVlNjhyeHphayZlcD12MV9naWZzX3NlYXJjaCZjdD1n/3ddeHaOqi7UoE/giphy.gif"
]

class Kiss(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

def register_kiss_command(bot):
    @bot.tree.command(name="kiss", description="Fais un bisou à quelqu'un")
    @app_commands.describe(target="La personne que tu veux embrasser")
    async def kiss(interaction: discord.Interaction, target: discord.Member):
        if target.bot:
            return await interaction.response.send_message(
                "🤖 Les bots n’ont pas besoin d’amour numérique…", ephemeral=True
            )

        if interaction.user.id == target.id:
            return await interaction.response.send_message(
                "💋 Tu ne peux pas t’embrasser toi-même…", ephemeral=True
            )

        gif_url = random.choice(KISS_GIFS)
        embed = discord.Embed(
            title="GotValis : échange d'amour détecté 💋",
            description=f"{interaction.user.mention} embrasse {target.mention} avec amour.",
            color=discord.Color.red()
        )
        embed.set_image(url=gif_url)
        await interaction.response.send_message(embed=embed)

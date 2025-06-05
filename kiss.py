import discord
import random
from discord import app_commands
from discord.ext import commands

class Kiss(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.kiss_gifs = [
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
            description=f"{interaction.user.mention} embrasse {membre.mention} avec plein d'amour.",
            color=discord.Color.pink()
        )
        embed.set_image(url=gif)

        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(Kiss(bot))

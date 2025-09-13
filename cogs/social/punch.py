# cogs/social/punch.py
# Version cosmétique (aucun dégât pour éviter les imports externes).
import discord
import random
from discord import app_commands
from discord.ext import commands

PUNCH_GIFS = [
    "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExdTB2eXk4cDRmd3kwdXpxeHVxbmYyMWY2ZzU1N3VkMzAybGF3bW5weiZlcD12MV9naWZzX3NlYXJjaCZjdD1n/wiaoWlW17fqIo/giphy.gif",
    "https://media.giphy.com/media/v1.Y2lkPWVjZjA1ZTQ3MDE3czhhbnowcXl0cjd0dnFvd2FkMW9rc2RlamJ6eHNyN3ZpczhneSZlcD12MV9naWZzX3NlYXJjaCZjdD1n/11HeubLHnQJSAU/giphy.gif",
    "https://media.giphy.com/media/v1.Y2lkPWVjZjA1ZTQ3anFrbTdsNnh6ZXNmM3BkeG1wNXA5ZWJ0Y2tmeW5iMW82Ym90YXNweCZlcD12MV9naWZzX3NlYXJjaCZjdD1n/oNEJo2QnbZUkPNyv4F/giphy.gif",
    "https://media.giphy.com/media/v1.Y2lkPWVjZjA1ZTQ3eXVrOXQwdWpnN3ZiMDRjNHB2MWl2amJyeXVpMmVicWV3N2cyd2U0dSZlcD12MV9naWZzX3NlYXJjaCZjdD1n/NY3tXwOBUwQYq7lbXx/giphy.gif",
    "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExdHY2ZWdibDQ5eDQ1N2RheXFtNjB2cHVwaWJ3aWVkaHhxbzBoZDVhaCZlcD12MV9naWZzX3NlYXJjaCZjdD1n/NuiEoMDbstN0J2KAiH/giphy.gif",
    "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExdHY2ZWdibDQ5eDQ1N2RheXFtNjB2cHVwaWJ3aWVkaHhxbzBoZDVhaCZlcD12MV9naWZzX3NlYXJjaCZjdD1n/uLklwTDvckBW27wqmU/giphy.gif",
    "https://media.giphy.com/media/v1.Y2lkPWVjZjA1ZTQ3NTUzazRhbWF1Ympxem0wZXNqbG8zN3FpMXgxZnppNDE4YzMzMWxsMyZlcD12MV9naWZzX3NlYXJjaCZjdD1n/zkpLdM8u8aLabkR6m9/giphy.gif",
    "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExYXk3dXc3YTdud2w0bndxZTRjaDljMmIyM2M2czRjdHg0NWpmemZsdCZlcD12MV9naWZzX3NlYXJjaCZjdD1n/xUNd9HZq1itMkiK652/giphy.gif",
]

PUNCH_CRIT_GIFS = [
    "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExaDVzdXAzbG9saHR5ZTJwd2piNmVna2R0dTlhenluYXJld3R5MWtsdSZlcD12MV9naWZzX3NlYXJjaCZjdD1n/qPzZQtsv21zjy/giphy.gif",
    "https://media.giphy.com/media/v1.Y2lkPWVjZjA1ZTQ3MzFyeXY0ZnNqZWh3eW95MnA2MWJwbnA1eHE0a3g0bmptNHgxdmZpNyZlcD12MV9naWZzX3NlYXJjaCZjdD1n/g0tSbN7zqTwwpYqQge/giphy.gif",
    "https://media.giphy.com/media/o2TqK6vEzhp96/giphy.gif",
]

class PunchCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="punch", description="Donne un coup de poing à quelqu’un !")
    @app_commands.describe(target="La personne que tu veux frapper")
    async def punch(self, interaction: discord.Interaction, target: discord.Member):
        if target.bot:
            await interaction.response.send_message("🤖 Frapper un bot ? Il n’a pas de visage...", ephemeral=True)
            return

        # 1% d’animation “spéciale”
        if random.random() < 0.01:
            gif_url = random.choice(PUNCH_CRIT_GIFS)
            embed = discord.Embed(
                title="GotValis : coup significatif détecté ⚠️",
                description=f"{interaction.user.mention} a frappé {target.mention}. **Coup mémorable !**",
                color=discord.Color.red(),
            )
        else:
            gif_url = random.choice(PUNCH_GIFS)
            embed = discord.Embed(
                title="GotValis : impact physique détecté 👊",
                description=f"{interaction.user.mention} donne un coup de poing à {target.mention}.",
                color=discord.Color.orange(),
            )

        embed.set_image(url=gif_url)
        await interaction.response.send_message(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(PunchCog(bot))

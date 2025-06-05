import discord
import random
from discord import app_commands
from storage import hp
from utils import handle_death

# GIFs pour coups normaux (99%)
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

# GIFs spéciaux pour le coup qui fait 1 dégât (1%)
PUNCH_CRIT_GIFS = [
    "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExaDVzdXAzbG9saHR5ZTJwd2piNmVna2R0dTlhenluYXJld3R5MWtsdSZlcD12MV9naWZzX3NlYXJjaCZjdD1n/qPzZQtsv21zjy/giphy.gif",
    "https://media.giphy.com/media/v1.Y2lkPWVjZjA1ZTQ3MzFyeXY0ZnNqZWh3eW95MnA2MWJwbnA1eHE0a3g0bmptNHgxdmZpNyZlcD12MV9naWZzX3NlYXJjaCZjdD1n/g0tSbN7zqTwwpYqQge/giphy.gif",
    "https://media.giphy.com/media/o2TqK6vEzhp96/giphy.gif",
    # Ajoute ici d'autres GIFs épiques pour coup spécial
]

def register_punch_command(bot):
    @bot.tree.command(name="punch", description="Donne un coup de poing à quelqu’un !")
    @app_commands.describe(target="La personne que tu veux frapper")
    async def punch(interaction: discord.Interaction, target: discord.Member):
        if target.bot:
            return await interaction.response.send_message(
                "🤖 Frapper un bot ? Il n’a pas de visage...", ephemeral=True
            )

        author = interaction.user
        target_id = str(target.id)
        guild_id = str(interaction.guild.id)

        # 1 % de chance de dégâts
        if random.random() < 0.01:
            gif_url = random.choice(PUNCH_CRIT_GIFS)
            before = hp[guild_id].get(target_id, 100)
            after = max(before - 1, 0)
            hp[guild_id][target_id] = after
            sauvegarder()

            if after == 0:
                handle_death(guild_id, target_id, str(author.id))

            embed = discord.Embed(
                title="GotValis : coup significatif détecté ⚠️",
                description=f"{author.mention} a frappé {target.mention}. **1 dégât infligé !** ({before} → {after})",
                color=discord.Color.red()
            )
        else:
            gif_url = random.choice(PUNCH_GIFS)
            embed = discord.Embed(
                title="GotValis : impact physique détecté 👊",
                description=f"{author.mention} donne un coup de poing à {target.mention}.",
                color=discord.Color.orange()
            )

        embed.set_image(url=gif_url)
        await interaction.response.send_message(embed=embed)

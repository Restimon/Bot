import discord
import random
from discord import app_commands
from storage import hp, sauvegarder
from utils import handle_death

# GIFs pour coups normaux (99%)
PUNCH_GIFS = [
    "https://media.giphy.com/media/l0MYt5jPR6QX5pnqM/giphy.gif",
    "https://media.giphy.com/media/xUNd9HZq1itMkiK652/giphy.gif",
    "https://media.giphy.com/media/13HXKG2qk3xjIY/giphy.gif",
    "https://media.giphy.com/media/5t9wJjyHAOxvnDnH3X/giphy.gif",
]

# GIFs spéciaux pour le coup qui fait 1 dégât (1%)
PUNCH_CRIT_GIFS = [
    "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExaDVzdXAzbG9saHR5ZTJwd2piNmVna2R0dTlhenluYXJld3R5MWtsdSZlcD12MV9naWZzX3NlYXJjaCZjdD1n/qPzZQtsv21zjy/giphy.gif",
    "https://media.giphy.com/media/v1.Y2lkPWVjZjA1ZTQ3MzFyeXY0ZnNqZWh3eW95MnA2MWJwbnA1eHE0a3g0bmptNHgxdmZpNyZlcD12MV9naWZzX3NlYXJjaCZjdD1n/g0tSbN7zqTwwpYqQge/giphy.gif",
    "https://media.giphy.com/media/l2JJKs3I69qfaQleE/giphy.gif",
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

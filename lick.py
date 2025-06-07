import discord
import random
from discord import app_commands

# Une petite liste de GIFs (tu peux en rajouter autant que tu veux)
LICK_GIFS = [
    "https://media.tenor.com/ItxDWyVZKfgAAAAC/anime-lick.gif",
    "https://media.tenor.com/BuVr_f0G_RAAAAAC/lick-anime.gif",
    "https://media.tenor.com/MGE2wNRDZLEAAAAC/anime-lick-lick.gif",
    "https://media.tenor.com/m-7xE3E6qFMAAAAC/lick-anime.gif"
]

def register_lick_command(bot):
    @bot.tree.command(name="lick", description="Lèche un membre.")
    @app_commands.describe(user="Le membre que vous voulez lécher.")
    async def lick_slash(interaction: discord.Interaction, user: discord.Member):

        await interaction.response.defer(thinking=True)

        author_mention = interaction.user.mention
        target_mention = user.mention

        gif_url = random.choice(LICK_GIFS)

        # Prépare l'embed
        embed = discord.Embed(
            title="GotValis : impact d'une lechouille 👅",
            description=f"{author_mention} lèche {target_mention}... 🍭",
            color=discord.Color.pink()
        )
        embed.set_image(url=gif_url)

        await interaction.followup.send(embed=embed)

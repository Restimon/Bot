import discord
import random
from discord import app_commands

# Liste de GIFs pour la morsure (tu peux en rajouter)
BITE_GIFS = [
    "https://media.tenor.com/mrvbxXNswb4AAAAC/anime-bite.gif",
    "https://media.tenor.com/9-ZO-1jB4uYAAAAC/anime-bite.gif",
    "https://media.tenor.com/l_El4-dx0D8AAAAC/anime-bite.gif",
    "https://media.tenor.com/HkWwPBWbPTwAAAAC/anime-bite-anime.gif"
]

def register_bite_command(bot):
    @bot.tree.command(name="bite", description="Mord un membre.")
    @app_commands.describe(user="Le membre que vous voulez mordre.")
    async def bite_slash(interaction: discord.Interaction, user: discord.Member):

        await interaction.response.defer(thinking=True)

        author_mention = interaction.user.mention
        target_mention = user.mention

        gif_url = random.choice(BITE_GIFS)

        # Prépare l'embed
        embed = discord.Embed(
            title="GotValis : morsure détecté 👄 ",
            description=f"{author_mention} mord tendrement {target_mention} ! 👄",
            color=discord.Color.red()
        )
        embed.set_image(url=gif_url)

        await interaction.followup.send(embed=embed)

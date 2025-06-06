import discord
import random
from discord import app_commands

# Liste de GIFs pour la morsure (tu peux en rajouter)
BITE_GIFS = [
    "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExMWI4emVzaGJpd3FkbnA4cmZhNDBuOXBqcHM1OWtoZGZpeXY5ZDB6cSZlcD12MV9naWZzX3NlYXJjaCZjdD1n/lrMUMn9lnpaJDsvP0u/giphy.gif",
    "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExMWI4emVzaGJpd3FkbnA4cmZhNDBuOXBqcHM1OWtoZGZpeXY5ZDB6cSZlcD12MV9naWZzX3NlYXJjaCZjdD1n/YW3obh7zZ4Rj2/giphy.gif",
    "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExMWI4emVzaGJpd3FkbnA4cmZhNDBuOXBqcHM1OWtoZGZpeXY5ZDB6cSZlcD12MV9naWZzX3NlYXJjaCZjdD1n/69159EHgBoG08/giphy.gif",
    "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExNmFodzNlMzlpc3ppYXp1Z25kM3QzeDBheHhjOHc0OGY5MjhnZ213eCZlcD12MV9naWZzX3NlYXJjaCZjdD1n/U1wMHRq7bnuInYaVlB/giphy.gif",
    "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExNmFodzNlMzlpc3ppYXp1Z25kM3QzeDBheHhjOHc0OGY5MjhnZ213eCZlcD12MV9naWZzX3NlYXJjaCZjdD1n/OqQOwXiCyJAmA/giphy.gif",
    "https://media.giphy.com/media/v1.Y2lkPWVjZjA1ZTQ3YTRpaWFjeng2M3FxYXVvanl4eW1rb3FmOGVsdDUzdG13cmEwM3MwMCZlcD12MV9naWZzX3NlYXJjaCZjdD1n/7rAYDoEhokWEpk0vw2/giphy.gif",
    "https://media.giphy.com/media/v1.Y2lkPWVjZjA1ZTQ3ZzlhMnVvY2tyMXFmMWc2djZzNmphOGhzZDc5em9jYnNhYXV1dDFvNSZlcD12MV9naWZzX3NlYXJjaCZjdD1n/ixoMvaJ2NhFgouq9aY/giphy.gif",
    "https://media.giphy.com/media/v1.Y2lkPWVjZjA1ZTQ3ZzlhMnVvY2tyMXFmMWc2djZzNmphOGhzZDc5em9jYnNhYXV1dDFvNSZlcD12MV9naWZzX3NlYXJjaCZjdD1n/cDX2QcwxcV2evBGn6q/giphy.gif",
    "https://media.giphy.com/media/v1.Y2lkPWVjZjA1ZTQ3Y2I5Yjl4a2RpeDhjdmxoYmZleHd5cHc4MnVxZGZ4aWNwdWJiMXFzYiZlcD12MV9naWZzX3NlYXJjaCZjdD1n/F0vhUJJkVFXPCl2jJu/giphy.gif",
    "https://media.giphy.com/media/v1.Y2lkPWVjZjA1ZTQ3Y25ycjU2b3dicWo2OW42NjN3b2JxYXFodGgzdGtlcW84eXAxaTZkciZlcD12MV9naWZzX3NlYXJjaCZjdD1n/idNoM77zIzcWP4Lbmz/giphy.gif",
    "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExNmFodzNlMzlpc3ppYXp1Z25kM3QzeDBheHhjOHc0OGY5MjhnZ213eCZlcD12MV9naWZzX3NlYXJjaCZjdD1n/sXR1Lyui5SEmI/giphy.gif",
    "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExNmFodzNlMzlpc3ppYXp1Z25kM3QzeDBheHhjOHc0OGY5MjhnZ213eCZlcD12MV9naWZzX3NlYXJjaCZjdD1n/LO9Y9hKLupIwko9IVd/giphy.gif",
    "https://media.giphy.com/media/v1.Y2lkPWVjZjA1ZTQ3YTk5cXVqbXczYzh2dzBuanFmaDM1a21xb3Y1YWN2a2VtZmxocnQzcSZlcD12MV9naWZzX3NlYXJjaCZjdD1n/q8TEi7UTxas92/giphy.gif"
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

import discord
import random
from discord import app_commands

# Liste des liens GIFs à compléter/modifier par toi
HUG_GIFS = [
    "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExbzFrZmNjOTd6bWRnOGQ5bjUzMHZibGpvbnV0Z2NwNTBsbGhrN2pidiZlcD12MV9naWZzX3NlYXJjaCZjdD1n/9d3LQ6TdV2Flo8ODTU/giphy.gif",
    "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExbzFrZmNjOTd6bWRnOGQ5bjUzMHZibGpvbnV0Z2NwNTBsbGhrN2pidiZlcD12MV9naWZzX3NlYXJjaCZjdD1n/xT39CXg70nNS0MFNLy/giphy.gif",
    "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExbzFrZmNjOTd6bWRnOGQ5bjUzMHZibGpvbnV0Z2NwNTBsbGhrN2pidiZlcD12MV9naWZzX3NlYXJjaCZjdD1n/Vz58J8shFW6BvqnYTm/giphy.gif",
    "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExbzFrZmNjOTd6bWRnOGQ5bjUzMHZibGpvbnV0Z2NwNTBsbGhrN2pidiZlcD12MV9naWZzX3NlYXJjaCZjdD1n/KG5oq4vesf9r8JbBEN/giphy.gif",
    "https://media.giphy.com/media/v1.Y2lkPWVjZjA1ZTQ3YjJmazlwbDRkZzc2YzR3MnlqczczNTc4YWl6ODY4d2t0em80dnJqOSZlcD12MV9naWZzX3NlYXJjaCZjdD1n/3AKPHmFKETX4foqk3q/giphy.gif",
    "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExb2xlMnlubXBpbDdmcjZpNmNtN2cwNjQxb3llZGpwOWc1MnN4YWk5dyZlcD12MV9naWZzX3NlYXJjaCZjdD1n/49mdjsMrH7oze/giphy.gif",
    "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExb2xlMnlubXBpbDdmcjZpNmNtN2cwNjQxb3llZGpwOWc1MnN4YWk5dyZlcD12MV9naWZzX3NlYXJjaCZjdD1n/svXXBgduBsJ1u/giphy.gif",
    "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExb2xlMnlubXBpbDdmcjZpNmNtN2cwNjQxb3llZGpwOWc1MnN4YWk5dyZlcD12MV9naWZzX3NlYXJjaCZjdD1n/od5H3PmEG5EVq/giphy.gif",
    "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExb2xlMnlubXBpbDdmcjZpNmNtN2cwNjQxb3llZGpwOWc1MnN4YWk5dyZlcD12MV9naWZzX3NlYXJjaCZjdD1n/5eyhBKLvYhafu/giphy.gif",
    "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExb2xlMnlubXBpbDdmcjZpNmNtN2cwNjQxb3llZGpwOWc1MnN4YWk5dyZlcD12MV9naWZzX3NlYXJjaCZjdD1n/qscdhWs5o3yb6/giphy.gif",
    "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExb2xlMnlubXBpbDdmcjZpNmNtN2cwNjQxb3llZGpwOWc1MnN4YWk5dyZlcD12MV9naWZzX3NlYXJjaCZjdD1n/ZQN9jsRWp1M76/giphy.gif",
    "https://media.giphy.com/media/v1.Y2lkPWVjZjA1ZTQ3NzIwNXF5dXF1YXNhNjlrdHA5ZWFpMGVxeWdmeDEyYjgwdGhvNTBjcCZlcD12MV9naWZzX3NlYXJjaCZjdD1n/3bqtLDeiDtwhq/giphy.gif",
    "https://media.giphy.com/media/v1.Y2lkPWVjZjA1ZTQ3NzIwNXF5dXF1YXNhNjlrdHA5ZWFpMGVxeWdmeDEyYjgwdGhvNTBjcCZlcD12MV9naWZzX3NlYXJjaCZjdD1n/u9BxQbM5bxvwY/giphy.gif",
    "https://media.giphy.com/media/v1.Y2lkPWVjZjA1ZTQ3NzIwNXF5dXF1YXNhNjlrdHA5ZWFpMGVxeWdmeDEyYjgwdGhvNTBjcCZlcD12MV9naWZzX3NlYXJjaCZjdD1n/LIqFOpO9Qh0uA/giphy.gif",
    "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExb2xlMnlubXBpbDdmcjZpNmNtN2cwNjQxb3llZGpwOWc1MnN4YWk5dyZlcD12MV9naWZzX3NlYXJjaCZjdD1n/kvKFM3UWg2P04/giphy.gif",
    # ajoute tes propres liens ici
]

def register_hug_command(bot):
    @bot.tree.command(name="hug", description="Fais un câlin à quelqu'un")
    @app_commands.describe(target="La personne que tu veux câliner")
    async def hug(interaction: discord.Interaction, target: discord.Member):
        if target.bot:
            return await interaction.response.send_message(
                "🤖 Les bots n’ont pas besoin de câlins... sauf si ?", ephemeral=True
            )

        gif_url = random.choice(HUG_GIFS)
        embed = discord.Embed(
            title="GotValis : transfert d’affection détecté 💞",
            description=f"{interaction.user.mention} fait un câlin à {target.mention} !",
            color=discord.Color.pink()
        )
        embed.set_image(url=gif_url)
        await interaction.response.send_message(embed=embed)

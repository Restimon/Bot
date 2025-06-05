import discord
import random
from discord import app_commands

SLAP_GIFS = [
    "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExYXk3dXc3YTdud2w0bndxZTRjaDljMmIyM2M2czRjdHg0NWpmemZsdCZlcD12MV9naWZzX3NlYXJjaCZjdD1n/vcShFtinE7YUo/giphy.gif",
    "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExYXk3dXc3YTdud2w0bndxZTRjaDljMmIyM2M2czRjdHg0NWpmemZsdCZlcD12MV9naWZzX3NlYXJjaCZjdD1n/Gf3AUz3eBNbTW/giphy.gif",
    "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExYXk3dXc3YTdud2w0bndxZTRjaDljMmIyM2M2czRjdHg0NWpmemZsdCZlcD12MV9naWZzX3NlYXJjaCZjdD1n/xUNd9HZq1itMkiK652/giphy.gif",
    "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExYXk3dXc3YTdud2w0bndxZTRjaDljMmIyM2M2czRjdHg0NWpmemZsdCZlcD12MV9naWZzX3NlYXJjaCZjdD1n/Gf3AUz3eBNbTW/giphy.gif",
    "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExYXk3dXc3YTdud2w0bndxZTRjaDljMmIyM2M2czRjdHg0NWpmemZsdCZlcD12MV9naWZzX3NlYXJjaCZjdD1n/aKuOVPfgxxIylvPrJx/giphy.gif",
    "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExYXk3dXc3YTdud2w0bndxZTRjaDljMmIyM2M2czRjdHg0NWpmemZsdCZlcD12MV9naWZzX3NlYXJjaCZjdD1n/3EAwGiruFDUQM/giphy.gif",
    "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExYXk3dXc3YTdud2w0bndxZTRjaDljMmIyM2M2czRjdHg0NWpmemZsdCZlcD12MV9naWZzX3NlYXJjaCZjdD1n/WvzGVdiVRNq8qtWPKu/giphy.gif",
    "https://media.giphy.com/media/v1.Y2lkPWVjZjA1ZTQ3YWFjeWk5anN1ejRtZXc4bGowZzh1bmxjOXNhNWlxODE0djk0bmgwYiZlcD12MV9naWZzX3NlYXJjaCZjdD1n/vh27cTDI0KWvbT8SCo/giphy.gif",
    "https://media.giphy.com/media/v1.Y2lkPWVjZjA1ZTQ3ZmlwZ2E4OGk0eDk3MzA1Ym82MnlrOTQ2dHJpbjJzYWx1bTVobXZuNiZlcD12MV9naWZzX3NlYXJjaCZjdD1n/UybfDsUxoJtl8e3xeV/giphy.gif",
    "https://media.giphy.com/media/v1.Y2lkPWVjZjA1ZTQ3YTNwcWo0aDl5cnI5cDR4bXA5bXBoMmlpcDF1djJyOG13Mmo2NXJqayZlcD12MV9naWZzX3NlYXJjaCZjdD1n/Qv7WFppXtkqkM/giphy.gif",
    # Ajoute d'autres GIFs ici si tu veux
]

def register_slap_command(bot):
    @bot.tree.command(name="slap", description="Mets une baffe à quelqu’un")
    @app_commands.describe(target="La personne que tu veux gifler")
    async def slap(interaction: discord.Interaction, target: discord.Member):
        if target.bot:
            return await interaction.response.send_message(
                "🤖 Les bots n’ont pas peur des baffes numériques.", ephemeral=True
            )

        if target.id == interaction.user.id:
            return await interaction.response.send_message(
                "🙃 Tu ne peux pas te gifler toi-même… enfin, techniquement si, mais pourquoi ?", ephemeral=True
            )

        gif_url = random.choice(SLAP_GIFS)
        embed = discord.Embed(
            title="GotValis : sanction comportementale appliquée 🖐️",
            description=f"{interaction.user.mention} gifle violemment {target.mention} !",
            color=discord.Color.red()
        )
        embed.set_image(url=gif_url)
        await interaction.response.send_message(embed=embed)

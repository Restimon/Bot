import discord
from discord.ext import commands

def register_help_commands(bot):
    @bot.command(name="aide")
    async def help_command(ctx):
        embed = discord.Embed(
            title="📖 Manuel d'opérations SomniCorp",
            description="Liste des procédures approuvées par SomniCorp. À utiliser avec précaution.",
            color=discord.Color.teal()
        )
        embed.add_field(name="🧰 Inventaire", value="`/inv` — Voir ton inventaire ou celui d’un membre.", inline=False)
        embed.add_field(name="⚔️ Combat", value="`/fight @membre` — Attaque un joueur.\n`/heal [@membre]` — Soigne.", inline=False)
        embed.add_field(name="🎁 Récompense quotidienne", value="`/daily` — Récupère ta récompense du jour.", inline=False)
        embed.add_field(name="🏆 Classement", value="`/leaderboard` — Affiche le classement.", inline=False)
        embed.set_footer(text="Utilisez /help pour la version slash.")
        await ctx.send(embed=embed)

    @bot.tree.command(name="help", description="Affiche la liste des commandes disponibles")
    async def help_slash(interaction: discord.Interaction):
        embed = discord.Embed(
            title="📖 Manuel d'opérations SomniCorp",
            description="Liste des procédures approuvées par SomniCorp. À utiliser avec précaution.",
            color=discord.Color.teal()
        )
        embed.add_field(name="🧰 Inventaire", value="`/inv` — Voir ton inventaire ou celui d’un membre.", inline=False)
        embed.add_field(name="⚔️ Combat", value="`/fight @membre`, `/heal [@membre]`", inline=False)
        embed.add_field(name="🎁 Récompense quotidienne", value="`/daily` — Réclame un bonus 1x par jour.", inline=False)
        embed.add_field(name="🏆 Classement", value="`/leaderboard` — Voir les dégâts et soins.", inline=False)
        embed.set_footer(text="Réalisez vos rêves, tout simplement — avec SomniCorp.")
        await interaction.response.send_message(embed=embed, ephemeral=True)

import discord
from discord.ext import commands

def register_help_commands(bot):
    @bot.command(name="aide")
    async def help_command(ctx):
        embed = build_help_embed()
        await ctx.send(embed=embed)

    @bot.tree.command(name="help", description="Affiche la liste des commandes disponibles")
    async def help_slash(interaction: discord.Interaction):
        embed = build_help_embed()
        await interaction.response.send_message(embed=embed, ephemeral=True)

def build_help_embed():
    embed = discord.Embed(
        title="📖 Manuel d'opérations SomniCorp",
        description="Voici les commandes disponibles pour interagir avec le système SomniCorp :",
        color=discord.Color.teal()
    )
    embed.add_field(
        name="🧰 Inventaire",
        value="`/inv` — Voir ton inventaire ou celui d’un membre.",
        inline=False
    )
    embed.add_field(
        name="⚔️ Combat",
        value="`/fight @membre` — Utilise un objet pour attaquer.\n`/heal [@membre]` — Utilise un objet pour soigner.",
        inline=False
    )
    embed.add_field(
        name="🎁 Quotidien",
        value="`/daily` — Obtiens ta récompense quotidienne.",
        inline=False
    )
    embed.add_field(
        name="🏆 Classement",
        value="`/leaderboard` — Consulte le classement global de ton serveur.",
        inline=False
    )
    embed.set_footer(text="Réalisez vos rêves, tout simplement — avec SomniCorp.")
    return embed

import discord
from discord.ext import commands

def register_help_commands(bot):
    @bot.command(name="aide")
    async def help_command(ctx):
        embed = build_help_embed()
        await ctx.send(embed=embed)

    @bot.tree.command(name="help", description="📘 Affiche toutes les commandes de GotValis")
    async def help_slash(interaction: discord.Interaction):
        await interaction.response.defer(thinking=False)
        embed = build_help_embed()
        await interaction.followup.send(embed=embed)

def build_help_embed():
    embed = discord.Embed(
        title="📘 Manuel Opérationnel - GotValis",
        description="Toutes les fonctionnalités mises à disposition par l’infrastructure **GotValis**.",
        color=discord.Color.teal()
    )

    embed.add_field(
        name="🎒 Inventaire",
        value="`/inv [@membre]` — Consulte ton inventaire ou celui de quelqu’un d’autre.",
        inline=False
    )

    embed.add_field(
        name="⚔️ Combat & Objets",
        value=(
            "`/fight @cible` — Utilise un objet offensif.\n"
            "`/heal [@cible]` — Utilise un objet de soin (💉 par exemple).\n"
            "`/box` — Utilise une 📦 pour obtenir des objets aléatoires.\n"
            "Certains objets appliquent des statuts persistants (🧪 poison, 🦠 virus, 🧟 infection...)."
        ),
        inline=False
    )

    embed.add_field(
        name="🧪 Statuts et effets GotValis",
        value=(
            "• **🧪 Poison** : -3 PV toutes les 30min pendant 3h. Réduit de 1 les dégâts infligés.\n"
            "• **🦠 Virus** : -5 PV immédiats, puis -5 PV par heure pendant 6h. Transmissible à chaque attaque. L’attaquant subit 2 dégâts.\n"
            "• **🧟 Infection** : -5 PV immédiats, -2 PV toutes les 30min pendant 3h. 25% de chance de propagation à chaque attaque."
        ),
        inline=False
    )

    embed.add_field(
        name="📦 Objets disponibles",
        value="`/item liste` — Affiche la description complète de tous les objets du jeu.",
        inline=False
    )

    embed.add_field(
        name="📊 Statistiques et Classements",
        value=(
            "`/leaderboard` — Classement global (avec kills et morts).\n"
            "`/info [@membre]` — Voir les PV, stats, statuts et classement personnel.\n"
            "`/status [@membre]` — Voir les effets persistants d’un joueur (virus, poison, etc.)."
        ),
        inline=False
    )

    embed.add_field(
        name="🎁 Récompense Quotidienne",
        value="`/daily` — Récupère des objets chaque jour grâce à GotValis.",
        inline=False
    )

    embed.set_footer(text="☁️ Propulsé par GotValis — La technologie au service de vos rêves.")
    return embed

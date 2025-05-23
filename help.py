import discord
from discord.ext import commands

def register_help_commands(bot):
    @bot.command(name="aide")
    async def help_command(ctx):
        embed = build_help_embed()
        await ctx.send(embed=embed)

    @bot.tree.command(name="help", description="📘 Affiche toutes les commandes de SomniCorp")
    async def help_slash(interaction: discord.Interaction):
        await interaction.response.defer(thinking=False)
        embed = build_help_embed()
        await interaction.followup.send(embed=embed)

def build_help_embed():
    embed = discord.Embed(
        title="📘 Manuel Opérationnel - SomniCorp",
        description="Toutes les fonctionnalités mises à disposition par l’infrastructure **SomniCorp**.",
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
        name="🧪 Statuts et effets SomniCorp",
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
            "`/setleaderboardchannel #salon` *(admin)* — Définit le salon du classement **spécial** mis à jour automatiquement.\n"
            "`/status [@membre]` — Voir les effets persistants d’un joueur (virus, poison, etc.)."
        ),
        inline=False
    )

    embed.add_field(
        name="🎁 Récompense Quotidienne",
        value="`/daily` — Récupère des objets chaque jour grâce à SomniCorp.",
        inline=False
    )

    embed.add_field(
        name="🛠️ Outils Admin (modérateurs uniquement)",
        value=(
            "`/reset @membre` — Réinitialise les stats d’un joueur.\n"
            "`/resetinv @membre` — Vide l’inventaire d’un joueur.\n"
            "`/resethp @membre` — Remet les PV à 100.\n"
            "`/resetall` — Réinitialise tous les joueurs (PV, stats, inventaire, statuts).\n"
            "`/resetleaderboard` — Réinitialise tout le classement.\n"
            "`/setleaderboardchannel #salon` — Définit le salon pour le leaderboard spécial.\n"
            "`/get_leaderboard_channel` — Affiche le salon actuel du leaderboard spécial.\n"
            "`/stopleaderboard` — Supprime le message et stoppe la MAJ automatique.\n"
            "`/supply` — Force l’apparition d’un ravitaillement spécial.\n"
            "`/forcer_lb_temp` — Met à jour manuellement le leaderboard spécial.\n"
            "`/giveitem @membre 🪓` — Donne un objet à un joueur.\n"
            "`/purge_status @membre` — Supprime les effets (virus, poison, infection) d’un joueur."
        ),
        inline=False
    )

    embed.set_footer(text="☁️ Propulsé par SomniCorp — La technologie au service de vos rêves.")
    return embed

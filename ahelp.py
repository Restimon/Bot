import discord
from discord import app_commands

def register_ahelp_command(bot):
    @bot.tree.command(name="ahelp", description="📙 Commandes admin GotValis")
    @app_commands.checks.has_permissions(administrator=True)
    async def help_admin(interaction: discord.Interaction):
        embed = build_ahelp_embed()
        await interaction.response.send_message(embed=embed, ephemeral=True)

def build_ahelp_embed():
    embed = discord.Embed(
        title="📙 Manuel Administrateur - GotValis",
        description="Commandes réservées aux administrateurs pour la gestion du système GotValis.",
        color=discord.Color.red()
    )

    embed.add_field(
        name="🎯 Gestion des joueurs",
        value=(
            "`/reset @membre` — Réinitialise les stats d’un joueur.\n"
            "`/resethp @membre` — Remet les PV d’un joueur à 100.\n"
            "`/resetinv @membre` — Vide l’inventaire d’un joueur.\n"
            "`/resetall` — Réinitialise **tous les joueurs** (PV, stats, inventaire, statuts).\n"
            "`/resetleaderboard` — Réinitialise le classement complet."
        ),
        inline=False
    )

    embed.add_field(
        name="📊 Leaderboard spécial",
        value=(
            "`/setleaderboardchannel #salon` — Définit le salon pour le classement spécial.\n"
            "`/get_leaderboard_channel` — Affiche le salon actuel du leaderboard spécial.\n"
            "`/stopleaderboard` — Supprime le message et stoppe la MAJ automatique.\n"
            "`/forcer_lb_temp` — Met à jour manuellement le leaderboard spécial."
        ),
        inline=False
    )

    embed.add_field(
        name="📦 Ravitaillement",
        value="`/supply` — Force l’apparition immédiate d’un ravitaillement spécial.",
        inline=False
    )

    embed.add_field(
        name="🎁 Objets & inventaire",
        value="`/giveitem @membre 🪓` — Donne un objet à un joueur.",
        inline=False
    )

    embed.add_field(
        name="🧼 Statuts",
        value="`/purge_status @membre` — Supprime poison, virus et infection d’un joueur.",
        inline=False
    )

    embed.add_field(
        name="💾 Sauvegardes",
        value=(
            "`/backups` — Affiche les sauvegardes disponibles pour ce serveur.\n"
            "`/restore fichier.json` — Restaure une sauvegarde locale."
        ),
        inline=False
    )

    embed.set_footer(text="🔐 Accès restreint : réservé aux administrateurs disposant des permissions adéquates.")
    return embed

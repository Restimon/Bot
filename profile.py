import discord
from discord import app_commands
from utils import inventaire, hp, leaderboard, OBJETS

def register_profile_command(bot):
    @bot.tree.command(name="info", description="Affiche le profil SomniCorp d’un membre.")
    @app_commands.describe(user="Le membre à inspecter")
    async def profile_slash(interaction: discord.Interaction, user: discord.Member = None):
        member = user or interaction.user
        uid = str(member.id)

        user_hp = hp.get(uid, 100)
        user_inv = inventaire.get(uid, [])
        user_stats = leaderboard.get(uid, {"degats": 0, "soin": 0})
        points = user_stats["degats"] + user_stats["soin"]

        # Calcul du rang
        sorted_lb = sorted(leaderboard.items(), key=lambda x: x[1]["degats"] + x[1]["soin"], reverse=True)
        rank = next((i + 1 for i, (id, _) in enumerate(sorted_lb) if id == uid), None)

        # Appliquer médaille si top 3
        medal = ""
        if rank == 1:
            medal = "🥇 "
        elif rank == 2:
            medal = "🥈 "
        elif rank == 3:
            medal = "🥉 "

        # Regrouper les objets par emoji et compter
        item_counts = {}
        for item in user_inv:
            item_counts[item] = item_counts.get(item, 0) + 1

        inv_display = "Aucun objet." if not item_counts else "\n".join(
            f"{emoji} × {count} — *{OBJETS.get(emoji, {}).get('type', 'inconnu')}*"
            for emoji, count in item_counts.items()
        )

        embed = discord.Embed(
            title=f"📄 Profil SomniCorp de {member.display_name}",
            description="Voici les informations enregistrées pour ce membre.",
            color=discord.Color.purple()
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="❤️ Points de vie", value=f"{user_hp} / 100", inline=False)
        embed.add_field(name="🎒 Inventaire", value=inv_display, inline=False)
        embed.add_field(
            name="📊 Statistiques",
            value=(
                f"• 🗡️ Dégâts infligés : **{user_stats.get('degats', 0)}**\n"
                f"• ✨ Soins prodigués : **{user_stats.get('soin', 0)}**\n"
                f"• 🎯 Points totaux : **{points}**"
            ),
            inline=False
        )
        embed.add_field(
            name="🏆 Classement général",
            value=f"{medal}{rank}" if rank else "Non classé",
            inline=False
        )
        embed.set_footer(text="Analyse générée par les serveurs de SomniCorp.")

        await interaction.response.send_message(embed=embed, ephemeral=False)

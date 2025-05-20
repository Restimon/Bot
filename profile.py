import discord
from discord import app_commands
from storage import get_user_data, inventaire, hp, leaderboard
from utils import OBJETS

def register_profile_command(bot):
    @bot.tree.command(name="info", description="Affiche le profil SomniCorp d’un membre.")
    @app_commands.describe(user="Le membre à inspecter")
    async def profile_slash(interaction: discord.Interaction, user: discord.Member = None):
        await interaction.response.defer(thinking=True, ephemeral=False)

        member = user or interaction.user
        guild_id = str(interaction.guild.id)
        uid = str(member.id)

        # Récupérer les données utilisateur dans ce serveur
        user_data = get_user_data(guild_id, uid)
        user_inv = user_data["inventory"]
        user_hp = user_data["hp"]
        user_stats = user_data["stats"]
        points = user_stats["degats"] + user_stats["soin"]

        # Tri du classement pour CE serveur uniquement
        server_leaderboard = leaderboard.get(guild_id, {})
        sorted_lb = sorted(
            server_leaderboard.items(),
            key=lambda x: x[1]["degats"] + x[1]["soin"],
            reverse=True
        )
        rank = next((i + 1 for i, (id, _) in enumerate(sorted_lb) if id == uid), None)

        # Médaille si top 3
        medals = {1: "🥇", 2: "🥈", 3: "🥉"}
        medal = medals.get(rank, "")

        # Regrouper inventaire
        item_counts = {}
        for item in user_inv:
            item_counts[item] = item_counts.get(item, 0) + 1

        inv_display = "Aucun objet." if not item_counts else "\n".join(
            f"{emoji} × {count}" for emoji, count in item_counts.items()
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
                f"• 🗡️ Dégâts infligés : **{user_stats['degats']}**\n"
                f"• ✨ Soins prodigués : **{user_stats['soin']}**\n"
                f"• 🎯 Points totaux : **{points}**"
            ),
            inline=False
        )
        embed.add_field(
            name="🏆 Classement général",
            value=f"{medal} Rang {rank}" if rank else "Non classé",
            inline=False
        )
        embed.set_footer(text="Analyse générée par les serveurs de SomniCorp.")

        await interaction.followup.send(embed=embed)

import discord
import time
from discord import app_commands
from storage import get_user_data, leaderboard
from data import leaderboard
from economy_utils import get_gotcoins  # ✅ On centralise le calcul

def register_stats_command(bot):
    @bot.tree.command(name="stats", description="📊 Affiche les statistiques de GotCoins et de combat d’un membre.")
    @app_commands.describe(user="Le membre dont vous voulez consulter les statistiques")
    async def stats_slash(interaction: discord.Interaction, user: discord.Member = None):
        await interaction.response.defer(thinking=True)

        member = user or interaction.user
        guild_id = str(interaction.guild.id)
        uid = str(member.id)

        user_inv, user_hp, user_stats = get_user_data(guild_id, uid)
        gotcoins = get_gotcoins(user_stats)

        # Classement basé sur GotCoins
        server_leaderboard = leaderboard.get(guild_id, {})
        sorted_lb = sorted(
            server_leaderboard.items(),
            key=lambda x: get_gotcoins(x[1]),
            reverse=True
        )
        rank = next((i + 1 for i, (id, _) in enumerate(sorted_lb) if id == uid), None)
        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(rank, "")

        # Build embed
        embed = discord.Embed(
            title=f"📊 Statistiques de {member.display_name}",
            description="Analyse des performances GotValis.",
            color=discord.Color.blue()
        )
        embed.set_thumbnail(url=member.display_avatar.url)

        embed.add_field(
            name="💰 GotCoins actuels",
            value=f"**{gotcoins}**",
            inline=False
        )
        embed.add_field(
            name="📈 Détails des statistiques",
            value=(
                f"• 🗡️ Dégâts infligés : **{user_stats.get('degats', 0)}**\n"
                f"• ✨ Soins prodigués : **{user_stats.get('soin', 0)}**\n"
                f"• ☠️ Kills : **{user_stats.get('kills', 0)}**\n"
                f"• 💀 Morts : **{user_stats.get('morts', 0)}**\n"
            ),
            inline=False
        )
        embed.add_field(
            name="🏆 Classement général",
            value=f"{medal} Rang {rank}" if rank else "Non classé",
            inline=False
        )

        embed.set_footer(text="💰 Les GotCoins sont votre richesse accumulée dans GotValis.")
        await interaction.followup.send(embed=embed)

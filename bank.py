import discord
from discord import app_commands
from storage import get_user_data, leaderboard
from economy import get_balance, get_total_gotcoins_earned

def register_bank_command(bot):
    @bot.tree.command(name="bank", description="💰 Consulte ton solde de GotCoins et ton classement.")
    @app_commands.describe(user="Le membre à inspecter")
    async def bank_slash(interaction: discord.Interaction, user: discord.Member = None):
        await interaction.response.defer(thinking=True)

        member = user or interaction.user
        guild_id = str(interaction.guild.id)
        uid = str(member.id)

        _, _, user_stats = get_user_data(guild_id, uid)

        # ✅ Utiliser get_balance pour la balance actuelle
        gotcoins = get_balance(guild_id, uid)

        # Classement basé sur GotCoins (balance actuelle)
        server_leaderboard = leaderboard.get(guild_id, {})
        sorted_lb = sorted(
            server_leaderboard.items(),
            key=lambda x: get_balance(guild_id, x[0]),  # ✅ get_balance ici aussi
            reverse=True
        )
        rank = next((i + 1 for i, (id, _) in enumerate(sorted_lb) if id == uid), None)
        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(rank, "")

        # Construction de l'embed
        embed = discord.Embed(
            title=f"📄 Banque GotValis de {member.display_name}",
            color=discord.Color.gold()
        )
        embed.set_thumbnail(url=member.display_avatar.url)

        embed.add_field(
            name="💰 GotCoins",
            value=f"**{gotcoins}** GotCoins",
            inline=False
        )

        embed.add_field(
            name="🏆 Classement général",
            value=f"{medal} Rang {rank}" if rank else "Non classé",
            inline=False
        )

        # ✅ Optionnel : total gagné en carrière (ça peut être utile)
        total_earned = get_total_gotcoins_earned(guild_id, uid)
        embed.add_field(
            name="📈 Total gagné en carrière",
            value=f"**{total_earned}** GotCoins",
            inline=False
        )

        await interaction.followup.send(embed=embed)

import discord
import time
from discord import app_commands
from storage import get_user_data, get_user_balance
from economy import gotcoins_stats, get_total_gotcoins_earned, compute_message_gains, compute_voice_gains, get_balance
from data import weekly_message_count, weekly_voice_time

def register_stats_command(bot):
    @bot.tree.command(name="stats", description="📊 Affiche les statistiques de GotCoins et de combat d’un membre.")
    @app_commands.describe(user="Le membre dont vous voulez consulter les statistiques")
    async def stats_slash(interaction: discord.Interaction, user: discord.Member = None):
        await interaction.response.defer(thinking=True)

        member = user or interaction.user
        guild_id = str(interaction.guild.id)
        uid = str(member.id)

        # Récupère les stats actuelles et balance
        user_stats = gotcoins_stats.get(guild_id, {}).get(uid, {})
        gotcoins_total = get_total_gotcoins_earned(guild_id, uid)  # ✅ total carrière
        balance = get_user_balance(guild_id, uid)  # ✅ propre via storage.py

        # Classement basé sur total gagné
        server_lb = gotcoins_stats.get(guild_id, {})
        sorted_lb = sorted(
            server_lb.items(),
            key=lambda x: get_total_gotcoins_earned(guild_id, x[0]),  # ✅ on trie bien sur total carrière
            reverse=True
        )
        rank = next((i + 1 for i, (id, _) in enumerate(sorted_lb) if id == uid), None)
        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(rank, "")

        # Récupère les stats de messages / vocal
        msg_count = weekly_message_count.get(guild_id, {}).get(uid, 0)
        voice_sec = weekly_voice_time.get(guild_id, {}).get(uid, 0)
        voice_min = voice_sec // 60
        voice_h = voice_min // 60
        voice_m = voice_min % 60

        # Build embed
        embed = discord.Embed(
            title=f"📊 Statistiques de {member.display_name}",
            description="Analyse des performances GotValis.",
            color=discord.Color.blue()
        )
        embed.set_thumbnail(url=member.display_avatar.url)

        embed.add_field(
            name="💰 GotCoins totaux gagnés",
            value=f"**{gotcoins_total}**",
            inline=False
        )
        embed.add_field(
            name="💵 Solde réel (dépensable)",
            value=f"**{balance} GotCoins**",
            inline=False
        )
        embed.add_field(
            name="📈 Détails des statistiques",
            value=(
                f"• 🗡️ Dégâts infligés : **{user_stats.get('degats', 0)}**\n"
                f"• ✨ Soins prodigués : **{user_stats.get('soin', 0)}**\n"
                f"• ☠️ Kills : **{user_stats.get('kills', 0)}**\n"
                f"• 💀 Morts : **{user_stats.get('morts', 0)}**\n"
                f"• 🎁 Gains divers (autre) : **{user_stats.get('autre', 0)}**\n"
                f"• 🛒 Dépenses (achats) : **{user_stats.get('achats', 0)}**"
            ),
            inline=False
        )
        embed.add_field(
            name="📊 Activité hebdomadaire",
            value=(
                f"• ✉️ Messages envoyés : **{msg_count}**\n"
                f"• 🎙️ Temps en vocal : **{voice_h}h {voice_m}min**"
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

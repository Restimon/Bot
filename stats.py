# stats.py
import discord
from discord import app_commands

from storage import get_user_data
# 🔧 Rendu compatible avec anciennes versions de storage.py
try:
    from storage import get_user_balance  # exposé par certaines versions
except ImportError:
    from economy import get_balance as get_user_balance  # fallback

from economy import gotcoins_stats, get_total_gotcoins_earned
from data import weekly_message_log, weekly_voice_time


def register_stats_command(bot):
    @bot.tree.command(
        name="stats",
        description="📊 Affiche les statistiques de GotCoins et de combat d’un membre."
    )
    @app_commands.describe(user="Le membre dont vous voulez consulter les statistiques")
    async def stats_slash(interaction: discord.Interaction, user: discord.Member | None = None):
        await interaction.response.defer(thinking=True)

        member = user or interaction.user
        guild_id = str(interaction.guild.id)
        uid = str(member.id)

        # Stats GotCoins (totaux cumulés et solde)
        user_stats = gotcoins_stats.get(guild_id, {}).get(uid, {})
        gotcoins_total = get_total_gotcoins_earned(guild_id, uid)
        balance = get_user_balance(guild_id, uid)

        # Classement basé sur le total gagné
        server_lb = gotcoins_stats.get(guild_id, {})
        sorted_lb = sorted(
            server_lb.items(),
            key=lambda x: get_total_gotcoins_earned(guild_id, x[0]),
            reverse=True
        )
        rank = next((i + 1 for i, (id_, _) in enumerate(sorted_lb) if id_ == uid), None)
        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(rank, "")

        # Activité hebdo
        msg_count = len(weekly_message_log.get(guild_id, {}).get(uid, []))
        voice_sec_total = int(weekly_voice_time.get(guild_id, {}).get(uid, 0))

        # Formatage temps vocal (j/h/min)
        days = voice_sec_total // (24 * 3600)
        voice_sec_total %= (24 * 3600)
        hours = voice_sec_total // 3600
        voice_sec_total %= 3600
        mins = voice_sec_total // 60
        voice_time_str = f"**{days} j {hours} h {mins} min**"

        # Embed
        embed = discord.Embed(
            title=f"📊 Statistiques de {member.display_name}",
            description="Analyse des performances GotValis.",
            color=discord.Color.blue()
        )
        embed.set_thumbnail(url=member.display_avatar.url)

        embed.add_field(name="💰 GotCoins totaux gagnés", value=f"**{gotcoins_total}**", inline=False)
        embed.add_field(name="💵 Solde réel (dépensable)", value=f"**{balance} GotCoins**", inline=False)

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
            value=(f"• ✉️ Messages envoyés : **{msg_count}**\n"
                   f"• 🎙️ Temps en vocal : {voice_time_str}"),
            inline=False
        )

        embed.add_field(
            name="🏆 Classement général",
            value=f"{medal} Rang {rank}" if rank else "Non classé",
            inline=False
        )

        embed.set_footer(text="💰 Les GotCoins sont votre richesse accumulée dans GotValis.")
        await interaction.followup.send(embed=embed)

import discord
import time

from discord import app_commands
from storage import get_user_data, leaderboard
from data import virus_status, poison_status
from utils import OBJETS

def register_profile_command(bot):
    @bot.tree.command(name="info", description="Affiche le profil SomniCorp d’un membre.")
    @app_commands.describe(user="Le membre à inspecter")
    async def profile_slash(interaction: discord.Interaction, user: discord.Member = None):
        try:
            await interaction.response.defer(thinking=True, ephemeral=False)
        except discord.NotFound:
            return

        member = user or interaction.user
        guild_id = str(interaction.guild.id)
        uid = str(member.id)

        user_inv, user_hp, user_stats = get_user_data(guild_id, uid)
        points = user_stats["degats"] + user_stats["soin"]

        server_leaderboard = leaderboard.get(guild_id, {})
        sorted_lb = sorted(
            server_leaderboard.items(),
            key=lambda x: x[1]["degats"] + x[1]["soin"],
            reverse=True
        )
        rank = next((i + 1 for i, (id, _) in enumerate(sorted_lb) if id == uid), None)
        medals = {1: "🥇", 2: "🥈", 3: "🥉"}
        medal = medals.get(rank, "")

        item_counts = {}
        for item in user_inv:
            item_counts[item] = item_counts.get(item, 0) + 1
        inv_display = "Aucun objet." if not item_counts else "\n".join(
            f"{emoji} × {count}" for emoji, count in item_counts.items()
        )

        embed = discord.Embed(
            title=f"📄 Profil SomniCorp de {member.display_name}",
            description="Analyse médicale et opérationnelle en cours...",
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

        # ☣️ Virus et Poison
        now = time.time()
        status_lines = []

        v = virus_status.get(guild_id, {}).get(uid)
        if v:
            elapsed = now - v["start"]
            remaining = max(0, v["duration"] - elapsed)
            next_tick = 3600 - (elapsed % 3600)
            warning = " ⚠️" if next_tick < 300 else ""
            v_remain_m = int(remaining // 60)
            v_tick_m = int(next_tick // 60)
            v_tick_s = int(next_tick % 60)
            status_lines.append(
                f"🦠 Virus : **{v_remain_m} min restantes** | prochain dégât dans **{v_tick_m}m {v_tick_s}s**{warning}"
            )

        p = poison_status.get(guild_id, {}).get(uid)
        if p:
            elapsed = now - p["start"]
            remaining = max(0, p["duration"] - elapsed)
            next_tick = 1800 - (elapsed % 1800)
            warning = " ⚠️" if next_tick < 300 else ""
            p_remain_m = int(remaining // 60)
            p_tick_m = int(next_tick // 60)
            p_tick_s = int(next_tick % 60)
            status_lines.append(
                f"🧪 Poison : **{p_remain_m} min restantes** | prochain dégât dans **{p_tick_m}m {p_tick_s}s**{warning}"
            )

        embed.add_field(
            name="☣️ Effets actifs",
            value="\n".join(status_lines) if status_lines else "✅ Aucun effet détecté par SomniCorp.",
            inline=False
        )

        embed.set_footer(text="📡 Rapport généré par les serveurs SomniCorp.")
        await interaction.followup.send(embed=embed)

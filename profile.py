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
            return  # L’interaction a expiré, on ne fait rien

        member = user or interaction.user
        guild_id = str(interaction.guild.id)
        uid = str(member.id)

        # Récupération des données utilisateur
        user_inv, user_hp, user_stats = get_user_data(guild_id, uid)
        points = user_stats["degats"] + user_stats["soin"]

        # Classement local
        server_leaderboard = leaderboard.get(guild_id, {})
        sorted_lb = sorted(
            server_leaderboard.items(),
            key=lambda x: x[1]["degats"] + x[1]["soin"],
            reverse=True
        )
        rank = next((i + 1 for i, (id, _) in enumerate(sorted_lb) if id == uid), None)
        medals = {1: "🥇", 2: "🥈", 3: "🥉"}
        medal = medals.get(rank, "")

        # Affichage inventaire
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

        # ☣️ Ajout des effets Poison / Virus
        now = time.time()
        status_lines = []

        virus = virus_status.get(guild_id, {}).get(uid)
        if virus:
            elapsed = now - virus["start"]
            remaining = max(0, virus["duration"] - elapsed)
            next_tick = 3600 - (elapsed % 3600)
            status_lines.append(f"🦠 Virus — {int(remaining // 60)} min restantes | prochain dégât dans {int(next_tick // 60)} min")

        poison = poison_status.get(guild_id, {}).get(uid)
        if poison:
            elapsed = now - poison["start"]
            remaining = max(0, poison["duration"] - elapsed)
            next_tick = 1800 - (elapsed % 1800)
            status_lines.append(f"🧪 Poison — {int(remaining // 60)} min restantes | prochain dégât dans {int(next_tick // 60)} min")

        embed.add_field(
            name="☣️ Effets actifs",
            value="\n".join(status_lines) if status_lines else "Aucun effet négatif actif.",
            inline=False
        )

        embed.set_footer(text="Analyse générée par les serveurs de SomniCorp.")
        await interaction.followup.send(embed=embed)

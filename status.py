import discord
import time
from discord import app_commands
from data import virus_status, poison_status

def register_status_command(bot):
    @bot.tree.command(name="status", description="Voir si un membre est affecté par un virus ou un poison SomniCorp")
    @app_commands.describe(user="Membre à inspecter (optionnel)")
    async def status_command(interaction: discord.Interaction, user: discord.Member = None):
        member = user or interaction.user
        guild_id = str(interaction.guild.id)
        user_id = str(member.id)
        now = time.time()

        embed = discord.Embed(
            title=f"🧬 Statut de {member.display_name}",
            color=discord.Color.orange()
        )

        # Virus
        v_stat = virus_status.get(guild_id, {}).get(user_id)
        if v_stat:
            v_elapsed = now - v_stat["start"]
            v_remaining = max(0, v_stat["duration"] - v_elapsed)
            v_hours = int(v_remaining // 3600)
            v_minutes = int((v_remaining % 3600) // 60)
            embed.add_field(
                name="🦠 Infection virale",
                value=f"Infecté — {v_hours}h {v_minutes}min restants\n💉 Vaccin possible.",
                inline=False
            )
        else:
            embed.add_field(name="🦠 Infection virale", value="✅ Non infecté", inline=False)

        # Poison
        p_stat = poison_status.get(guild_id, {}).get(user_id)
        if p_stat:
            p_elapsed = now - p_stat["start"]
            p_remaining = max(0, p_stat["duration"] - p_elapsed)
            p_hours = int(p_remaining // 3600)
            p_minutes = int((p_remaining % 3600) // 60)
            embed.add_field(
                name="🧪 Empoisonnement",
                value=f"Empoisonné — {p_hours}h {p_minutes}min restants\n🧼 Aucun remède connu.",
                inline=False
            )
        else:
            embed.add_field(name="🧪 Empoisonnement", value="✅ Non empoisonné", inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)

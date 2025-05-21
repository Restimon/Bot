import discord
import time
from discord import app_commands
from data import virus_status, poison_status, infection_status

def register_status_command(bot):
    @bot.tree.command(name="status", description="Voir si un membre est affecté par un virus ou un poison SomniCorp")
    @app_commands.describe(user="Membre à inspecter (optionnel)")
    async def status_command(interaction: discord.Interaction, user: discord.Member = None):
        member = user or interaction.user
        guild_id = str(interaction.guild.id)
        user_id = str(member.id)
        now = time.time()

        embed = discord.Embed(
            title=f"🧬 Rapport médical SomniCorp — {member.display_name}",
            color=discord.Color.orange()
        )

        # ... [début inchangé]

        # 🦠 Virus
        v_stat = virus_status.get(guild_id, {}).get(user_id)
        if v_stat:
            v_elapsed = now - v_stat["start"]
            v_remaining = max(0, v_stat["duration"] - v_elapsed)
            v_next_tick = 3600 - (v_elapsed % 3600)
            v_hours = int(v_remaining // 3600)
            v_minutes = int((v_remaining % 3600) // 60)
            v_tick_m = int(v_next_tick // 60)
            v_tick_s = int(v_next_tick % 60)
            warning = " ⚠️" if v_tick_m < 5 else ""

            embed.add_field(
                name="🦠 Infection virale détectée",
                value=(
                    f"• Temps restant : **{v_hours}h {v_minutes}min**\n"
                    f"• Prochain dégât : **dans {v_tick_m}min {v_tick_s}s**{warning}\n"
                    f"• ⚔️ En attaquant, vous perdez **2 PV** et **propagez le virus** à votre cible.\n"
                    f"💉 Utilisez un vaccin via `/heal` pour éradiquer le virus."
                ),
                inline=False
            )
        else:
            embed.add_field(name="🦠 Infection virale", value="✅ Aucun virus détecté par SomniCorp", inline=False)

        # 🧪 Poison
        p_stat = poison_status.get(guild_id, {}).get(user_id)
        if p_stat:
            p_elapsed = now - p_stat["start"]
            p_remaining = max(0, p_stat["duration"] - p_elapsed)
            p_next_tick = 1800 - (p_elapsed % 1800)
            p_hours = int(p_remaining // 3600)
            p_minutes = int((p_remaining % 3600) // 60)
            p_tick_m = int(p_next_tick // 60)
            p_tick_s = int(p_next_tick % 60)
            warning = " ⚠️" if p_tick_m < 5 else ""

            embed.add_field(
                name="🧪 Empoisonnement détecté",
                value=(
                    f"• Temps restant : **{p_hours}h {p_minutes}min**\n"
                    f"• Prochain dégât : **dans {p_tick_m}min {p_tick_s}s**{warning}\n"
                    f"• ⚔️ Vos attaques infligent **1 dégât en moins** tant que vous êtes empoisonné.\n"
                    f"🧼 Aucun antidote connu. Survivez."
                ),
                inline=False
            )
        else:
            embed.add_field(name="🧪 Empoisonnement", value="✅ Aucun poison détecté par SomniCorp", inline=False)

        # 🧟 Infection
        i_stat = infection_status.get(guild_id, {}).get(user_id)
        if i_stat:
            i_elapsed = now - i_stat["start"]
            i_remaining = max(0, i_stat["duration"] - i_elapsed)
            i_next_tick = 1800 - (i_elapsed % 1800)
            i_hours = int(i_remaining // 3600)
            i_minutes = int((i_remaining % 3600) // 60)
            i_tick_m = int(i_next_tick // 60)
            i_tick_s = int(i_next_tick % 60)
            warning = " ⚠️" if i_tick_m < 5 else ""

            embed.add_field(
                name="🧟 Infection détectée",
                value=(
                    f"• Temps restant : **{i_hours}h {i_minutes}min**\n"
                    f"• Prochain dégât : **dans {i_tick_m}min {i_tick_s}s**{warning}\n"
                    f"• ⚔️ Attaquer donne **25% de chance** d’infecter votre cible.\n"
                    f"• 😵 Vous subissez **2 dégâts toutes les 30 min.**"
                ),
                inline=False
            )
        else:
            embed.add_field(name="🧟 Infection", value="✅ Aucun agent infectieux détecté", inline=False)

        embed.set_footer(text="📡 Données scannées et transmises par les serveurs de SomniCorp.")
        await interaction.response.send_message(embed=embed)

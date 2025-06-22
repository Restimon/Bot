import discord
import time
from discord import app_commands
from data import (
    virus_status, poison_status, infection_status,
    immunite_status, regeneration_status
)
from embeds import build_embed_from_item

def register_status_command(bot):
    @bot.tree.command(name="status", description="Voir si un membre est affecté par un virus ou un poison GotValis")
    @app_commands.describe(user="Membre à inspecter (optionnel)")
    async def status_command(interaction: discord.Interaction, user: discord.Member = None):
        member = user or interaction.user
        guild_id = str(interaction.guild.id)
        user_id = str(member.id)
        now = time.time()

        embed = discord.Embed(
            title=f"🧬 Rapport médical — {member.display_name}",
            color=discord.Color.orange()
        )

        # 🧩 Fonction utilitaire pour formater les durées
        def format_time(seconds):
            minutes = int(seconds // 60)
            secs = int(seconds % 60)
            return f"{minutes}m {secs}s"

        # ⭐️ Immunité
        if (im := immunite_status.get(guild_id, {}).get(user_id)):
            remaining = max(0, im["duration"] - (now - im["start"]))
            embed.add_field(
                name="⭐️ Immunité active",
                value=f"• Temps restant : **{format_time(remaining)}**",
                inline=False
            )

        # 💕 Régénération
        if (regen := regeneration_status.get(guild_id, {}).get(user_id)):
            elapsed = now - regen["start"]
            remaining = max(0, regen["duration"] - elapsed)
            next_tick = 1800 - (elapsed % 1800)
            warn = " ⚠️" if next_tick < 300 else ""
            embed.add_field(
                name="💕 Régénération cellulaire",
                value=(
                    f"• Temps restant : **{int(remaining // 60)} min**\n"
                    f"• Prochain soin : **dans {format_time(next_tick)}**{warn}\n"
                    f"• ✨ Régénère **3 PV toutes les 30 min**"
                ),
                inline=False
            )

        # 🦠 Virus
        if (virus := virus_status.get(guild_id, {}).get(user_id)):
            elapsed = now - virus["start"]
            remaining = max(0, virus["duration"] - elapsed)
            tick = 3600 - (elapsed % 3600)
            warn = " ⚠️" if tick < 300 else ""
            embed.add_field(
                name="🦠 Infection virale",
                value=(
                    f"• Temps restant : **{int(remaining // 3600)}h {int((remaining % 3600) // 60)}min**\n"
                    f"• Prochain dégât : **dans {format_time(tick)}**{warn}\n"
                    f"• ⚔️ Vous perdez **2 PV** par attaque et propagez le virus.\n"
                    f"💉 Utilisez un vaccin via `/heal`."
                ),
                inline=False
            )
        else:
            embed.add_field(name="🦠 Infection virale", value="✅ Aucun virus détecté", inline=False)

        # 🧪 Poison
        if (poison := poison_status.get(guild_id, {}).get(user_id)):
            elapsed = now - poison["start"]
            remaining = max(0, poison["duration"] - elapsed)
            tick = 1800 - (elapsed % 1800)
            warn = " ⚠️" if tick < 300 else ""
            embed.add_field(
                name="🧪 Empoisonnement",
                value=(
                    f"• Temps restant : **{int(remaining // 3600)}h {int((remaining % 3600) // 60)}min**\n"
                    f"• Prochain dégât : **dans {format_time(tick)}**{warn}\n"
                    f"• ⚔️ Vos attaques infligent **1 dégât en moins**.\n"
                    f"🧼 Aucun antidote connu."
                ),
                inline=False
            )
        else:
            embed.add_field(name="🧪 Empoisonnement", value="✅ Aucun poison détecté", inline=False)

        # 🧟 Infection GotValis
        if (infect := infection_status.get(guild_id, {}).get(user_id)):
            elapsed = now - infect["start"]
            remaining = max(0, infect["duration"] - elapsed)
            tick = 1800 - (elapsed % 1800)
            warn = " ⚠️" if tick < 300 else ""
            embed.add_field(
                name="🧟 Infection GotValis",
                value=(
                    f"• Temps restant : **{int(remaining // 3600)}h {int((remaining % 3600) // 60)}min**\n"
                    f"• Prochain dégât : **dans {format_time(tick)}**{warn}\n"
                    f"• ⚔️ Vous avez **25% de chance** d’infecter votre cible.\n"
                    f"• 😵 Vous subissez **2 dégâts toutes les 30 min.**"
                ),
                inline=False
            )
        else:
            embed.add_field(name="🧟 Infection", value="✅ Aucun agent infectieux détecté", inline=False)

        embed.set_footer(text="📡 Données scannées via les serveurs GotValis.")
        await interaction.response.send_message(embed=embed)

import discord
import time
from discord import app_commands
from storage import get_user_data, leaderboard
from data import (
    virus_status, poison_status, infection_status,
    shields, esquive_status, casque_status, immunite_status,
    regeneration_status,
)
from embeds import build_embed_from_item
from economy_utils import get_gotcoins

def register_profile_command(bot):
    @bot.tree.command(name="info", description="Affiche le profil GotValis d’un membre.")
    @app_commands.describe(user="Le membre à inspecter")
    async def profile_slash(interaction: discord.Interaction, user: discord.Member = None):
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

        # Inventaire
        item_counts = {}
        for item in user_inv:
            item_counts[item] = item_counts.get(item, 0) + 1
        inv_display = "Aucun objet." if not item_counts else "\n".join(f"{emoji} × {count}" for emoji, count in item_counts.items())

        # PV + bouclier
        shield_amt = shields.get(guild_id, {}).get(uid, 0)
        hp_display = f"{user_hp} / 100" + (f" + 🛡 {shield_amt}" if shield_amt > 0 else "")

        embed = discord.Embed(
            title=f"📄 Profil GotValis de {member.display_name}",
            description="Analyse médicale et opérationnelle en cours...",
            color=discord.Color.purple()
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="❤️ Points de vie", value=hp_display, inline=False)
        embed.add_field(name="🎒 Inventaire", value=inv_display, inline=False)
        embed.add_field(
            name="📊 Statistiques",
            value=(
                f"• 🗡️ Dégâts infligés : **{user_stats['degats']}**\n"
                f"• ✨ Soins prodigués : **{user_stats['soin']}**\n"
                f"• ☠️ Kills : **{user_stats.get('kills', 0)}**\n"
                f"• 💀 Morts : **{user_stats.get('morts', 0)}**\n"
                f"• 💰 GotCoins : **{gotcoins}**"
            ),
            inline=False
        )
        embed.add_field(
            name="🏆 Classement général",
            value=f"{medal} Rang {rank}" if rank else "Non classé",
            inline=False
        )

        # Effets négatifs
        now = time.time()
        status_lines = []

        for status, label, tick, emoji, note in [
            (virus_status, "Virus actif", 3600, "🦠", "Lors d’une attaque : -2 PV pour vous + propagation du virus."),
            (poison_status, "Empoisonnement actif", 1800, "🧪", "Vos attaques infligent **1 dégât en moins**."),
            (infection_status, "Infection active", 1800, "🧟", "25% de chance d’infecter votre cible en attaquant.")
        ]:
            data = status.get(guild_id, {}).get(uid)
            if isinstance(data, dict) and "start" in data and "duration" in data:
                elapsed = now - data["start"]
                remaining = max(0, data["duration"] - elapsed)
                next_tick = tick - (elapsed % tick)
                warning = " ⚠️" if next_tick < 300 else ""
                rem_min = int(remaining // 60)
                t_m = int(next_tick // 60)
                t_s = int(next_tick % 60)
                status_lines.append(
                    f"{emoji} **{label}**\n"
                    f"• Temps restant : **{rem_min} min**\n"
                    f"• Prochain dégât : **dans {t_m}m {t_s}s**{warning}\n"
                    f"• ⚔️ {note}"
                )

        embed.add_field(
            name="☣️ État pathologique",
            value="\n\n".join(status_lines) if status_lines else "✅ Aucun effet négatif détecté.",
            inline=False
        )

        # Bonus temporaires (hors bouclier)
        bonus_lines = []

        for bonus, emoji, label, extra in [
            (esquive_status, "💨", "Esquive améliorée", "+20%"),
            (casque_status, "🪖", "Casque", "dégâts reçus ÷2"),
            (immunite_status, "⭐️", "Immunité totale", "")
        ]:
            data = bonus.get(guild_id, {}).get(uid)
            if isinstance(data, dict) and "start" in data and "duration" in data:
                elapsed = now - data["start"]
                remaining = max(0, data["duration"] - elapsed)
                rem_min = int(remaining // 60)
                bonus_lines.append(f"{emoji} **{label}** — {rem_min} min restants {extra}")

        # ✅ Régénération
        regen_data = regeneration_status.get(guild_id, {}).get(uid)
        if isinstance(regen_data, dict) and "start" in regen_data and "duration" in regen_data:
            elapsed = now - regen_data["start"]
            remaining = max(0, regen_data["duration"] - elapsed)
            rem_min = int(remaining // 60)
            bonus_lines.append(f"💕 **Régénération** — {rem_min} min restantes (+3 PV / 30 min)")

        if bonus_lines:
            bonus_embed = discord.Embed(
                title="🌀 Effets temporaires actifs",
                description="\n".join(bonus_lines),
                color=discord.Color.teal()
            )
            bonus_embed.set_footer(text="⏳ Bonus positifs actifs détectés.")
            await interaction.followup.send(embeds=[embed, bonus_embed])
        else:
            await interaction.followup.send(embed=embed)

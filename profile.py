import discord
import time
from discord import app_commands
from storage import get_user_data, hp
from data import (
    virus_status, poison_status, infection_status,
    shields, esquive_status, casque_status, immunite_status,
    regeneration_status,
)
from economy import get_total_gotcoins_earned, get_balance, gotcoins_stats, get_gotcoins

def register_profile_command(bot):
    @bot.tree.command(name="profile", description="Affiche le profil GotValis d’un membre.")
    @app_commands.describe(user="Le membre à inspecter")
    async def profile_slash(interaction: discord.Interaction, user: discord.Member = None):
        await interaction.response.defer(thinking=True)

        member = user or interaction.user
        guild_id = str(interaction.guild.id)
        uid = str(member.id)

        user_inv, user_hp, _ = get_user_data(guild_id, uid)
        total_gotcoins = get_total_gotcoins_earned(guild_id, uid)
        balance = get_balance(guild_id, uid)

        # Classement basé sur argent total gagné
        server_lb = gotcoins_stats.get(guild_id, {})
        sorted_lb = sorted(
            server_lb.items(),
            key=lambda x: get_total_gotcoins_earned(guild_id, x[0]),
            reverse=True
        )
        rank = next((i + 1 for i, (id, _) in enumerate(sorted_lb) if id == uid), None)
        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(rank, "")

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
        embed.add_field(name="💰 GotCoins totaux (carrière)", value=f"**{total_gotcoins}**", inline=False)
        embed.add_field(name="💵 Solde actuel (dépensable)", value=f"**{balance} GotCoins**", inline=False)
        embed.add_field(
            name="🏆 Classement général",
            value=f"{medal} Rang {rank}" if rank else "Non classé",
            inline=False
        )

        # 📅 Date de join
        joined_at = member.joined_at
        if joined_at:
            embed.add_field(
                name="📅 Membre depuis",
                value=joined_at.strftime("%d %B %Y à %Hh%M"),
                inline=False
            )

        # INVENTAIRE
        item_counts = {}
        for item in user_inv:
            item_counts[item] = item_counts.get(item, 0) + 1

        if not item_counts:
            embed.add_field(name="🎒 Inventaire", value="Aucun objet.", inline=False)
        else:
            chunk_size = 4
            item_list = list(item_counts.items())
            chunks = [item_list[i:i+chunk_size] for i in range(0, len(item_list), chunk_size)]

            for i, chunk in enumerate(chunks):
                value = "\n".join(f"{emoji} × {count}" for emoji, count in chunk)
                embed.add_field(
                    name="🎒 Inventaire" if i == 0 else "\u200b",
                    value=value,
                    inline=True
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

        # Bonus temporaires
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

        # Régénération
        regen_data = regeneration_status.get(guild_id, {}).get(uid)
        if isinstance(regen_data, dict) and "start" in regen_data and "duration" in regen_data:
            elapsed = now - regen_data["start"]
            remaining = max(0, regen_data["duration"] - elapsed)
            rem_min = int(remaining // 60)
            bonus_lines.append(f"💕 **Régénération** — {rem_min} min restantes (+3 PV / 30 min)")

        # Envoi
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

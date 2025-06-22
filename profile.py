import discord
import time
import os
from discord import app_commands
from storage import get_user_data, get_collection, hp
from data import (
    virus_status, poison_status, infection_status,
    shields, esquive_status, casque_status, immunite_status,
    regeneration_status, personnages_equipés
)
from personnage import PERSONNAGES
from economy import get_total_gotcoins_earned, get_balance, gotcoins_stats

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

        # Classement GotCoins
        server_lb = gotcoins_stats.get(guild_id, {})
        sorted_lb = sorted(
            server_lb.items(),
            key=lambda x: get_total_gotcoins_earned(guild_id, x[0]),
            reverse=True
        )
        rank = next((i + 1 for i, (id, _) in enumerate(sorted_lb) if id == uid), None)
        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(rank, "")

        # PV + Bouclier
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

        if member.joined_at:
            embed.add_field(
                name="📅 Membre depuis",
                value=member.joined_at.strftime("%d %B %Y à %Hh%M"),
                inline=False
            )

        # Inventaire
        item_counts = {}
        for item in user_inv:
            if isinstance(item, str):
                item_counts[item] = item_counts.get(item, 0) + 1

        if not item_counts:
            embed.add_field(name="🎒 Inventaire", value="Aucun objet.", inline=False)
        else:
            chunk_size = 4
            items = list(item_counts.items())
            chunks = [items[i:i+chunk_size] for i in range(0, len(items), chunk_size)]
            for i, chunk in enumerate(chunks):
                value = "\n".join(f"{emoji} × {count}" for emoji, count in chunk)
                embed.add_field(name="🎒 Inventaire" if i == 0 else "\u200b", value=value, inline=True)

        # États pathologiques
        now = time.time()
        status_lines = []
        for status, label, tick, emoji, note in [
            (virus_status, "Virus actif", 3600, "🦠", "-2 PV à chaque attaque + propagation."),
            (poison_status, "Empoisonnement", 1800, "🧪", "-1 dégât sur tes attaques."),
            (infection_status, "Infection", 1800, "🧟", "25% de propager une infection.")
        ]:
            data = status.get(guild_id, {}).get(uid)
            if isinstance(data, dict) and "start" in data and "duration" in data:
                elapsed = now - data["start"]
                remaining = max(0, data["duration"] - elapsed)
                next_tick = tick - (elapsed % tick)
                warning = " ⚠️" if next_tick < 300 else ""
                rem_min = int(remaining // 60)
                t_m, t_s = int(next_tick // 60), int(next_tick % 60)
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
            (casque_status, "🪖", "Casque", "½ dégâts"),
            (immunite_status, "⭐️", "Immunité", "")
        ]:
            data = bonus.get(guild_id, {}).get(uid)
            if isinstance(data, dict) and "start" in data and "duration" in data:
                elapsed = now - data["start"]
                rem_min = int(max(0, data["duration"] - elapsed) // 60)
                bonus_lines.append(f"{emoji} **{label}** — {rem_min} min restants {extra}")

        regen = regeneration_status.get(guild_id, {}).get(uid)
        if isinstance(regen, dict) and "start" in regen and "duration" in regen:
            elapsed = now - regen["start"]
            rem_min = int(max(0, regen["duration"] - elapsed) // 60)
            bonus_lines.append(f"💕 **Régénération** — {rem_min} min (+3 PV / 30 min)")

        if bonus_lines:
            bonus_embed = discord.Embed(
                title="🌀 Effets temporaires actifs",
                description="\n".join(bonus_lines),
                color=discord.Color.teal()
            )
            bonus_embed.set_footer(text="⏳ Bonus positifs actifs détectés.")
            await interaction.followup.send(embed=embed)
            await interaction.followup.send(embed=bonus_embed)
        else:
            await interaction.followup.send(embed=embed)

        # Personnage actif
        perso_nom = personnages_equipés.get(guild_id, {}).get(uid)
        if perso_nom and perso_nom in PERSONNAGES:
            collection = get_collection(guild_id, uid)
            if perso_nom in collection:
                # Numéro dans la collection (ordre rareté/faction/alpha)
                sorted_names = sorted(
                    collection.keys(),
                    key=lambda nom: (
                        {"Commun": 0, "Rare": 1, "Epique": 2, "Legendaire": 3}.get(PERSONNAGES[nom]["rarete"], 99),
                        PERSONNAGES[nom]["faction"],
                        nom
                    )
                )
                index = sorted_names.index(perso_nom) + 1
                perso_data = PERSONNAGES[perso_nom]
                image_path = perso_data.get("image")
                image_name = os.path.basename(image_path) if image_path else None
        
                embed.add_field(
                    name="🎭 Personnage équipé",
                    value=(
                        f"**#{index} – {perso_nom}**\n"
                        f"🎁 {perso_data['passif_nom']} {perso_data['emoji']}\n"
                        f"> {perso_data['passif_desc']}"
                    ),
                    inline=False
                )
        
                if image_path and os.path.exists(image_path):
                    file = discord.File(image_path, filename=image_name)
                    embed.set_image(url=f"attachment://{image_name}")
                    await interaction.followup.send(embed=embed, file=file)
                    return

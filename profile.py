# profile.py
import os
import time
import discord
from datetime import datetime, timedelta  # 🆕
from discord import app_commands

from storage import get_user_data, get_collection, hp
from data import (
    virus_status, poison_status, infection_status,
    shields, esquive_status, casque_status, immunite_status,
    regeneration_status, personnages_equipés,
    tirages  # 🆕 état des tirages journaliers (dict "guild-user" -> iso datetime)
)
from personnage import PERSONNAGES
from economy import get_total_gotcoins_earned, get_balance, gotcoins_stats


def _remaining_minutes_from_dict(data: dict) -> int:
    if not isinstance(data, dict):
        return 0
    now = time.time()
    start = data.get("start")
    duration = data.get("duration")
    if not isinstance(start, (int, float)) or not isinstance(duration, (int, float)):
        return 0
    remaining = max(0, (start + duration) - now)
    return int(remaining // 60)

def _remaining_minutes_from_expiry(expiry_ts: float) -> int:
    if not isinstance(expiry_ts, (int, float)):
        return 0
    now = time.time()
    remaining = max(0, expiry_ts - now)
    return int(remaining // 60)

def _fmt_duration_minutes(mins: int) -> str:
    if mins >= 120:
        h = mins // 60
        m = mins % 60
        return f"{h}h {m}min" if m else f"{h}h"
    return f"{mins} min"

def _rarity_sort_key(nom: str):
    p = PERSONNAGES.get(nom, {})
    ordre_r = {"Commun": 0, "Rare": 1, "Épique": 2, "Légendaire": 3}
    return (
        ordre_r.get(p.get("rarete"), 99),
        p.get("faction", "ZZZ"),
        nom
    )


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

        server_lb = gotcoins_stats.get(guild_id, {})
        sorted_lb = sorted(
            server_lb.items(),
            key=lambda x: get_total_gotcoins_earned(guild_id, x[0]),
            reverse=True
        )
        rank = next((i + 1 for i, (id_, _) in enumerate(sorted_lb) if id_ == uid), None)
        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(rank, "")

        shield_amt = shields.get(guild_id, {}).get(uid, 0)
        hp_display = f"{user_hp} / 100" + (f" + 🛡 {shield_amt}" if shield_amt > 0 else "")

        perso_nom = personnages_equipés.get(guild_id, {}).get(uid)
        faction_line = ""
        if perso_nom and perso_nom in PERSONNAGES:
            faction = PERSONNAGES[perso_nom].get("faction")
            if faction:
                faction_line = f"\n🎖 Faction : **{faction}**"

        embed = discord.Embed(
            title=f"📄 Profil GotValis de {member.display_name}{faction_line}",
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
        for it in user_inv:
            if isinstance(it, str):
                item_counts[it] = item_counts.get(it, 0) + 1

        if not item_counts:
            embed.add_field(name="🎒 Inventaire", value="Aucun objet.", inline=False)
        else:
            items = list(item_counts.items())
            chunk_size = 4
            for i in range(0, len(items), chunk_size):
                chunk = items[i:i+chunk_size]
                value = "\n".join(f"{emoji} × {count}" for emoji, count in chunk)
                embed.add_field(name="🎒 Inventaire" if i == 0 else "\u200b", value=value, inline=True)

        # 🎟️ Tickets de tirage
        ticket_count = item_counts.get("🎟️", 0)
        embed.add_field(
            name="🎟️ Tickets de tirage disponibles",
            value=f"**{ticket_count}**" if ticket_count > 0 else "Aucun",
            inline=False
        )

        # 🆕 Tirage journalier: disponible / temps restant
        key = f"{guild_id}-{uid}"
        txt_tirage = "✅ Disponible maintenant"
        if key in tirages:
            try:
                last_time = datetime.fromisoformat(tirages[key])
                delta = datetime.utcnow() - last_time
                if delta < timedelta(days=1):
                    remaining = timedelta(days=1) - delta
                    mins = int(remaining.total_seconds() // 60)
                    txt_tirage = f"⏳ Disponible dans **{_fmt_duration_minutes(mins)}**"
            except Exception:
                # si format inattendu, on considère disponible
                pass
        embed.add_field(name="🎴 Tirage journalier", value=txt_tirage, inline=False)

        # États pathologiques
        now = time.time()
        status_lines = []
        for status, label, tick, emoji, note in [
            (virus_status, "Virus actif", 3600, "🦠", "-2 PV à chaque attaque + propagation."),
            (poison_status, "Empoisonnement", 1800, "🧪", "-1 dégât sur tes attaques."),
            (infection_status, "Infection", 1800, "🧟", "25% de propager une infection."),
        ]:
            data = status.get(guild_id, {}).get(uid)
            if isinstance(data, dict) and "start" in data and "duration" in data:
                elapsed = now - data["start"]
                remaining = max(0, data["duration"] - elapsed)
                next_tick = tick - (elapsed % tick)
                rem_min = int(remaining // 60)
                t_m, t_s = int(next_tick // 60), int(next_tick % 60)
                warning = " ⚠️" if next_tick < 300 else ""
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

        esquive = esquive_status.get(guild_id, {}).get(uid)
        if isinstance(esquive, dict):
            rem = _remaining_minutes_from_dict(esquive)
            if rem > 0:
                bonus_lines.append(
                    f"💨 **Esquive améliorée** — {_fmt_duration_minutes(rem)} restants "
                    f"(+{int(esquive.get('valeur', 0.2)*100)}%)"
                )

        casque = casque_status.get(guild_id, {}).get(uid)
        if isinstance(casque, dict):
            rem = _remaining_minutes_from_dict(casque)
        else:
            rem = _remaining_minutes_from_expiry(casque)
        if rem > 0:
            bonus_lines.append(f"🪖 **Casque** — {_fmt_duration_minutes(rem)} (½ dégâts)")

        immun = immunite_status.get(guild_id, {}).get(uid)
        if isinstance(immun, dict):
            rem = _remaining_minutes_from_dict(immun)
        else:
            rem = _remaining_minutes_from_expiry(immun)
        if rem > 0:
            bonus_lines.append(f"⭐️ **Immunité** — {_fmt_duration_minutes(rem)}")

        regen = regeneration_status.get(guild_id, {}).get(uid)
        if isinstance(regen, dict):
            rem = _remaining_minutes_from_dict(regen)
            if rem > 0:
                bonus_lines.append(f"💕 **Régénération** — {_fmt_duration_minutes(rem)} (+3 PV / 30 min)")

        bonus_embed = None
        if bonus_lines:
            bonus_embed = discord.Embed(
                title="🌀 Effets temporaires actifs",
                description="\n".join(bonus_lines),
                color=discord.Color.teal()
            )
            bonus_embed.set_footer(text="⏳ Bonus positifs actifs détectés.")

        # Personnage équipé
        file = None
        if perso_nom and perso_nom in PERSONNAGES:
            collection = get_collection(guild_id, uid) or {}
            if perso_nom in collection:
                sorted_names = sorted(collection.keys(), key=_rarity_sort_key)
                index = sorted_names.index(perso_nom) + 1

                p = PERSONNAGES[perso_nom]
                passif = p.get("passif", {})
                passif_nom = passif.get("nom", "Passif")
                passif_effet = passif.get("effet", "")

                embed.add_field(
                    name="🎭 Personnage équipé",
                    value=(f"**#{index} – {perso_nom}**\n"
                           f"🎁 **{passif_nom}**\n"
                           f"> {passif_effet}"),
                    inline=False
                )

                image_path = p.get("image")
                if image_path and os.path.exists(image_path):
                    image_name = os.path.basename(image_path)
                    try:
                        file = discord.File(image_path, filename=image_name)
                        embed.set_image(url=f"attachment://{image_name}")
                    except Exception:
                        file = None

        # Envois
        if bonus_embed:
            await interaction.followup.send(embed=embed, file=file)
            await interaction.followup.send(embed=bonus_embed)
        else:
            await interaction.followup.send(embed=embed, file=file)

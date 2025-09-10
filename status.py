# status.py
# Rapport d'états (virus, poison, infection, régénération, immunité, brûlure)
# Compatible avec nos structures mixtes (dict {start,duration} OU timestamp d’expiration).

import time
import discord
from discord import app_commands

from data import (
    virus_status, poison_status, infection_status, burn_status,
    immunite_status, regeneration_status
)

# On tolère les deux API des passifs :
# - appliquer_passif_utilisateur(guild_id, user_id, contexte, données)
# - appliquer_passif(user_id, contexte, données) (shim)
try:
    from passifs import appliquer_passif_utilisateur as _passif_user
    def _APPLIQUER(user_id: str, contexte: str, données: dict):
        return _passif_user(données["guild_id"], user_id, contexte, données)
except Exception:
    try:
        from passifs import appliquer_passif as _passif_direct
        def _APPLIQUER(user_id: str, contexte: str, données: dict):
            return _passif_direct(user_id, contexte, données)
    except Exception:
        def _APPLIQUER(*_, **__):
            return None


# ------------ Helpers temps ------------
def _fmt_ms(seconds: float) -> str:
    seconds = max(0, int(seconds))
    m, s = divmod(seconds, 60)
    return f"{m}m {s}s"

def _fmt_hm(seconds: float) -> str:
    seconds = max(0, int(seconds))
    h, r = divmod(seconds, 3600)
    m = r // 60
    return f"{h}h {m}min"

def _remaining_from_dict(d: dict) -> float:
    """dict {'start': ts, 'duration': secs} -> remaining seconds"""
    if not isinstance(d, dict):
        return 0
    start = d.get("start")
    duration = d.get("duration")
    if not isinstance(start, (int, float)) or not isinstance(duration, (int, float)):
        return 0
    return max(0.0, (start + duration) - time.time())

def _remaining_from_expiry(expiry_ts: float) -> float:
    """float expiry_ts -> remaining seconds"""
    if not isinstance(expiry_ts, (int, float)):
        return 0
    return max(0.0, expiry_ts - time.time())

def _tick_info(start_ts: float, tick_secs: int) -> float:
    """temps restant avant le prochain 'tick' à partir de start_ts, période tick_secs"""
    if not isinstance(start_ts, (int, float)) or tick_secs <= 0:
        return 0
    elapsed = max(0.0, time.time() - start_ts)
    return tick_secs - (elapsed % tick_secs)


def register_status_command(bot):
    @bot.tree.command(
        name="status",
        description="Voir les effets GotValis actifs (virus, poison, infection, régénération, immunité, brûlure)."
    )
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
        embed.set_thumbnail(url=member.display_avatar.url if member.display_avatar else discord.Embed.Empty)

        # ⭐️ Immunité (timestamp OU dict)
        im = immunite_status.get(guild_id, {}).get(user_id)
        if isinstance(im, dict):
            im_rem = _remaining_from_dict(im)
        else:
            im_rem = _remaining_from_expiry(im)

        if im_rem > 0:
            embed.add_field(
                name="⭐️ Immunité active",
                value=f"• Temps restant : **{_fmt_ms(im_rem)}**",
                inline=False
            )
        else:
            embed.add_field(name="⭐️ Immunité", value="❌ Aucune", inline=False)

        # 💕 Régénération (dict attendu dans notre système, mais on tolère rien/None)
        regen = regeneration_status.get(guild_id, {}).get(user_id)
        if isinstance(regen, dict):
            rem = _remaining_from_dict(regen)
            if rem > 0:
                next_tick = _tick_info(regen.get("start", now), 1800)
                warn = " ⚠️" if next_tick < 300 else ""
                embed.add_field(
                    name="💕 Régénération cellulaire",
                    value=(
                        f"• Temps restant : **{_fmt_hm(rem)}**\n"
                        f"• Prochain soin : **dans {_fmt_ms(next_tick)}**{warn}\n"
                        f"• ✨ Régénère **3 PV toutes les 30 min**"
                    ),
                    inline=False
                )
            else:
                embed.add_field(name="💕 Régénération", value="❌ Aucune", inline=False)
        else:
            embed.add_field(name="💕 Régénération", value="❌ Aucune", inline=False)

        # 🦠 Virus (dict)
        virus = virus_status.get(guild_id, {}).get(user_id)
        if isinstance(virus, dict):
            rem = _remaining_from_dict(virus)
            if rem > 0:
                tick = _tick_info(virus.get("start", now), 3600)
                warn = " ⚠️" if tick < 300 else ""
                embed.add_field(
                    name="🦠 Infection virale",
                    value=(
                        f"• Temps restant : **{_fmt_hm(rem)}**\n"
                        f"• Prochain dégât : **dans {_fmt_ms(tick)}**{warn}\n"
                        f"• ⚔️ Vous perdez **2 PV** par attaque et propagez le virus.\n"
                        f"💉 Utilisez un vaccin via `/heal`."
                    ),
                    inline=False
                )
            else:
                embed.add_field(name="🦠 Infection virale", value="✅ Aucun virus détecté", inline=False)
        else:
            embed.add_field(name="🦠 Infection virale", value="✅ Aucun virus détecté", inline=False)

        # 🧪 Poison (dict)
        poison = poison_status.get(guild_id, {}).get(user_id)
        if isinstance(poison, dict):
            rem = _remaining_from_dict(poison)
            if rem > 0:
                tick = _tick_info(poison.get("start", now), 1800)
                warn = " ⚠️" if tick < 300 else ""
                embed.add_field(
                    name="🧪 Empoisonnement",
                    value=(
                        f"• Temps restant : **{_fmt_hm(rem)}**\n"
                        f"• Prochain dégât : **dans {_fmt_ms(tick)}**{warn}\n"
                        f"• ⚔️ Vos attaques infligent **1 dégât en moins**."
                    ),
                    inline=False
                )
            else:
                embed.add_field(name="🧪 Empoisonnement", value="✅ Aucun poison détecté", inline=False)
        else:
            embed.add_field(name="🧪 Empoisonnement", value="✅ Aucun poison détecté", inline=False)

        # 🔥 Brûlure (dict)
        brule = burn_status.get(guild_id, {}).get(user_id)
        if isinstance(brule, dict) and brule.get("actif"):
            ticks_restants = int(brule.get("ticks_restants", 0))
            next_tick = max(0.0, brule.get("next_tick", now) - now)
            # 3 ticks au total sur 3h ; si on n’a pas la durée exacte on affiche les ticks restants
            embed.add_field(
                name="🔥 Brûlure",
                value=(
                    f"• Ticks restants : **{ticks_restants}**\n"
                    f"• Prochain dégât : **dans {_fmt_ms(next_tick)}**\n"
                    f"• ⚔️ Inflige **1 PV** par heure, pendant **3h**."
                ),
                inline=False
            )
        else:
            embed.add_field(name="🔥 Brûlure", value="✅ Aucune lésion thermique", inline=False)

        # 🧟 Infection GotValis (dict) — gestion immunité via passif (Anna, Abomination…)
        inf = infection_status.get(guild_id, {}).get(user_id)
        is_immune = False
        try:
            res = _APPLIQUER(user_id, "tick_infection", {"guild_id": guild_id, "cible_id": user_id})
            if isinstance(res, dict) and res.get("annuler_degats"):
                is_immune = True
        except Exception:
            is_immune = False

        if isinstance(inf, dict) and not is_immune:
            rem = _remaining_from_dict(inf)
            if rem > 0:
                tick = _tick_info(inf.get("start", now), 1800)
                warn = " ⚠️" if tick < 300 else ""
                embed.add_field(
                    name="🧟 Infection GotValis",
                    value=(
                        f"• Temps restant : **{_fmt_hm(rem)}**\n"
                        f"• Prochain dégât : **dans {_fmt_ms(tick)}**{warn}\n"
                        f"• ⚔️ **25%** de propager l’infection en attaquant.\n"
                        f"• 😵 **2 dégâts** toutes les 30 minutes."
                    ),
                    inline=False
                )
            else:
                embed.add_field(name="🧟 Infection GotValis", value="✅ Aucune infection détectée", inline=False)
        else:
            embed.add_field(name="🧟 Infection GotValis", value="✅ Aucune infection détectée", inline=False)

        embed.set_footer(text="📡 Analyse en temps réel via GotValis.")
        await interaction.response.send_message(embed=embed, ephemeral=True)

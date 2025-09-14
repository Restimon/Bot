# cogs/info_cog.py
from __future__ import annotations

import collections
import discord
from discord import app_commands
from discord.ext import commands

# --- imports tolérants ---
try:
    from data import storage  # doit fournir get_user_data(), save_data(), hp, etc.
except Exception:
    storage = None

# economy_db: on essaie d'exister proprement même s'il manque
try:
    from data import economy_db
except Exception:
    economy_db = None

# stats_db pour “carrière” (facultatif)
try:
    from data import stats_db
except Exception:
    stats_db = None


def _fmt_inv(inv: list[str], max_lines: int = 10) -> str:
    """Compresse l’inventaire: emoji × count, tri par fréquence puis emoji."""
    # on ne compte que les strings (émoticônes d’objets)
    items = [x for x in inv if isinstance(x, str)]
    if not items:
        return "—"
    ctr = collections.Counter(items)
    # tri: d’abord quantité desc, puis clé
    pairs = sorted(ctr.items(), key=lambda kv: (-kv[1], kv[0]))
    lines = [f"{emo} × {qty}" for emo, qty in pairs[:max_lines]]
    rest = len(pairs) - len(lines)
    if rest > 0:
        lines.append(f"… (+{rest} types)")
    return "\n".join(lines)


async def _get_balances(guild_id: int, user_id: int):
    """
    Retourne (coins_actuels, tickets, coins_carreer) en essayant economy_db/stats_db.
    Fallbacks: 0 / comptage 🎟️ / None.
    """
    coins_now = 0
    tickets = 0
    coins_total = None  # carrière

    if economy_db:
        try:
            coins_now = await economy_db.get_balance(guild_id, user_id)  # doit renvoyer int
        except Exception:
            coins_now = 0
        try:
            # si vous avez une autre signature, adaptez ici
            tickets = await economy_db.get_tickets(guild_id, user_id)
        except Exception:
            tickets = 0

    if stats_db:
        try:
            # si vous avez un cumul de gains en base
            coins_total = await stats_db.get_total_coins(guild_id, user_id)
        except Exception:
            coins_total = None

    # Fallback “tickets” si pas d’économie dédiée: compte 🎟️ dans l’inventaire
    if tickets == 0 and storage is not None:
        try:
            inv, _, _ = storage.get_user_data(str(guild_id), str(user_id))
            tickets = sum(1 for x in inv if x == "🎟️")
        except Exception:
            pass

    return coins_now, tickets, coins_total


class InfoCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="profile", description="Affiche ton profil GotValis")
    async def profile(self, interaction: discord.Interaction, member: discord.Member | None = None):
        user = member or interaction.user
        gid = interaction.guild.id if interaction.guild else 0

        # Données storage (PV + inventaire)
        pv_now = 100
        pv_max = 100
        inv = []
        try:
            if storage:
                # hp: data.storage.hp[guild_id][user_id] si dispo
                gid_s, uid_s = str(gid), str(user.id)
                if hasattr(storage, "hp"):
                    pv_now = int(storage.hp.get(gid_s, {}).get(uid_s, 100))
                inv, _, _ = storage.get_user_data(gid_s, uid_s)
        except Exception:
            pass

        coins_now, tickets, coins_total = await _get_balances(gid, user.id)

        embed = discord.Embed(
            title=f"Profil GotValis de {user.display_name}",
            description="Analyse médicale et opérationnelle en cours…",
            color=discord.Color.blurple(),
        )
        embed.set_thumbnail(url=user.display_avatar.replace(size=256).url if user.display_avatar else discord.Embed.Empty)

        # Points de vie
        embed.add_field(name="❤️ Points de vie", value=f"{pv_now} / {pv_max}", inline=False)

        # Ressources
        res_lines = []
        if coins_total is not None:
            res_lines.append(f"💰 GotCoins totaux (carrière)\n**{coins_total}**")
        else:
            res_lines.append("💰 GotCoins totaux (carrière)\n—")
        res_lines.append(f"💳 Solde actuel (dépensable)\n**{coins_now}**")
        res_lines.append(f"🎟️ Tickets\n**{tickets}**")
        embed.add_field(name="📦 Ressources", value="\n".join(res_lines), inline=False)

        # Classement (placeholder simple; adaptez si vous avez un vrai leaderboard)
        try:
            joined = user.joined_at.strftime("%d %B %Y à %Hh%M") if user.joined_at else "—"
        except Exception:
            joined = "—"

        embed.add_field(name="📅 Membre depuis", value=joined, inline=False)

        # Inventaire
        inv_text = _fmt_inv(inv)
        embed.add_field(name="🎒 Inventaire", value=inv_text, inline=False)

        # État pathologique (à relier à votre module d’effets si besoin)
        embed.add_field(name="🧪 État pathologique", value="Aucun effet négatif détecté.", inline=False)

        await interaction.response.send_message(embed=embed)

    # alias /info pour ceux qui sont habitués
    @app_commands.command(name="info", description="Alias de /profile")
    async def info_alias(self, interaction: discord.Interaction):
        await self.profile.callback(self, interaction)  # appelle la même logique


async def setup(bot: commands.Bot):
    await bot.add_cog(InfoCog(bot))

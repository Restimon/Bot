# cogs/leaderboard_cog.py
from __future__ import annotations

from typing import Dict, List, Tuple, Optional

import discord
from discord import app_commands
from discord.ext import commands


# ─────────────────────────────────────────────────────────
# Imports souples vers data.storage
# ─────────────────────────────────────────────────────────
_storage = None
_get_user_data = None
_save_data = None

try:
    from data import storage as _storage  # type: ignore
except Exception:
    _storage = None

try:
    from data.storage import get_user_data as _get_user_data  # type: ignore
except Exception:
    _get_user_data = None

try:
    from data.storage import save_data as _save_data  # type: ignore
except Exception:
    _save_data = None


def _get_leaderboard(gid: int) -> Dict[str, Dict[str, int]]:
    """
    Retourne un dict {user_id: {points, kills, deaths}} pour CE serveur.
    Crée la structure si absente (et la laisse en mémoire).
    """
    if _storage is not None:
        if not hasattr(_storage, "leaderboard") or not isinstance(getattr(_storage, "leaderboard"), dict):
            setattr(_storage, "leaderboard", {})
        lb = getattr(_storage, "leaderboard")
        lb.setdefault(str(gid), {})
        return lb[str(gid)]

    # Fallback RAM
    if not hasattr(_get_leaderboard, "_mem"):
        _get_leaderboard._mem: Dict[str, Dict[str, Dict[str, int]]] = {}
    mem = _get_leaderboard._mem  # type: ignore
    mem.setdefault(str(gid), {})
    return mem[str(gid)]


def _get_equipment(gid: int, uid: int) -> Optional[Dict]:
    """
    Essaie de lire storage.equipment[guild_id][user_id] si dispo (optionnel).
    """
    if _storage is None:
        return None
    equip = getattr(_storage, "equipment", None)
    if not isinstance(equip, dict):
        return None
    g = equip.get(str(gid))
    if not isinstance(g, dict):
        return None
    e = g.get(str(uid))
    return e if isinstance(e, dict) else None


def _get_user(guild: discord.Guild, user_id: int) -> str:
    m = guild.get_member(user_id)
    return m.display_name if m else f"User {user_id}"


def _get_user_data_safe(gid: int, uid: int):
    """
    (inv, coins, perso) si possible, sinon fallbacks raisonnables.
    """
    if callable(_get_user_data):
        try:
            inv, coins, perso = _get_user_data(str(gid), str(uid))  # type: ignore
            return inv or [], int(coins or 0), perso
        except Exception:
            pass
    return [], 0, None


def _rank_sorted(gid: int) -> List[Tuple[int, Dict[str, int]]]:
    """
    Liste triée des (user_id, stats) en fonction des critères :
    points DESC, kills DESC, deaths ASC, user_id ASC.
    """
    lb = _get_leaderboard(gid)
    items: List[Tuple[int, Dict[str, int]]] = []
    for uid_str, stats in lb.items():
        try:
            uid = int(uid_str)
        except Exception:
            continue
        if not isinstance(stats, dict):
            continue
        pts = int(stats.get("points", 0) or 0)
        k = int(stats.get("kills", 0) or 0)
        d = int(stats.get("deaths", 0) or 0)
        items.append((uid, {"points": pts, "kills": k, "deaths": d}))

    items.sort(key=lambda x: (-x[1]["points"], -x[1]["kills"], x[1]["deaths"], x[0]))
    return items


def _find_rank(sorted_list: List[Tuple[int, Dict[str, int]]], uid: int) -> Optional[int]:
    for i, (u, _) in enumerate(sorted_list, start=1):
        if u == uid:
            return i
    return None


class LeaderboardCog(commands.Cog):
    """Classement par serveur + fiche rang & équipement."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ─────────────────────────────────────────────────────────
    # /leaderboard
    # ─────────────────────────────────────────────────────────
    @app_commands.command(name="leaderboard", description="Affiche le classement du serveur.")
    @app_commands.describe(page="Page (10 par page)")
    async def leaderboard(self, interaction: discord.Interaction, page: int = 1):
        if not interaction.guild:
            return await interaction.response.send_message("Commande serveur uniquement.", ephemeral=True)

        await interaction.response.defer(ephemeral=False, thinking=True)

        gid = interaction.guild.id
        rows = _rank_sorted(gid)
        if not rows:
            return await interaction.followup.send("Aucune donnée de classement pour ce serveur.")

        page = max(1, page)
        per_page = 10
        start = (page - 1) * per_page
        chunk = rows[start:start + per_page]
        if not chunk:
            return await interaction.followup.send("Cette page est vide.")

        e = discord.Embed(
            title=f"🏆 Classement — {interaction.guild.name}",
            description=f"Page **{page}**",
            color=discord.Color.gold(),
        )

        lines: List[str] = []
        for i, (uid, stats) in enumerate(chunk, start=start + 1):
            name = _get_user(interaction.guild, uid)
            inv, coins, perso = _get_user_data_safe(gid, uid)
            perso_name = perso.get("nom") if isinstance(perso, dict) else "—"
            k = stats["kills"]
            d = stats["deaths"]
            pts = stats["points"]

            # Petit résumé équipement si dispo
            equip = _get_equipment(gid, uid)
            if isinstance(equip, dict) and equip:
                # Essaie de montrer 2-3 slots connus (ex: arme, armure) ou tous les emojis
                # On agrège rapidement :
                parts = []
                for key, val in equip.items():
                    if isinstance(val, str):
                        parts.append(val)
                equip_txt = (" ".join(parts[:6])) if parts else "—"
            else:
                equip_txt = "—"

            lines.append(
                f"**#{i}** — **{name}**  •  **{pts}** pts  •  🗡 {k} / 💀 {d}  •  💰 {coins}\n"
                f"   Perso: *{perso_name}*  •  Équipement: {equip_txt}"
            )

        e.description = "\n\n".join(lines)
        await interaction.followup.send(embed=e)

    # ─────────────────────────────────────────────────────────
    # /rank
    # ─────────────────────────────────────────────────────────
    @app_commands.command(name="rank", description="Affiche ta position et ton équipement.")
    @app_commands.describe(user="Voir le rang d'un autre joueur")
    async def rank(self, interaction: discord.Interaction, user: Optional[discord.Member] = None):
        if not interaction.guild:
            return await interaction.response.send_message("Commande serveur uniquement.", ephemeral=True)

        await interaction.response.defer(ephemeral=True, thinking=True)

        member = user or interaction.user
        gid = interaction.guild.id
        uid = member.id

        rows = _rank_sorted(gid)
        if not rows:
            return await interaction.followup.send("Aucune donnée pour ce serveur.", ephemeral=True)

        rank_pos = _find_rank(rows, uid)
        stats = next((s for u, s in rows if u == uid), {"points": 0, "kills": 0, "deaths": 0})
        inv, coins, perso = _get_user_data_safe(gid, uid)
        perso_name = perso.get("nom") if isinstance(perso, dict) else "—"

        equip = _get_equipment(gid, uid)
        if isinstance(equip, dict) and equip:
            parts = []
            for key, val in equip.items():
                if isinstance(val, str):
                    parts.append(val)
            equip_txt = (" ".join(parts[:12])) if parts else "—"
        else:
            equip_txt = "—"

        e = discord.Embed(
            title=f"📊 Profil — {member.display_name}",
            color=discord.Color.blurple(),
        )
        e.set_thumbnail(url=member.display_avatar.url)
        e.add_field(name="Rang", value=f"**#{rank_pos}**" if rank_pos else "—", inline=True)
        e.add_field(name="Points", value=str(stats.get("points", 0)), inline=True)
        e.add_field(name="Kills / Deaths", value=f"{stats.get('kills', 0)} / {stats.get('deaths', 0)}", inline=True)
        e.add_field(name="GotCoins", value=str(coins), inline=True)
        e.add_field(name="Personnage", value=perso_name, inline=True)
        e.add_field(name="Équipement", value=equip_txt, inline=False)

        await interaction.followup.send(embed=e, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(LeaderboardCog(bot))

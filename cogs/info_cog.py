# cogs/info_cog.py
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional, Tuple

from data import storage


async def _get_rank_by_coins(user_id: int) -> Tuple[int, int]:
    """
    Retourne (rang, total_joueurs) selon les GotCoins ACTUELS (richesse).
    Si l'utilisateur n'existe pas encore, on le crée avant de calculer.
    """
    await storage.ensure_player(user_id)
    data = await storage.load_all()
    players = data.get("players", {})

    # Trie par coins décroissant
    classement = sorted(
        players.items(),
        key=lambda kv: int(kv[1].get("coins", 0)),
        reverse=True
    )
    total = len(classement)
    rang = total  # fallback
    for idx, (uid, pdata) in enumerate(classement, start=1):
        if uid == str(user_id):
            rang = idx
            break
    return rang, total


def _fmt_int(n: int) -> str:
    return f"{n:,}".replace(",", " ")


class InfoCog(commands.Cog):
    """Profil GotValis : fiche d'identité complète d'un joueur."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="info",
        description="Affiche ton profil GotValis (ou celui d’un autre joueur)."
    )
    @app_commands.describe(membre="Le joueur dont tu veux voir le profil.")
    async def info(self, interaction: discord.Interaction, membre: Optional[discord.Member] = None):
        user: discord.Member = membre or interaction.user

        # S'assure que le joueur existe, puis récupère toutes ses données
        pdata = await storage.ensure_player(user.id)
        coins = int(pdata.get("coins", 0))
        tickets = int(pdata.get("tickets", 0))
        hp = int(pdata.get("hp", 100))
        shield = int(pdata.get("shield", 0))
        equipped = pdata.get("equipped_character") or "Aucun"

        stats = pdata.get("stats", {})
        dmg = int(stats.get("damage", 0))
        heal = int(stats.get("healing", 0))
        kills = int(stats.get("kills", 0))
        deaths = int(stats.get("deaths", 0))

        # Classement (rang) par GotCoins actuels
        rang, total = await _get_rank_by_coins(user.id)

        # Embed au style "RP GotValis"
        title = f"Profil — {user.display_name}"
        desc = (
            "📡 **Dossier GotValis** ouvert.\n"
            "Les paramètres vitaux et ressources ont été synchronisés.\n"
            "Toute anomalie sera signalée au réseau."
        )
        emb = discord.Embed(
            title=title,
            description=desc,
            color=discord.Color.blurple()
        )

        # Avatar + footer
        if user.display_avatar:
            emb.set_thumbnail(url=user.display_avatar.url)

        emb.set_footer(text=f"ID: {user.id}")

        # Lignes principales
        emb.add_field(
            name="🩺 Vitales",
            value=f"❤️ PV: **{hp}/100**\n🛡 PB: **{shield}**",
            inline=True
        )
        emb.add_field(
            name="💰 Ressources",
            value=f"🪙 GotCoins: **{_fmt_int(coins)}**\n🎫 Tickets: **{tickets}**",
            inline=True
        )
        emb.add_field(
            name="🏷️ Équipement",
            value=f"Personnage: **{equipped}**",
            inline=False
        )

        # Classement
        emb.add_field(
            name="🏆 Classement",
            value=f"Rang richesse: **#{rang}** / {total}",
            inline=False
        )

        # Statistiques de terrain
        emb.add_field(
            name="📊 Historique d’opérations",
            value=(
                f"🔺 Dégâts infligés: **{_fmt_int(dmg)}**\n"
                f"🔻 Soins prodigués: **{_fmt_int(heal)}**\n"
                f"☠️ Kills: **{_fmt_int(kills)}**\n"
                f"💀 Morts: **{_fmt_int(deaths)}**"
            ),
            inline=False
        )

        # Effets actifs (liste courte)
        eff = pdata.get("effects", {})
        if isinstance(eff, dict) and eff:
            eff_list = ", ".join(sorted(eff.keys()))
            emb.add_field(name="🧪 Effets actifs", value=f"`{eff_list}`", inline=False)

        # Cooldowns (optionnel à l’affichage si utile)
        cds = pdata.get("cooldowns", {})
        if isinstance(cds, dict) and cds:
            # Affiche seulement ceux qui existent
            mapped = []
            for key in ("daily", "attack"):
                ts = cds.get(key)
                if ts:
                    mapped.append(f"• **{key}**: <t:{int(ts)}:R>")
            if mapped:
                emb.add_field(name="⏳ Cooldowns", value="\n".join(mapped), inline=False)

        await interaction.response.send_message(embed=emb)


async def setup(bot: commands.Bot):
    await bot.add_cog(InfoCog(bot))

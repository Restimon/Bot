# cogs/admin_cog.py
from __future__ import annotations

from typing import List

import discord
from discord.ext import commands
from discord import app_commands

# Persistance (helpers officiels)
from data.storage import (
    set_leaderboard_channel,
    get_leaderboard_channel,
)

from inventory_db import add_item

# Catalogue d’objets (emoji -> fiche). Optionnel si utils.py n’est pas présent.
try:
    from utils import OBJETS  # type: ignore
except Exception:
    OBJETS = {}

# ─────────────────────────────────────────────────────────────
# Autocomplete items (tous les items connus du catalogue)
# ─────────────────────────────────────────────────────────────
async def ac_all_items(interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
    cur = (current or "").strip().lower()
    out: List[app_commands.Choice[str]] = []
    for emoji, info in OBJETS.items():
        try:
            typ = str(info.get("type", "") or "")
            label = typ
            if typ == "attaque":
                # différentes clés possibles dans tes fiches
                for k in ("degats", "dmg", "value", "valeur"):
                    if k in info:
                        try:
                            d = int(info.get(k, 0) or 0)
                            if d:
                                label = f"attaque {d}"
                                break
                        except Exception:
                            pass
            elif typ == "attaque_chaine":
                d1 = int(info.get("degats_principal", info.get("dmg_main", info.get("valeur", 0))) or 0)
                d2 = int(info.get("degats_secondaire", info.get("dmg_chain", 0)) or 0)
                label = f"attaque {d1}+{d2}" if d1 or d2 else "attaque chaîne"
            elif typ == "soin":
                s = int(info.get("soin", info.get("value", info.get("valeur", 0))) or 0)
                label = f"soin {s}" if s else "soin"
            elif typ in ("poison", "infection", "brulure", "virus"):
                d = int(info.get("degats", info.get("value", info.get("valeur", 0))) or 0)
                itv = int(info.get("intervalle", info.get("interval", 60)) or 60)
                label = f"{typ} {d}/{max(1, itv)//60}m" if d else f"{typ}/{max(1, itv)//60}m"
            elif typ == "regen":
                v = int(info.get("valeur", info.get("value", 0)) or 0)
                itv = int(info.get("intervalle", info.get("interval", 60)) or 60)
                label = f"regen +{v}/{max(1, itv)//60}m" if v else "regen"
            elif typ == "bouclier":
                val = int(info.get("valeur", info.get("value", 0)) or 0)
                label = f"bouclier {val}" if val else "bouclier"
        except Exception:
            label = "objet"

        name = f"{emoji} • {label}"
        if not cur or cur in name.lower():
            out.append(app_commands.Choice(name=name[:100], value=emoji))
            if len(out) >= 20:
                break
    return out


class AdminCog(commands.Cog):
    """Commandes Admin (réservées aux administrateurs)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ─────────────────────────────────────────────────────────
    # Leaderboard: canal cible + reset
    # (Le rendu / mise à jour est géré par un autre cog de leaderboard)
    # ─────────────────────────────────────────────────────────
    @app_commands.default_permissions(administrator=True)
    @app_commands.command(
        name="admin_set_leaderboard_channel",
        description="(Admin) Définit le salon où le leaderboard persistant sera affiché."
    )
    @app_commands.describe(channel="Le salon cible")
    async def admin_set_leaderboard_channel(self, inter: discord.Interaction, channel: discord.TextChannel):
        if not inter.guild:
            return await inter.response.send_message("❌ À utiliser dans un serveur.", ephemeral=True)

        await inter.response.defer(ephemeral=True, thinking=True)
        # Persistance via storage helpers (synchro interne)
        set_leaderboard_channel(inter.guild.id, channel.id)

        await inter.followup.send(f"✅ Salon du leaderboard défini sur {channel.mention}.", ephemeral=True)

    @app_commands.default_permissions(administrator=True)
    @app_commands.command(
        name="admin_clear_leaderboard",
        description="(Admin) Supprime la configuration de leaderboard (canal mémorisé)."
    )
    async def admin_clear_leaderboard(self, inter: discord.Interaction):
        if not inter.guild:
            return await inter.response.send_message("❌ À utiliser dans un serveur.", ephemeral=True)

        await inter.response.defer(ephemeral=True, thinking=True)
        # Clear en passant None
        set_leaderboard_channel(inter.guild.id, None)
        await inter.followup.send("🗑️ Configuration du leaderboard effacée pour ce serveur.", ephemeral=True)

    @app_commands.default_permissions(administrator=True)
    @app_commands.command(
        name="admin_show_leaderboard_channel",
        description="(Admin) Affiche le salon actuellement configuré pour le leaderboard."
    )
    async def admin_show_leaderboard_channel(self, inter: discord.Interaction):
        if not inter.guild:
            return await inter.response.send_message("❌ À utiliser dans un serveur.", ephemeral=True)

        chan_id = get_leaderboard_channel(inter.guild.id)
        if chan_id:
            ch = inter.guild.get_channel(chan_id)
            if isinstance(ch, (discord.TextChannel, discord.Thread, discord.ForumChannel)):
                return await inter.response.send_message(f"📍 Salon configuré : {ch.mention}", ephemeral=True)
            return await inter.response.send_message(f"📍 Salon configuré : <#{chan_id}> (introuvable ?)", ephemeral=True)
        return await inter.response.send_message("ℹ️ Aucun salon configuré.", ephemeral=True)

    # ─────────────────────────────────────────────────────────
    # Petits utilitaires admin
    # ─────────────────────────────────────────────────────────
    @app_commands.default_permissions(administrator=True)
    @app_commands.command(name="admin_ping", description="(Admin) Ping de santé du bot.")
    async def admin_ping(self, inter: discord.Interaction):
        await inter.response.send_message("Pong ✅", ephemeral=True)

    # ─────────────────────────────────────────────────────────
    # NEW: Give d’items
    # ─────────────────────────────────────────────────────────
    @app_commands.command(name="admin_give_item", description="(Admin) Donne un objet à un joueur.")
    @app_commands.describe(
        cible="Joueur à qui donner l'objet",
        objet="Emoji de l'objet (autocomplete)",
        quantite="Quantité à donner (min 1)",
        silencieux="Si activé, la réponse est éphémère (par défaut: oui)",
    )
    @app_commands.autocomplete(objet=ac_all_items)
    @app_commands.default_permissions(administrator=True)
    async def admin_give_item(
        self,
        interaction: discord.Interaction,
        cible: discord.Member,
        objet: str,
        quantite: app_commands.Range[int, 1, 999] = 1,
        silencieux: bool = True,
    ):
        if not interaction.guild:
            return await interaction.response.send_message("Commande serveur uniquement.", ephemeral=True)

        if objet not in OBJETS:
            return await interaction.response.send_message(
                "Objet inconnu. Utilise l’autocomplete pour sélectionner un emoji valide.",
                ephemeral=True,
            )

        await add_item(cible.id, objet, int(quantite))

        info = OBJETS.get(objet) or {}
        typ = info.get("type", "objet")
        desc = (
            f"• Cible : {cible.mention}\n"
            f"• Objet : **{objet}** (*{typ}*)\n"
            f"• Quantité : **{quantite}**"
        )

        # ping LB live s’il existe (optionnel)
        try:
            from cogs.leaderboard_live import schedule_lb_update
            schedule_lb_update(self.bot, interaction.guild.id, "admin_give_item")
        except Exception:
            pass

        embed = discord.Embed(
            title="✅ Item attribué",
            description=desc,
            color=discord.Color.green()
        )
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=silencieux)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=silencieux)


async def setup(bot: commands.Bot):
    await bot.add_cog(AdminCog(bot))

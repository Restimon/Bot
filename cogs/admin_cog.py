# cogs/admin_cog.py
from __future__ import annotations

from typing import List

import discord
from discord.ext import commands
from discord import app_commands

from data import storage
from inventory_db import add_item

# Catalogue d’objets (emoji -> fiche). Optionnel si utils.py n’est pas présent.
try:
    from utils import OBJETS  # type: ignore
except Exception:
    OBJETS = {}

LEADERBOARD_KEY = "leaderboard"  # dans data.json: ["by_guild"][guild_id][LEADERBOARD_KEY] = {channel_id, message_id}


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
                d = int(info.get("degats", 0) or 0)
                if d:
                    label = f"attaque {d}"
            elif typ == "attaque_chaine":
                d1 = int(info.get("degats_principal", 0) or 0)
                d2 = int(info.get("degats_secondaire", 0) or 0)
                label = f"attaque {d1}+{d2}"
            elif typ == "soin":
                s = int(info.get("soin", 0) or 0)
                label = f"soin {s}" if s else "soin"
            elif typ in ("poison", "infection", "brulure", "virus"):
                d = int(info.get("degats", 0) or 0)
                itv = int(info.get("intervalle", 60) or 60)
                label = f"{typ} {d}/{max(1, itv)//60}m"
            elif typ == "regen":
                v = int(info.get("valeur", 0) or 0)
                itv = int(info.get("intervalle", 60) or 60)
                label = f"regen +{v}/{max(1, itv)//60}m"
            elif typ == "bouclier":
                val = int(info.get("valeur", 0) or 0)
                label = f"bouclier {val}"
        except Exception:
            label = "objet"

        name = f"{emoji} • {label}"
        if not cur or cur in name.lower():
            out.append(app_commands.Choice(name=name, value=emoji))
            if len(out) >= 20:
                break
    return out


class AdminCog(commands.Cog):
    """Commandes Admin (réservées aux administrateurs)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ─────────────────────────────────────────────────────────
    # Utils internes stockage
    # ─────────────────────────────────────────────────────────
    def _get_guild_bucket(self, guild_id: int) -> dict:
        # Compatibilité : storage.load_data / storage.save_data (synchro)
        data = storage.load_data()
        by_guild = data.setdefault("by_guild", {})
        bucket = by_guild.setdefault(str(guild_id), {})
        return bucket

    def _save_guild_bucket(self, guild_id: int, bucket: dict) -> None:
        data = storage.load_data()
        data.setdefault("by_guild", {})[str(guild_id)] = bucket
        storage.save_data(data)

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
        await inter.response.defer(ephemeral=True, thinking=True)
        bucket = self._get_guild_bucket(inter.guild_id)
        lb = bucket.setdefault(LEADERBOARD_KEY, {})
        lb["channel_id"] = channel.id
        # on ne crée pas encore le message; le cog du leaderboard s’en chargera si besoin
        self._save_guild_bucket(inter.guild_id, bucket)
        await inter.followup.send(f"✅ Salon du leaderboard défini sur {channel.mention}.", ephemeral=True)

    @app_commands.default_permissions(administrator=True)
    @app_commands.command(
        name="admin_clear_leaderboard",
        description="(Admin) Supprime les infos de leaderboard (canal/message mémorisés)."
    )
    async def admin_clear_leaderboard(self, inter: discord.Interaction):
        await inter.response.defer(ephemeral=True, thinking=True)
        bucket = self._get_guild_bucket(inter.guild_id)
        if LEADERBOARD_KEY in bucket:
            del bucket[LEADERBOARD_KEY]
            self._save_guild_bucket(inter.guild_id, bucket)
            await inter.followup.send("🗑️ Données leaderboard effacées pour ce serveur.", ephemeral=True)
        else:
            await inter.followup.send("ℹ️ Aucune donnée leaderboard à effacer.", ephemeral=True)

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

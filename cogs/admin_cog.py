# cogs/admin_cog.py
from __future__ import annotations

from typing import List

import discord
from discord.ext import commands
from discord import app_commands

# Persistance (helpers officiels)
try:
    from data.storage import (
        set_leaderboard_channel,
        get_leaderboard_channel,
    )
except Exception:
    # Stubs si le module n'est pas dispo (évite les crashs au boot)
    def set_leaderboard_channel(gid: int, cid: int | None) -> None: ...
    def get_leaderboard_channel(gid: int) -> int | None: return None

# DB inventaire
from inventory_db import add_item

# Catalogue d’objets (emoji -> fiche)
try:
    from utils import OBJETS  # type: ignore
except Exception:
    OBJETS = {}

# ✅ Types autorisés à apparaître dans l’autocomplete admin
ALLOWED_TYPES = {
    "attaque", "attaque_chaine",
    "virus", "poison", "infection", "brulure",
    "soin", "regen",
    "mysterybox", "vol", "vaccin",
    "bouclier", "esquive+", "reduction", "immunite",
}

# ─────────────────────────────────────────────────────────────
# Autocomplete items (propre, sans “soin_autre” & co)
# ─────────────────────────────────────────────────────────────
async def ac_all_items(interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
    cur = (current or "").strip().lower()
    out: List[app_commands.Choice[str]] = []

    for emoji, info in (OBJETS or {}).items():
        info = info or {}
        typ = str(info.get("type") or "")

        # Filtre : on ne propose que les vrais objets jouables
        if typ not in ALLOWED_TYPES:
            continue

        # Fabrique un libellé court & utile
        try:
            label = typ
            if typ == "attaque":
                for k in ("degats", "dmg", "value", "valeur"):
                    if k in info:
                        d = int(info.get(k, 0) or 0)
                        if d:
                            label = f"attaque {d}"
                            break
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
            elif typ == "esquive+":
                val = info.get("valeur", 0)
                label = f"esquive +{int(val*100)}%" if isinstance(val, (int, float)) else "esquive+"
            elif typ == "reduction":  # 🪖
                val = info.get("valeur", 0.5)
                label = f"casque -{int(val*100)}% dmg" if isinstance(val, (int, float)) else "casque"
            elif typ == "immunite":
                label = "immunité"
        except Exception:
            label = typ or "objet"

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
    # Leaderboard : configuration et actions liées
    # ─────────────────────────────────────────────────────────
    @app_commands.default_permissions(administrator=True)
    @app_commands.command(
        name="lb_set",
        description="(Admin) Définit le salon du leaderboard persistant et le poste/édite immédiatement."
    )
    @app_commands.describe(channel="Le salon où afficher le leaderboard")
    async def lb_set(self, inter: discord.Interaction, channel: discord.TextChannel):
        if not inter.guild:
            return await inter.response.send_message("❌ À utiliser dans un serveur.", ephemeral=True)

        set_leaderboard_channel(inter.guild.id, channel.id)

        await inter.response.defer(ephemeral=True, thinking=True)
        try:
            from cogs.leaderboard_live import trigger_lb_update_now
            await trigger_lb_update_now(self.bot, inter.guild.id, reason="set_channel")
        except Exception:
            pass

        await inter.followup.send(f"✅ Leaderboard configuré dans {channel.mention}.", ephemeral=True)

    @app_commands.default_permissions(administrator=True)
    @app_commands.command(name="lb_clear", description="(Admin) Efface la configuration de salon du leaderboard.")
    async def lb_clear(self, inter: discord.Interaction):
        if not inter.guild:
            return await inter.response.send_message("❌ À utiliser dans un serveur.", ephemeral=True)
        set_leaderboard_channel(inter.guild.id, None)
        await inter.response.send_message("🗑️ Configuration du leaderboard effacée.", ephemeral=True)

    @app_commands.default_permissions(administrator=True)
    @app_commands.command(name="lb_show", description="(Admin) Affiche le salon actuellement configuré pour le leaderboard.")
    async def lb_show(self, inter: discord.Interaction):
        if not inter.guild:
            return await inter.response.send_message("❌ À utiliser dans un serveur.", ephemeral=True)
        chan_id = get_leaderboard_channel(inter.guild.id)
        if chan_id:
            ch = inter.guild.get_channel(chan_id)
            if isinstance(ch, (discord.TextChannel, discord.Thread, discord.ForumChannel)):
                return await inter.response.send_message(f"📍 Salon configuré : {ch.mention}", ephemeral=True)
            return await inter.response.send_message(f"📍 Salon configuré : <#{chan_id}> (introuvable ?)", ephemeral=True)
        return await inter.response.send_message("ℹ️ Aucun salon configuré.", ephemeral=True)

    @app_commands.default_permissions(administrator=True)
    @app_commands.command(name="lb_refresh", description="(Admin) Recalcule et met à jour le leaderboard persistant.")
    async def lb_refresh(self, inter: discord.Interaction):
        if not inter.guild:
            return await inter.response.send_message("❌ À utiliser dans un serveur.", ephemeral=True)
        await inter.response.defer(ephemeral=True, thinking=True)
        try:
            from cogs.leaderboard_live import trigger_lb_update_now
            await trigger_lb_update_now(self.bot, inter.guild.id, reason="manual")
            await inter.followup.send("🔁 Leaderboard mis à jour.", ephemeral=True)
        except Exception as e:
            await inter.followup.send(f"❌ Impossible de rafraîchir : `{type(e).__name__}`", ephemeral=True)

    # ─────────────────────────────────────────────────────────
    # Utilitaires admin
    # ─────────────────────────────────────────────────────────
    @app_commands.default_permissions(administrator=True)
    @app_commands.command(name="admin_ping", description="(Admin) Ping de santé du bot.")
    async def admin_ping(self, inter: discord.Interaction):
        await inter.response.send_message("Pong ✅", ephemeral=True)

    # ─────────────────────────────────────────────────────────
    # Give d’items
    # ─────────────────────────────────────────────────────────
    @app_commands.default_permissions(administrator=True)
    @app_commands.command(name="admin_give_item", description="(Admin) Donne un objet à un joueur.")
    @app_commands.describe(
        cible="Joueur à qui donner l'objet",
        objet="Emoji de l'objet (autocomplete)",
        quantite="Quantité à donner (min 1)",
        silencieux="Réponse éphémère (par défaut: oui)",
    )
    @app_commands.autocomplete(objet=ac_all_items)
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

        # Validation stricte : emoji connu ET type autorisé
        if objet not in OBJETS or (OBJETS.get(objet, {}).get("type") not in ALLOWED_TYPES):
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

        # Optionnel : ping mise à jour du leaderboard live
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

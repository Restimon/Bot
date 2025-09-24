# cogs/admin_cog.py
from __future__ import annotations

from typing import List, Dict, Any

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
    # Fallbacks soft si data/storage n'est pas dispo
    _LB_MEM: Dict[int, int | None] = {}
    def set_leaderboard_channel(guild_id: int, channel_id: int | None) -> None:
        _LB_MEM[guild_id] = channel_id
    def get_leaderboard_channel(guild_id: int) -> int | None:
        return _LB_MEM.get(guild_id)

# DB inventaire
from inventory_db import add_item

# Catalogue d’objets (emoji -> fiche). Optionnel si utils.py n’est pas présent.
try:
    from utils import OBJETS  # type: ignore
except Exception:
    OBJETS: Dict[str, Dict[str, Any]] = {}

# ─────────────────────────────────────────────────────────────
# Autocomplete items (tous les items connus du catalogue) — amélioré
# ─────────────────────────────────────────────────────────────
async def ac_all_items(interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
    cur = (current or "").strip().lower()

    # Priorité d’affichage: défensifs en tête, puis soins/regen, puis offensifs, puis divers
    TYPE_ORDER = {
        "bouclier": 0,
        "reduction": 0,   # 🪖
        "esquive+": 0,    # 👟
        "immunite": 0,    # ⭐️
        "soin": 1,
        "regen": 1,
        "vaccin": 2,
        "poison": 3,
        "infection": 3,
        "virus": 3,
        "brulure": 3,
        "attaque": 4,
        "attaque_chaine": 4,
        "mysterybox": 5,
        "vol": 5,
    }

    # Synonymes/termes de recherche additionnels pour certains items
    NAME_OVERRIDES = {
        "🪖": ["casque", "reduc", "réduction", "armure"],
        "👟": ["esquive", "dodge"],
        "⭐️": ["immunite", "immunité", "immune"],
        "🛡": ["bouclier", "shield", "pb"],
    }

    def _label(emoji: str, info: dict) -> str:
        typ = str(info.get("type", "") or "")
        try:
            if typ == "attaque":
                d = int(info.get("degats", info.get("dmg", info.get("valeur", 0))) or 0)
                return f"{emoji} • attaque {d}" if d else f"{emoji} • attaque"
            if typ == "attaque_chaine":
                d1 = int(info.get("degats_principal", info.get("dmg_main", info.get("valeur", 0))) or 0)
                d2 = int(info.get("degats_secondaire", info.get("dmg_chain", 0)) or 0)
                return f"{emoji} • attaque {d1}+{d2}" if (d1 or d2) else f"{emoji} • attaque chaîne"
            if typ in ("poison", "infection", "virus", "brulure"):
                d = int(info.get("degats", info.get("value", info.get("valeur", 0))) or 0)
                itv = int(info.get("intervalle", info.get("interval", 60)) or 60)
                return f"{emoji} • {typ} {d}/{max(1, itv)//60}m" if d else f"{emoji} • {typ}/{max(1, itv)//60}m"
            if typ == "soin":
                s = int(info.get("soin", info.get("value", info.get("valeur", 0))) or 0)
                return f"{emoji} • soin {s}" if s else f"{emoji} • soin"
            if typ == "regen":
                v = int(info.get("valeur", info.get("value", 0)) or 0)
                itv = int(info.get("intervalle", info.get("interval", 60)) or 60)
                return f"{emoji} • regen +{v}/{max(1, itv)//60}m" if v else f"{emoji} • regen"
            if typ == "bouclier":
                val = int(info.get("valeur", info.get("value", 0)) or 0)
                return f"{emoji} • bouclier {val}" if val else f"{emoji} • bouclier"
            if typ == "reduction":
                val = info.get("valeur")
                pct = f"{int(float(val)*100)}%" if isinstance(val, (int, float)) else ""
                return f"{emoji} • réduction {pct}".strip()
            if typ == "immunite":
                return f"{emoji} • immunité"
            if typ == "esquive+":
                val = info.get("valeur")
                pct = f"{int(float(val)*100)}%" if isinstance(val, (int, float)) else ""
                return f"{emoji} • esquive+ {pct}".strip()
            if typ == "mysterybox":
                return f"{emoji} • mysterybox"
            if typ == "vol":
                return f"{emoji} • vol"
        except Exception:
            pass
        return f"{emoji} • {typ or 'objet'}"

    # Prépare liste + tri par priorité puis emoji
    items = []
    for emoji, info in OBJETS.items():
        typ = str(info.get("type", "") or "")
        items.append((TYPE_ORDER.get(typ, 9), str(emoji), info))
    items.sort(key=lambda t: (t[0], t[1]))

    # Filtrage avec synonymes
    out: List[app_commands.Choice[str]] = []
    for _, emoji, info in items:
        label = _label(emoji, info)
        haystack = f"{label.lower()} {emoji}"
        for syn in NAME_OVERRIDES.get(emoji, []):
            haystack += f" {syn.lower()}"
        if cur and cur not in haystack:
            continue
        out.append(app_commands.Choice(name=label[:100], value=emoji))
        if len(out) >= 25:  # limite Discord
            break

    # Si rien trouvé avec filtre → 25 premiers
    if not out:
        for _, emoji, info in items[:25]:
            out.append(app_commands.Choice(name=_label(emoji, info)[:100], value=emoji))

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

        # 1) mémorise le salon
        set_leaderboard_channel(inter.guild.id, channel.id)

        # 2) demande au cog leaderboard_live de créer/éditer le message unique
        await inter.response.defer(ephemeral=True, thinking=True)
        try:
            from cogs.leaderboard_live import trigger_lb_update_now
            await trigger_lb_update_now(self.bot, inter.guild.id, reason="set_channel")
        except Exception:
            pass

        await inter.followup.send(f"✅ Leaderboard configuré dans {channel.mention}.", ephemeral=True)

    @app_commands.default_permissions(administrator=True)
    @app_commands.command(
        name="lb_clear",
        description="(Admin) Efface la configuration de salon du leaderboard."
    )
    async def lb_clear(self, inter: discord.Interaction):
        if not inter.guild:
            return await inter.response.send_message("❌ À utiliser dans un serveur.", ephemeral=True)
        set_leaderboard_channel(inter.guild.id, None)
        await inter.response.send_message("🗑️ Configuration du leaderboard effacée.", ephemeral=True)

    @app_commands.default_permissions(administrator=True)
    @app_commands.command(
        name="lb_show",
        description="(Admin) Affiche le salon actuellement configuré pour le leaderboard."
    )
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
    @app_commands.command(
        name="lb_refresh",
        description="(Admin) Recalcule et met à jour le leaderboard persistant (force un refresh immédiat)."
    )
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
    # Petits utilitaires admin
    # ─────────────────────────────────────────────────────────
    @app_commands.default_permissions(administrator=True)
    @app_commands.command(name="admin_ping", description="(Admin) Ping de santé du bot.")
    async def admin_ping(self, inter: discord.Interaction):
        await inter.response.send_message("Pong ✅", ephemeral=True)

    # ─────────────────────────────────────────────────────────
    # Give d’items (avec autocomplete amélioré)
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

        # ping mise à jour du leaderboard si le cog live est chargé
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

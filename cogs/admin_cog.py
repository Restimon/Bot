# cogs/admin_cog.py
from __future__ import annotations

from typing import List, Dict, Any, Optional

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
    # Fallback no-op si stockage absent (ne plante pas le cog)
    def set_leaderboard_channel(*args, **kwargs): ...
    def get_leaderboard_channel(*args, **kwargs): return None

# Inventaire
from inventory_db import add_item

# Catalogue d’objets (emoji -> fiche)
try:
    from utils import OBJETS  # type: ignore
except Exception:
    OBJETS: Dict[str, Dict[str, Any]] = {}

# ---------- Autocomplete: tous les items connus (+ alias conviviaux) ----------
_ITEM_ALIASES: Dict[str, List[str]] = {
    "🪖": ["casque", "helmet", "reduc", "réduction", "mitigation"],
    "🛡": ["bouclier", "shield", "pb", "protections"],
    "👟": ["esquive", "dodge"],
    "⭐️": ["immunité", "immune"],
    "💉": ["vaccin", "cleanse"],
    "💕": ["regen", "régénération", "hot"],
    "🍀": ["soin 1", "heal1"],
    "🩸": ["soin 5", "heal5"],
    "🩹": ["soin 10", "heal10"],
    "💊": ["soin 15", "heal15"],
    "🧪": ["poison"],
    "🧟": ["infection"],
    "🦠": ["virus"],
    "📦": ["mystery", "box", "mysterybox"],
    "🔍": ["vol", "steal"],
}

def _short_label(emoji: str, info: Dict[str, Any]) -> str:
    t = str(info.get("type", "") or "")
    try:
        if t == "attaque":
            d = int(info.get("degats", info.get("dmg", info.get("value", 0))) or 0)
            return f"attaque {d}" if d else "attaque"
        if t == "attaque_chaine":
            d1 = int(info.get("degats_principal", info.get("dmg_main", 0)) or 0)
            d2 = int(info.get("degats_secondaire", info.get("dmg_chain", 0)) or 0)
            return f"attaque {d1}+{d2}" if (d1 or d2) else "attaque chaîne"
        if t in ("poison", "infection", "brulure", "virus"):
            d = int(info.get("degats", info.get("value", 0)) or 0)
            itv = int(info.get("intervalle", info.get("interval", 60)) or 60)
            return f"{t} {d}/{max(1, itv)//60}m" if d else f"{t}/{max(1, itv)//60}m"
        if t == "soin":
            s = int(info.get("soin", info.get("value", info.get("valeur", 0))) or 0)
            return f"soin {s}" if s else "soin"
        if t == "regen":
            v = int(info.get("valeur", info.get("value", 0)) or 0)
            itv = int(info.get("intervalle", info.get("interval", 60)) or 60)
            return f"regen +{v}/{max(1, itv)//60}m" if v else "regen"
        if t == "bouclier":
            val = int(info.get("valeur", info.get("value", 0)) or 0)
            return f"bouclier {val}" if val else "bouclier"
        if t == "reduction":
            val = info.get("valeur", info.get("value", 0))
            try:
                pct = int(float(val) * 100) if isinstance(val, (int, float)) and float(val) <= 1 else int(val)
                return f"réduction {pct}%"
            except Exception:
                return "réduction"
        if t == "esquive+":
            val = info.get("valeur", info.get("value", 0))
            try:
                pct = int(float(val) * 100) if isinstance(val, (int, float)) and float(val) <= 1 else int(val)
                return f"esquive +{pct}%"
            except Exception:
                return "esquive+"
        if t == "immunite":
            return "immunité"
        if t == "mysterybox":
            return "mystery box"
        if t == "vol":
            return "vol"
        if t == "vaccin":
            return "vaccin"
    except Exception:
        pass
    return t or "objet"

async def ac_all_items(interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
    cur = (current or "").strip().lower()
    out: List[app_commands.Choice[str]] = []

    # On peut aussi prioriser certains types si tu veux un ordre custom.
    TYPE_ORDER = {
        "attaque": 10,
        "attaque_chaine": 11,
        "soin": 20,
        "regen": 21,
        "bouclier": 30,
        "reduction": 31,   # ← 🪖
        "esquive+": 32,
        "immunite": 33,
        "poison": 40,
        "infection": 41,
        "virus": 42,
        "brulure": 43,
        "mysterybox": 50,
        "vol": 51,
        "vaccin": 52,
    }

    def _type_order(t: str) -> int:
        return TYPE_ORDER.get(t, 99)

    # on trie pour avoir un ordre stable et lisible
    for emoji, info in sorted(OBJETS.items(), key=lambda kv: (_type_order(kv[1].get("type", "")), kv[0])):
        try:
            typ = str(info.get("type", "") or "")
            label = typ
            if typ == "attaque":
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
            elif typ == "reduction":
                val = info.get("valeur", info.get("value", 0))
                # affiche "casque" pour être plus parlant
                if isinstance(val, (int, float)) and val:
                    try:
                        pct = int(float(val) * 100)
                        label = f"casque -{pct}% dmg"
                    except Exception:
                        label = "casque (réduction)"
                else:
                    label = "casque (réduction)"
            elif typ == "esquive+":
                val = info.get("valeur", info.get("value", 0))
                if isinstance(val, (int, float)):
                    try:
                        pct = int(float(val) * 100)
                        label = f"esquive +{pct}%"
                    except Exception:
                        label = "esquive+"
                else:
                    label = "esquive+"
            elif typ == "immunite":
                label = "immunité"
            else:
                label = typ or "objet"
        except Exception:
            label = "objet"

        name = f"{emoji} • {label}"
        # Filtre : on matche aussi sur quelques alias utiles
        aliases = (label.lower(), typ.lower())
        hay = " ".join((name.lower(),) + aliases)
        if not cur or cur in hay:
            out.append(app_commands.Choice(name=name[:100], value=emoji))
            if len(out) >= 25:  # ← Discord autorise jusqu’à 25
                break

    return out

class AdminTools(commands.Cog):
    """Commandes Admin (réservées aux administrateurs)."""
    qualified_name = "AdminTools"  # nom unique pour éviter les collisions

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
    # Petits utilitaires admin
    # ─────────────────────────────────────────────────────────
    @app_commands.default_permissions(administrator=True)
    @app_commands.command(name="admin_ping", description="(Admin) Ping de santé du bot.")
    async def admin_ping(self, inter: discord.Interaction):
        await inter.response.send_message("Pong ✅", ephemeral=True)

    # ─────────────────────────────────────────────────────────
    # Give d’items
    # ─────────────────────────────────────────────────────────
    @app_commands.command(name="admin_give_item", description="(Admin) Donne un objet à un joueur.")
    @app_commands.describe(
        cible="Joueur à qui donner l'objet",
        objet="Emoji de l'objet (autocomplete — ex: 🪖, 'casque')",
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
                "Objet inconnu. Utilise l’autocomplete (tu peux taper « casque » pour 🪖).",
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

        try:
            from cogs.leaderboard_live import schedule_lb_update
            schedule_lb_update(self.bot, interaction.guild.id, "admin_give_item")
        except Exception:
            pass

        embed = discord.Embed(title="✅ Item attribué", description=desc, color=discord.Color.green())
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=silencieux)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=silencieux)


async def setup(bot: commands.Bot):
    # Si un cog homonyme existe déjà, on ne double pas
    if bot.get_cog("AdminTools"):
        return
    await bot.add_cog(AdminTools(bot))

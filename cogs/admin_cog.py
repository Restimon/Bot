# cogs/admin_cog.py
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional

# Économie / inventaire / stats / effets / passifs
from economy_db import add_coins, spend_coins, get_balance, set_balance
from inventory_db import add_item, remove_item, get_item_qty
from stats_db import set_hp, set_shield, revive_full, get_hp, get_shield
from effects_db import clear_effects
from passifs import set_equipped_name, get_equipped_name
from personnage import PERSONNAGES

# Leaderboard
from leaderboard import (
    init_leaderboard_db,
    set_leaderboard_message,
    clear_leaderboard_message,
    ensure_and_update_message,
    build_embed,
)

ADMIN_GROUP_NAME = "admin"

def _has_admin(interaction: discord.Interaction) -> bool:
    if not isinstance(interaction.user, discord.Member):
        return False
    perms = interaction.user.guild_permissions
    return perms.administrator or perms.manage_guild


class AdminCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        await init_leaderboard_db()

    # ─────────────────────────────────────────────────────────────
    # Groupe racine /admin
    # ─────────────────────────────────────────────────────────────
    admin = app_commands.Group(name=ADMIN_GROUP_NAME, description="Commandes d'administration GotValis")

    # ---------- Leaderboard ----------
    @admin.command(name="leaderboard_set", description="Installer/placer le leaderboard persistant dans un salon.")
    @app_commands.describe(channel="Salon cible pour le message de classement")
    async def leaderboard_set(self, interaction: discord.Interaction, channel: discord.TextChannel):
        if not _has_admin(interaction):
            await interaction.response.send_message("❌ Permission insuffisante.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        emb = await build_embed(channel.guild)
        msg = await channel.send(embed=emb)
        await set_leaderboard_message(channel.guild.id, channel.id, msg.id)
        await interaction.followup.send(f"✅ Leaderboard installé dans {channel.mention}.", ephemeral=True)

    @admin.command(name="leaderboard_clear", description="Supprimer la configuration du leaderboard de ce serveur.")
    async def leaderboard_clear_cmd(self, interaction: discord.Interaction):
        if not _has_admin(interaction):
            await interaction.response.send_message("❌ Permission insuffisante.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        await clear_leaderboard_message(interaction.guild_id)
        await interaction.followup.send("🗑️ Config leaderboard supprimée. Le message existant ne sera plus mis à jour.", ephemeral=True)

    @admin.command(name="leaderboard_update", description="Forcer une mise à jour immédiate du leaderboard.")
    async def leaderboard_update(self, interaction: discord.Interaction):
        if not _has_admin(interaction):
            await interaction.response.send_message("❌ Permission insuffisante.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        ok = await ensure_and_update_message(interaction.guild)
        await interaction.followup.send("🔄 Leaderboard mis à jour." if ok else "⚠️ Aucun leaderboard configuré.", ephemeral=True)

    # ---------- Coins ----------
    @admin.command(name="coins", description="Ajouter, retirer ou fixer le solde GotCoins d'un joueur.")
    @app_commands.describe(
        membre="Cible",
        action="add / remove / set",
        montant="Montant en GotCoins"
    )
    @app_commands.choices(
        action=[
            app_commands.Choice(name="add", value="add"),
            app_commands.Choice(name="remove", value="remove"),
            app_commands.Choice(name="set", value="set"),
        ]
    )
    async def coins(self, interaction: discord.Interaction, membre: discord.Member, action: app_commands.Choice[str], montant: int):
        if not _has_admin(interaction):
            await interaction.response.send_message("❌ Permission insuffisante.", ephemeral=True)
            return
        if montant < 0:
            await interaction.response.send_message("❌ Montant invalide.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)

        if action.value == "add":
            await add_coins(membre.id, montant)
        elif action.value == "remove":
            # retire sans aller sous 0
            bal = await get_balance(membre.id)
            to_spend = min(bal, montant)
            if to_spend > 0:
                await spend_coins(membre.id, to_spend)
        else:  # set
            await set_balance(membre.id, montant)

        new_bal = await get_balance(membre.id)
        await interaction.followup.send(f"💰 Nouveau solde de {membre.mention} : **{new_bal}** GotCoins.", ephemeral=True)

    # ---------- Items (inclut 🎟️) ----------
    @admin.command(name="item", description="Donner ou retirer un item (emoji) à un joueur.")
    @app_commands.describe(
        membre="Cible",
        emoji="Emoji de l'objet (ex: 🧪, 🛡, 🎟️...)",
        quantite="Quantité",
        action="give / take"
    )
    @app_commands.choices(
        action=[
            app_commands.Choice(name="give", value="give"),
            app_commands.Choice(name="take", value="take"),
        ]
    )
    async def item(self, interaction: discord.Interaction, membre: discord.Member, emoji: str, quantite: int, action: app_commands.Choice[str]):
        if not _has_admin(interaction):
            await interaction.response.send_message("❌ Permission insuffisante.", ephemeral=True)
            return
        if quantite <= 0:
            await interaction.response.send_message("❌ Quantité invalide.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)

        if action.value == "give":
            await add_item(membre.id, emoji, quantite)
            qty = await get_item_qty(membre.id, emoji)
            await interaction.followup.send(f"🎁 {membre.mention} reçoit **{quantite}× {emoji}** (total: {qty}).", ephemeral=True)
        else:
            ok = await remove_item(membre.id, emoji, quantite)
            if not ok:
                await interaction.followup.send("⚠️ Stock insuffisant pour retirer.", ephemeral=True)
                return
            qty = await get_item_qty(membre.id, emoji)
            await interaction.followup.send(f"🗑️ Retiré **{quantite}× {emoji}** à {membre.mention} (reste: {qty}).", ephemeral=True)

    # ---------- Effets ----------
    @admin.command(name="effects_clear", description="Purger tous les effets (positifs/négatifs) d'un joueur.")
    @app_commands.describe(membre="Cible")
    async def effects_clear(self, interaction: discord.Interaction, membre: discord.Member):
        if not _has_admin(interaction):
            await interaction.response.send_message("❌ Permission insuffisante.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        await clear_effects(membre.id)
        await interaction.followup.send(f"🧼 Tous les effets de {membre.mention} ont été purgés.", ephemeral=True)

    # ---------- PV/PB ----------
    @admin.command(name="revive", description="Réanimer (100 PV, 0 PB) et nettoyer les effets d'un joueur.")
    @app_commands.describe(membre="Cible")
    async def revive(self, interaction: discord.Interaction, membre: discord.Member):
        if not _has_admin(interaction):
            await interaction.response.send_message("❌ Permission insuffisante.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        await revive_full(membre.id)
        await clear_effects(membre.id)
        await interaction.followup.send(f"❤️‍🩹 {membre.mention} est réanimé à **100 PV** et **0 PB**.", ephemeral=True)

    @admin.command(name="hp_set", description="Fixer précisément les PV et/ou PB d'un joueur.")
    @app_commands.describe(membre="Cible", pv="Nouveaux PV (laisser -1 pour ignorer)", pb="Nouveaux PB (laisser -1 pour ignorer)")
    async def hp_set(self, interaction: discord.Interaction, membre: discord.Member, pv: int = -1, pb: int = -1):
        if not _has_admin(interaction):
            await interaction.response.send_message("❌ Permission insuffisante.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)

        if pv >= 0:
            await set_hp(membre.id, pv)
        if pb >= 0:
            await set_shield(membre.id, pb)

        cur_hp, _ = await get_hp(membre.id)
        cur_pb = await get_shield(membre.id)
        await interaction.followup.send(f"🔧 Nouvel état de {membre.mention} → ❤️ {cur_hp} PV | 🛡 {cur_pb} PB.", ephemeral=True)

    # ---------- Équipement personnage ----------
    @admin.command(name="equip", description="Équiper (ou retirer) un personnage sur un joueur.")
    @app_commands.describe(
        membre="Cible",
        nom_personnage="Nom EXACT ou 'none' pour retirer"
    )
    async def equip(self, interaction: discord.Interaction, membre: discord.Member, nom_personnage: str):
        if not _has_admin(interaction):
            await interaction.response.send_message("❌ Permission insuffisante.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)

        name = nom_personnage.strip()
        if name.lower() in {"none", "aucun", "retirer"}:
            await set_equipped_name(membre.id, None)
            await interaction.followup.send(f"🗃️ Personnage retiré pour {membre.mention}.", ephemeral=True)
            return

        if name not in PERSONNAGES:
            await interaction.followup.send("❌ Personnage introuvable (nom exact requis).", ephemeral=True)
            return

        await set_equipped_name(membre.id, name)
        await interaction.followup.send(f"🎴 {membre.mention} équipe **{name}**.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(AdminCog(bot))

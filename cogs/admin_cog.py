# cogs/admin_cog.py
from __future__ import annotations

import discord
from discord.ext import commands
from discord import app_commands

from data import storage

LEADERBOARD_KEY = "leaderboard"  # dans data.json: ["by_guild"][guild_id][LEADERBOARD_KEY] = {channel_id, message_id}

class AdminCog(commands.Cog):
    """Commandes Admin (réservées aux administrateurs)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ─────────────────────────────────────────────────────────
    # Utils internes stockage
    # ─────────────────────────────────────────────────────────
    def _get_guild_bucket(self, guild_id: int) -> dict:
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
    @app_commands.command(name="admin_set_leaderboard_channel",
                          description="(Admin) Définit le salon où le leaderboard persistant sera affiché.")
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
    @app_commands.command(name="admin_clear_leaderboard",
                          description="(Admin) Supprime les infos de leaderboard (canal/message mémorisés).")
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

async def setup(bot: commands.Bot):
    await bot.add_cog(AdminCog(bot))

# cogs/admin_leaderboard_cog.py
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from leaderboard import (
    init_leaderboard_db,
    set_leaderboard_message,
    clear_leaderboard_message,
    ensure_and_update_message,
    build_embed,
)

class AdminLeaderboard(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        await init_leaderboard_db()

    def _admin_check(self, interaction: discord.Interaction) -> bool:
        # Admins ou Manage Guild
        if not interaction.user:
            return False
        if isinstance(interaction.user, discord.Member):
            perms = interaction.user.guild_permissions
            return perms.administrator or perms.manage_guild
        return False

    @app_commands.command(name="leaderboard_set", description="(Admin) Place le leaderboard dans un salon choisi.")
    @app_commands.describe(channel="Salon où afficher le leaderboard persistant.")
    async def leaderboard_set(self, interaction: discord.Interaction, channel: discord.TextChannel):
        if not self._admin_check(interaction):
            await interaction.response.send_message("❌ Permission insuffisante.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)

        # Poster nouveau message
        emb = await build_embed(channel.guild)
        msg = await channel.send(embed=emb)

        # Stocker en DB
        await set_leaderboard_message(channel.guild.id, channel.id, msg.id)

        await interaction.followup.send(f"✅ Leaderboard installé dans {channel.mention} (message épinglé mis à jour automatiquement).", ephemeral=True)

    @app_commands.command(name="leaderboard_clear", description="(Admin) Retire la configuration du leaderboard pour ce serveur.")
    async def leaderboard_clear(self, interaction: discord.Interaction):
        if not self._admin_check(interaction):
            await interaction.response.send_message("❌ Permission insuffisante.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)

        await clear_leaderboard_message(interaction.guild_id)
        await interaction.followup.send("🗑️ Configuration du leaderboard supprimée pour ce serveur. (Le message existant ne sera plus mis à jour.)", ephemeral=True)

    @app_commands.command(name="leaderboard_update", description="(Admin) Force une mise à jour immédiate du leaderboard.")
    async def leaderboard_update(self, interaction: discord.Interaction):
        if not self._admin_check(interaction):
            await interaction.response.send_message("❌ Permission insuffisante.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        ok = await ensure_and_update_message(interaction.guild)
        if ok:
            await interaction.followup.send("🔄 Leaderboard mis à jour.", ephemeral=True)
        else:
            await interaction.followup.send("⚠️ Aucun leaderboard configuré pour ce serveur.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(AdminLeaderboard(bot))

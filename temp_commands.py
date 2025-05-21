# temp_commands.py

import discord
from discord import app_commands
from discord.ext import commands
import logging

from storage import inventaire, hp, leaderboard
from data import sauvegarder
from config import get_config, get_guild_config, save_config

def register_temp_commands(bot: commands.Bot):
    @bot.tree.command(name="forcereset", description="(Temporaire) Forcer le reset annuel des stats.")
    @app_commands.checks.has_permissions(administrator=True)
    async def force_reset(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        # Reset des données par serveur
        for gid in list(inventaire.keys()):
            inventaire[gid] = {}
        for gid in list(hp.keys()):
            hp[gid] = {}
        for gid in list(leaderboard.keys()):
            leaderboard[gid] = {}

        sauvegarder()

        # Message d’annonce
        announcement_msg = "🧹 **Réinitialisation forcée des données effectuée.** Toutes les statistiques ont été remises à zéro."

        for server_id, server_conf in config.items():
            channel_id = server_conf.get("leaderboard_channel_id")
            if not channel_id:
                continue
            try:
                channel = bot.get_channel(channel_id)
                if channel:
                    await channel.send(announcement_msg)
            except Exception as e:
                logging.error(f"❌ Impossible d’envoyer l’annonce dans {channel_id} (serveur {server_id}) : {e}")

        await interaction.followup.send("✅ Réinitialisation effectuée et message diffusé.", ephemeral=True)

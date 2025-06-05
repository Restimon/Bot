import discord
from discord import app_commands

def register_sync_command(bot):
    @bot.tree.command(name="sync", description="🔄 Synchronise les commandes slash du bot (admin uniquement)")
    @app_commands.checks.has_permissions(administrator=True)
    async def sync_commands(interaction: discord.Interaction):
        try:
            await interaction.response.defer(thinking=True, ephemeral=True)
            synced = await bot.tree.sync()  # ⤴️ Synchronise avec Discord (globalement)
            await interaction.followup.send(f"✅ {len(synced)} commandes synchronisées avec succès.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Erreur lors de la synchronisation : {e}", ephemeral=True)

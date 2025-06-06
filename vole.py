import discord
from discord import app_commands
import random

from storage import get_user_data
from utils import OBJETS
from embeds import build_embed_from_item
from utils import get_mention
from data import is_immune

def register_vole_command(bot):
    @bot.tree.command(name="vole", description="🔍 Vole un objet à un autre joueur.")
    @app_commands.describe(cible="Le joueur à voler")
    async def vole_slash(interaction: discord.Interaction, cible: discord.Member):
        await interaction.response.defer(thinking=True)

        if cible.bot:
            await interaction.followup.send("❌ Tu ne peux pas voler un bot.", ephemeral=True)
            return

        guild_id = str(interaction.guild.id)
        user_id = str(interaction.user.id)
        target_id = str(cible.id)

        inv_user, _, _ = get_user_data(guild_id, user_id)
        inv_target, _, _ = get_user_data(guild_id, target_id)

        if "🔍" not in inv_user:
            await interaction.followup.send("❌ Tu n’as pas de 🔍 à utiliser.", ephemeral=True)
            return

        # Vérifie immunité
        if is_immune(guild_id, target_id):
            await interaction.followup.send(f"⭐️ {get_mention(interaction.guild, target_id)} est immunisé. Impossible de voler.", ephemeral=True)
            return

        # Vérifie que la cible a des objets
        stealable = [item for item in inv_target if item != "📦"]
        if not stealable:
            await interaction.followup.send(f"❌ {get_mention(interaction.guild, target_id)} n’a aucun objet à voler.", ephemeral=True)
            return

        # Vol réussi
        item_stolen = random.choice(stealable)
        inv_target.remove(item_stolen)
        inv_user.remove("🔍")
        inv_user.append(item_stolen)

        embed = discord.Embed(
            title="🔍 Vol réussi !",
            description=(
                f"{get_mention(interaction.guild, user_id)} a volé **{item_stolen}** "
                f"à {get_mention(interaction.guild, target_id)}."
            ),
            color=discord.Color.orange()
        )
        await interaction.followup.send(embed=embed)

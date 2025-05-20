import discord
from discord import app_commands
from utils import OBJETS
from storage import get_user_data
from data import sauvegarder
from combat import apply_item_with_cooldown

def register_heal_command(bot):
    @bot.tree.command(name="heal", description="Soigne toi ou un autre membre avec un objet de soin")
    @app_commands.describe(target="Membre à soigner (ou toi-même)", item="Objet de soin à utiliser (emoji)")
    async def heal_slash(interaction: discord.Interaction, target: discord.Member = None, item: str = None):
        guild_id = str(interaction.guild.id)
        uid = str(interaction.user.id)
        tid = str(target.id) if target else uid

        user_inv, _, _ = get_user_data(guild_id, uid)

        if not item or item not in OBJETS:
            return await interaction.response.send_message("❌ Objet inconnu ou non spécifié.", ephemeral=True)

        if item not in user_inv:
            return await interaction.response.send_message(f"🚫 SomniCorp ne détecte pas {item} dans ton inventaire.", ephemeral=True)

        if OBJETS[item]["type"] != "soin":
            return await interaction.response.send_message("⚠️ Cet objet n’est pas destiné à soigner !", ephemeral=True)

        embed, success = apply_item_with_cooldown(uid, tid, item, interaction)

        if success:
            user_inv.remove(item)  # On ne retire l’objet que si l'action est réussie

        sauvegarder()
        await interaction.response.send_message(embed=embed)

    @heal_slash.autocomplete("item")
    async def autocomplete_items(interaction: discord.Interaction, current: str):
        guild_id = str(interaction.guild.id)
        uid = str(interaction.user.id)
        user_inv, _, _ = get_user_data(guild_id, uid)

        heal_items = sorted(set(i for i in user_inv if OBJETS.get(i, {}).get("type") == "soin"))

        if not heal_items:
            return [app_commands.Choice(name="Aucun objet de soin", value="")]

        return [
            app_commands.Choice(name=emoji, value=emoji)
            for emoji in heal_items if current in emoji
        ][:25]

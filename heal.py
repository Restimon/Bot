# heal.py
import discord
from discord import app_commands
from utils import inventaire, OBJETS, leaderboard, hp
from data import sauvegarder
from combat import apply_item_with_cooldown

def register_heal_command(bot):
    @bot.tree.command(name="heal", description="Soigne toi ou un autre membre avec un objet de soin")
    @app_commands.describe(target="Membre à soigner (ou toi-même)", item="Objet de soin à utiliser (emoji)")
    async def heal_slash(interaction: discord.Interaction, target: discord.Member = None, item: str = None):
        uid = str(interaction.user.id)
        tid = str(target.id) if target else uid

        # Vérifie possession
        if uid not in inventaire or item not in inventaire[uid]:
            return await interaction.response.send_message("❌ Tu n’as pas cet objet de soin dans ton inventaire.", ephemeral=True)

        # Vérifie que c’est bien un objet de soin
        if item not in OBJETS or OBJETS[item]["type"] != "soin":
            return await interaction.response.send_message("⚠️ Cet objet ne sert pas à soigner !", ephemeral=True)

        # Appliquer l’effet
        inventaire[uid].remove(item)
        embed = apply_item_with_cooldown(uid, tid, item, interaction)
        sauvegarder()
        await interaction.response.send_message(embed=embed)

    @heal_slash.autocomplete("item")
    async def autocomplete_items(interaction: discord.Interaction, current: str):
        uid = str(interaction.user.id)
        items = inventaire.get(uid, [])
        heal_items = sorted(set(i for i in items if OBJETS.get(i, {}).get("type") == "soin"))
        return [
            app_commands.Choice(name=f"{emoji}", value=emoji)
            for emoji in heal_items if current in emoji
        ]

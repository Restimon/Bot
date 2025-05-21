import discord
from discord import app_commands
from utils import OBJETS
from storage import get_user_data
from data import sauvegarder, virus_status
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

        if OBJETS[item]["type"] != "soin" and item != "💉":
            return await interaction.response.send_message("⚠️ Cet objet n’est pas destiné à soigner !", ephemeral=True)

        # Traitement spécial pour 💉 vaccin
        if item == "💉":
            virus_status.setdefault(guild_id, {})
            if uid in virus_status[guild_id]:
                del virus_status[guild_id][uid]
                description = f"💉 {interaction.user.mention} s’est administré un vaccin.\n🦠 Le virus a été **éradiqué** avec succès !"
            else:
                description = f"💉 Aucun virus détecté chez {interaction.user.mention}. L’injection était inutile."

            user_inv.remove("💉")
            sauvegarder()

            embed = discord.Embed(title="📢 Vaccination SomniCorp", description=description, color=discord.Color.green())
            return await interaction.response.send_message(embed=embed)

        # Traitement normal des soins
        embed, success = apply_item_with_cooldown(uid, tid, item, interaction)

        if success:
            user_inv.remove(item)

        sauvegarder()
        await interaction.response.send_message(embed=embed)

    @heal_slash.autocomplete("item")
    async def autocomplete_items(interaction: discord.Interaction, current: str):
        guild_id = str(interaction.guild.id)
        uid = str(interaction.user.id)
        user_inv, _, _ = get_user_data(guild_id, uid)

        heal_items = sorted(set(i for i in user_inv if OBJETS.get(i, {}).get("type") == "soin" or i == "💉"))

        if not heal_items:
            return [app_commands.Choice(name="Aucun objet de soin", value="")]

        return [
            app_commands.Choice(name=emoji, value=emoji)
            for emoji in heal_items if current in emoji
        ][:25]

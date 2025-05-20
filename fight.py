import discord
from discord import app_commands
from data import sauvegarder
from utils import OBJETS
from storage import get_user_data
from combat import apply_item_with_cooldown

def register_fight_command(bot):
    @bot.tree.command(name="fight", description="Attaque un autre membre avec un objet spécifique")
    @app_commands.describe(target="La personne à attaquer", item="Objet d’attaque à utiliser (emoji)")
    async def fight_slash(interaction: discord.Interaction, target: discord.Member, item: str):
        guild_id = str(interaction.guild.id)
        uid = str(interaction.user.id)
        tid = str(target.id)

        user_inv, _, _ = get_user_data(guild_id, uid)

        if item not in user_inv:
            return await interaction.response.send_message("❌ Tu n’as pas cet objet dans ton inventaire.", ephemeral=True)

        if item not in OBJETS or OBJETS[item]["type"] != "attaque":
            return await interaction.response.send_message("⚠️ Cet objet n’est pas une arme valide !", ephemeral=True)

        embed, success = apply_item_with_cooldown(uid, tid, item, interaction)

        if success:
            user_inv.remove(item)  # On ne consomme l’objet que si l’attaque a vraiment lieu

        sauvegarder()
        await interaction.response.send_message(embed=embed)


    # 🔽 Veille à ce que ceci soit bien indenté au même niveau que `async def fight_slash`
    @fight_slash.autocomplete("item")
    async def autocomplete_items(interaction: discord.Interaction, current: str):
        guild_id = str(interaction.guild.id)
        uid = str(interaction.user.id)
        user_inv, _, _ = get_user_data(guild_id, uid)

        attack_items = sorted(set(i for i in user_inv if OBJETS.get(i, {}).get("type") == "attaque"))
        if not attack_items:
            return [app_commands.Choice(name="Aucune arme disponible", value="")]

        return [
            app_commands.Choice(name=f"{emoji}", value=emoji)
            for emoji in attack_items if current in emoji
        ][:25]

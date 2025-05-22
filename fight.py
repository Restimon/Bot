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

        # Récupère l'inventaire du joueur
        user_inv, _, _ = get_user_data(guild_id, uid)

        # Vérifie que l'objet est possédé
        if item not in user_inv:
            return await interaction.response.send_message("❌ Tu n’as pas cet objet dans ton inventaire.", ephemeral=True)

        # Vérifie que l'objet est bien une arme ou un effet de statut offensif
        if item not in OBJETS or OBJETS[item]["type"] not in ["attaque", "virus", "poison", "infection"]:
            return await interaction.response.send_message("⚠️ Cet objet n’est pas une arme valide !", ephemeral=True)

        # Applique l'objet via le système de combat
        result = await apply_item_with_cooldown(uid, tid, item, interaction)
        if not isinstance(result, tuple) or len(result) != 2:
            await interaction.response.send_message("❌ Erreur inattendue (résultat invalide).")
            return
        embed, success = result

        if success:
            user_inv.remove(item)  # Consomme l'objet si l'attaque réussit
            sauvegarder()
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)

    @fight_slash.autocomplete("item")
    async def autocomplete_items(interaction: discord.Interaction, current: str):
        guild_id = str(interaction.guild.id)
        uid = str(interaction.user.id)
        user_inv, _, _ = get_user_data(guild_id, uid)

        # Filtre les objets d’attaque que le joueur possède
        attack_items = sorted(set(
            i for i in user_inv if OBJETS.get(i, {}).get("type") in ["attaque", "virus", "poison", "infection"]
        ))

        if not attack_items:
            return [app_commands.Choice(name="Aucune arme disponible", value="")]

        # Suggère les objets selon l'input
        return [
            app_commands.Choice(name=f"{emoji}", value=emoji)
            for emoji in attack_items if current in emoji
        ][:25]

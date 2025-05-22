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

        # 🔒 Refuser l'auto-attaque ou attaque de bots
        if target.bot or uid == tid:
            return await interaction.response.send_message(
                "🤖 Tu ne peux pas attaquer cette cible. Essaie plutôt un vrai adversaire !", ephemeral=True
            )

        user_inv, _, _ = get_user_data(guild_id, uid)

        if item not in user_inv:
            return await interaction.response.send_message("❌ Tu n’as pas cet objet dans ton inventaire.", ephemeral=True)

        if item not in OBJETS or OBJETS[item]["type"] not in ["attaque", "virus", "poison", "infection"]:
            return await interaction.response.send_message("⚠️ Cet objet n’est pas une arme valide !", ephemeral=True)

        result = await apply_item_with_cooldown(uid, tid, item, interaction)
        if not isinstance(result, tuple) or len(result) != 2:
            return await interaction.response.send_message("❌ Erreur inattendue (résultat invalide).", ephemeral=True)

        embed, success = result

        if success:
            user_inv.remove(item)
            sauvegarder()
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)

   @fight_slash.autocomplete("item")
async def autocomplete_items(interaction: discord.Interaction, current: str):
    guild_id = str(interaction.guild.id)
    uid = str(interaction.user.id)
    user_inv, _, _ = get_user_data(guild_id, uid)

    attack_types = ["attaque", "virus", "poison", "infection"]
    attack_items = sorted(set(
        i for i in user_inv if OBJETS.get(i, {}).get("type") in attack_types
    ))

    if not attack_items:
        return [app_commands.Choice(name="Aucune arme disponible", value="")]

    suggestions = []
    for emoji in attack_items:
        if current not in emoji:
            continue

        obj = OBJETS.get(emoji, {})
        typ = obj.get("type")

        if typ == "attaque":
            label = f"{emoji} ({obj.get('degats')} dmg, {int(obj.get('crit', 0)*100)}% crit)"
        elif emoji == "☠️":
            label = f"{emoji} (☠️ 24 dmg + 2×12, {int(obj.get('crit', 0)*100)}% crit)"
        elif typ == "virus":
            label = f"{emoji} (🦠 Virus : 5 initiaux + 5/h)"
        elif typ == "poison":
            label = f"{emoji} (🧪 Poison : 3/30min)"
        elif typ == "infection":
            label = f"{emoji} (🧟 Infection : 2/30min, propagation possible)"
        else:
            label = f"{emoji} (Objet spécial)"

        suggestions.append(app_commands.Choice(name=label, value=emoji))

    return suggestions[:25]

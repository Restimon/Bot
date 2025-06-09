# fight.py

import discord
from discord import app_commands
from utils import OBJETS
from storage import get_user_data
from data import sauvegarder
from combat import apply_item_with_cooldown, apply_attack_chain
from embeds import build_embed_from_item

def register_fight_command(bot):
    @bot.tree.command(name="fight", description="Attaque un autre membre avec un objet spécifique")
    @app_commands.describe(target="La personne à attaquer", item="Objet d’attaque à utiliser (emoji)")
    async def fight_slash(interaction: discord.Interaction, target: discord.Member, item: str):
        await interaction.response.defer(thinking=True)

        guild_id = str(interaction.guild.id)
        uid = str(interaction.user.id)
        tid = str(target.id)
        action = OBJETS.get(item, {})

        if target.bot:
            return await interaction.followup.send(
                "🤖 Tu ne peux pas attaquer un bot, même s’il a l’air louche.", ephemeral=True
            )

        if interaction.user.id == target.id:
            return await interaction.followup.send(
                "❌ Tu ne peux pas t'attaquer toi-même.", ephemeral=True
            )

        user_inv, _, _ = get_user_data(guild_id, uid)

        if item not in user_inv:
            return await interaction.followup.send(
                "❌ Tu n’as pas cet objet dans ton inventaire.", ephemeral=True
            )

        attack_types = ["attaque", "attaque_chaine", "virus", "poison", "infection"]

        if item not in OBJETS or OBJETS[item]["type"] not in attack_types:
            return await interaction.followup.send(
                "⚠️ Cet objet n’est pas une arme valide !", ephemeral=True
            )

        # ☠️ Attaque en chaîne
        if item == "☠️":
            await apply_attack_chain(interaction, uid, tid, item, action)

            # Retire l'objet après attaque en chaîne
            user_inv.remove(item)
            sauvegarder()

            return

        # Attaque normale
        embed, success = await apply_item_with_cooldown(interaction, uid, tid, item, action)

        if success:
            user_inv.remove(item)
            sauvegarder()

        if embed:
            await interaction.followup.send(embed=embed, ephemeral=False)  # Public

    # ✅ Autocomplétion des objets d'attaque avec description
    @fight_slash.autocomplete("item")
    async def autocomplete_items(interaction: discord.Interaction, current: str):
        guild_id = str(interaction.guild.id)
        uid = str(interaction.user.id)
        user_inv, _, _ = get_user_data(guild_id, uid)

        attack_types = ["attaque", "attaque_chaine", "virus", "poison", "infection"]

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
                label = f"{emoji} | {obj.get('degats')} dmg, {int(obj.get('crit', 0)*100)}% crit"
            elif typ == "attaque_chaine":
                label = f"{emoji} | ☠️ 24 dmg + 2×12, {int(obj.get('crit', 0)*100)}% crit"
            elif typ == "virus":
                label = f"{emoji} | Virus → 5 dmg initiaux + 5 dmg/h"
            elif typ == "poison":
                label = f"{emoji} | Poison → 3 dmg initiaux + 3 dmg/30min"
            elif typ == "infection":
                label = f"{emoji} | Infection → 5 dmg initiaux + 2 dmg/30min, propagation"
            else:
                label = f"{emoji} (Objet spécial)"

            suggestions.append(app_commands.Choice(name=label, value=emoji))

        return suggestions[:25]

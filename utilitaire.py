import discord
from discord import app_commands
from utils import OBJETS, get_mention
from storage import get_user_data
from data import sauvegarder, shields, immunite_status, esquive_status, casque_status
from embeds import build_embed_from_item

def register_utilitaire_command(bot):
    @bot.tree.command(name="utilitaire", description="Utilise un objet utilitaire ou de protection")
    @app_commands.describe(target="Cible (si applicable, ex: pour le vol)", item="Objet utilitaire à utiliser (emoji)")
    async def utilitaire_slash(interaction: discord.Interaction, target: discord.Member = None, item: str = ""):
        await interaction.response.defer(thinking=True)

        guild_id = str(interaction.guild.id)
        uid = str(interaction.user.id)
        tid = str(target.id) if target else uid  # si pas de target : auto-ciblage
        action = OBJETS.get(item, {})

        user_inv, _, _ = get_user_data(guild_id, uid)

        if item not in user_inv:
            return await interaction.followup.send(
                "❌ Tu n’as pas cet objet dans ton inventaire.", ephemeral=True
            )

        # Autoriser uniquement ces types :
        allowed_types = ["vol", "bouclier", "esquive+", "reduction", "immunite"]

        if item not in OBJETS or OBJETS[item]["type"] not in allowed_types:
            return await interaction.followup.send(
                "⚠️ Cet objet n’est pas utilisable via `/utilitaire`.", ephemeral=True
            )

        # Si c’est un vol, cible obligatoire
        if OBJETS[item]["type"] == "vol" and not target:
            return await interaction.followup.send(
                "❌ Tu dois cibler quelqu’un pour utiliser un objet de type **vol**.", ephemeral=True
            )

        # Appliquer l'effet
        embed = None
        success = False

        if action["type"] == "bouclier":
            shields.setdefault(guild_id, {})[uid] = shields.get(guild_id, {}).get(uid, 0) + 20
            embed = build_embed_from_item(item, f"{interaction.user.mention} a utilisé un **bouclier** de protection !")
            success = True

        elif action["type"] == "immunite":
            immunite_status.setdefault(guild_id, {})[uid] = {
                "start": interaction.created_at.timestamp(),
                "duration": action.get("duree", 2 * 3600)
            }
            embed = build_embed_from_item(item, f"{interaction.user.mention} bénéficie désormais d’une **immunité totale** pendant 2h.")
            success = True

        elif action["type"] == "esquive+":
            esquive_status.setdefault(guild_id, {})[uid] = {
                "start": interaction.created_at.timestamp(),
                "duration": action.get("duree", 3 * 3600),
                "valeur": action.get("valeur", 0.2)
            }
            embed = build_embed_from_item(item, f"{interaction.user.mention} bénéficie désormais d’une **augmentation d’esquive** pendant 3h.")
            success = True

        elif action["type"] == "reduction":
            casque_status.setdefault(guild_id, {})[uid] = {
                "start": interaction.created_at.timestamp(),
                "duration": action.get("duree", 4 * 3600)
            }
            embed = build_embed_from_item(item, f"{interaction.user.mention} bénéficie désormais d’une **réduction des dégâts** pendant 4h.")
            success = True

        elif action["type"] == "vol":
            result_embed = await voler_objet(interaction, uid, tid)
            embed = result_embed
            success = True

        # Retirer l'objet s'il a été utilisé avec succès
        if success:
            user_inv.remove(item)
            sauvegarder()

        if embed:
            await interaction.followup.send(embed=embed, ephemeral=True)

    # Autocomplétion
    @utilitaire_slash.autocomplete("item")
    async def autocomplete_items(interaction: discord.Interaction, current: str):
        guild_id = str(interaction.guild.id)
        uid = str(interaction.user.id)
        user_inv, _, _ = get_user_data(guild_id, uid)

        allowed_types = ["vol", "bouclier", "esquive+", "reduction", "immunite"]

        utilitaire_items = sorted(set(
            i for i in user_inv if OBJETS.get(i, {}).get("type") in allowed_types
        ))

        if not utilitaire_items:
            return [app_commands.Choice(name="Aucun objet utilitaire disponible", value="")]

        suggestions = []
        for emoji in utilitaire_items:
            if current not in emoji:
                continue

            obj = OBJETS.get(emoji, {})
            typ = obj.get("type")

            if typ == "vol":
                label = f"{emoji} | Vole un objet à la cible"
            elif typ == "bouclier":
                label = f"{emoji} | +20 Points de Bouclier"
            elif typ == "esquive+":
                label = f"{emoji} | Esquive +20% pendant 3h"
            elif typ == "reduction":
                label = f"{emoji} | Réduction dégâts x0.5 pendant 4h"
            elif typ == "immunite":
                label = f"{emoji} | Immunité totale pendant 2h"
            else:
                label = f"{emoji} (Objet spécial)"

            suggestions.append(app_commands.Choice(name=label, value=emoji))

        return suggestions[:25]

async def voler_objet(ctx, user_id, target_id):
    guild_id = str(ctx.guild.id)

    # Récupération inventaires
    user_inv, _, _ = get_user_data(guild_id, user_id)
    target_inv, _, _ = get_user_data(guild_id, target_id)

    # Cible vide ?
    possible_items = [item for item in target_inv if item != "📦"]
    if not possible_items:
        return build_embed_from_item("🔍", f"{get_mention(ctx.guild, user_id)} tente de voler un objet...\nMais {get_mention(ctx.guild, target_id)} n’a rien d’intéressant. 😶")

    # Vol aléatoire
    stolen = random.choice(possible_items)
    target_inv.remove(stolen)
    user_inv.append(stolen)

    return build_embed_from_item("🔍", f"{get_mention(ctx.guild, user_id)} a volé **{stolen}** à {get_mention(ctx.guild, target_id)} ! 🫣")

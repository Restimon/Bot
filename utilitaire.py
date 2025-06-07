import discord
import random
import time

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

        # Bouclier
        if action["type"] == "bouclier":
            shields.setdefault(guild_id, {})[tid] = shields.get(guild_id, {}).get(tid, 0) + 20

            current_pb = shields[guild_id][tid]
            current_hp = get_user_data(guild_id, tid)[1]

            # Différencier soi-même / autre
            if uid == tid:
                description = (
                    f"{interaction.user.mention} a activé un **bouclier** de protection !\n"
                    f"🛡 Il gagne un total de **{current_pb} PB** → ❤️ {current_hp} PV / 🛡 {current_pb} PB"
                )
            else:
                mention_cible = get_mention(interaction.guild, tid)
                description = (
                    f"{interaction.user.mention} a activé un **bouclier** de protection pour {mention_cible} !\n"
                    f"🛡 Il gagne un total de **{current_pb} PB** → ❤️ {current_hp} PV / 🛡 {current_pb} PB"
                )

            embed = build_embed_from_item(item, description)
            success = True

        # Immunité
        elif action["type"] == "immunite":
            immunite_status.setdefault(guild_id, {})[tid] = time.time() + action.get("duree", 3600)

            mention_cible = interaction.user.mention if uid == tid else get_mention(interaction.guild, tid)
            description = (
                f"{mention_cible} bénéficie désormais d’une **immunité totale** pendant 2h."
            )
            embed = build_embed_from_item(item, description)
            success = True

        # Esquive+
        elif action["type"] == "esquive+":
            esquive_status.setdefault(guild_id, {})[tid] = {
                "start": time.time(),
                "duration": action.get("duree", 3600),
                "valeur": action.get("valeur", 0.2)
            }

            mention_cible = interaction.user.mention if uid == tid else get_mention(interaction.guild, tid)
            description = (
                f"{mention_cible} bénéficie désormais d’une **augmentation d’esquive** pendant 3h."
            )
            embed = build_embed_from_item(item, description)
            success = True

        # Réduction (Casque)
        elif action["type"] == "reduction":
            casque_status.setdefault(guild_id, {})[tid] = time.time() + action.get("duree", 3600)

            mention_cible = interaction.user.mention if uid == tid else get_mention(interaction.guild, tid)
            description = (
                f"{mention_cible} bénéficie désormais d’une **réduction des dégâts** pendant 4h."
            )
            embed = build_embed_from_item(item, description)
            success = True

        # Vol
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

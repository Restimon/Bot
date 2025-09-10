# fight.py
import asyncio
import discord
from discord import app_commands

from utils import OBJETS
from storage import get_user_data
from data import sauvegarder
from combat import apply_item_with_cooldown, apply_attack_chain

# ⏳ Filet de sécurité : évite les "réfléchit..." infinis côté Discord
TIMEOUT_INTERNE = 8


def register_fight_command(bot: discord.Client):
    """
    Enregistre la commande /fight :
      /fight target:<membre> item:<emoji>
    Permet d'attaquer un joueur avec un objet de type attaque/virus/poison/infection.
    """

    @bot.tree.command(
        name="fight",
        description="Attaque un autre membre avec un objet spécifique",
    )
    @app_commands.describe(
        target="La personne à attaquer",
        item="Objet d’attaque à utiliser (emoji présent dans ton inventaire)",
    )
    async def fight_slash(
        interaction: discord.Interaction,
        target: discord.Member,
        item: str,
    ):
        # On défère immédiatement pour éviter le timeout Discord
        await interaction.response.defer(thinking=True)

        try:
            guild_id = str(interaction.guild.id)
            uid = str(interaction.user.id)
            tid = str(target.id)

            # 🚫 Garde-fous
            if target.bot:
                await interaction.followup.send(
                    "🤖 Tu ne peux pas attaquer un bot, même s’il a l’air louche.",
                    ephemeral=True,
                )
                return

            if interaction.user.id == target.id:
                await interaction.followup.send(
                    "❌ Tu ne peux pas t’attaquer toi-même.",
                    ephemeral=True,
                )
                return

            # 🎯 Validation de l’objet
            action = OBJETS.get(item)
            if not isinstance(action, dict):
                await interaction.followup.send(
                    "❌ Objet inconnu ou non autorisé.",
                    ephemeral=True,
                )
                return

            # 📦 Vérifie l'inventaire de l'attaquant
            user_inv, _, _ = get_user_data(guild_id, uid)
            if item not in user_inv:
                await interaction.followup.send(
                    "❌ Tu n’as pas cet objet dans ton inventaire.",
                    ephemeral=True,
                )
                return

            # 🔎 Vérifie le type d'objet (armes valides)
            types_valides = {"attaque", "attaque_chaine", "virus", "poison", "infection"}
            if action.get("type") not in types_valides:
                await interaction.followup.send(
                    "⚠️ Cet objet n’est pas une arme valide !",
                    ephemeral=True,
                )
                return

            # ☠️ Cas particulier : Attaque en chaîne
            if action.get("type") == "attaque_chaine" or item == "☠️":
                try:
                    # La fonction envoie elle-même les messages
                    await asyncio.wait_for(
                        apply_attack_chain(interaction, uid, tid, item, action),
                        timeout=TIMEOUT_INTERNE,
                    )
                except asyncio.TimeoutError:
                    await interaction.followup.send(
                        "⏳ L’attaque en chaîne a pris trop de temps. Réessaie dans un instant.",
                        ephemeral=True,
                    )
                    return
                except Exception as e:
                    await interaction.followup.send(
                        f"❌ Erreur pendant l’attaque en chaîne : {e}",
                        ephemeral=True,
                    )
                    return

                # ✅ On consomme l'objet si le moteur ne demande pas de le conserver
                if not action.get("no_consume", False):
                    try:
                        user_inv.remove(item)
                        sauvegarder()
                    except Exception:
                        pass
                return

            # 🔹 Attaques « normales » (attaque / virus / poison / infection)
            try:
                # Le moteur enverra lui-même l’embed; on récupère juste le flag de succès
                _, success = await asyncio.wait_for(
                    apply_item_with_cooldown(interaction, uid, tid, item, action),
                    timeout=TIMEOUT_INTERNE,
                )
            except asyncio.TimeoutError:
                await interaction.followup.send(
                    "⏳ L’attaque a mis trop de temps à se résoudre. Réessaie.",
                    ephemeral=True,
                )
                return
            except Exception as e:
                await interaction.followup.send(
                    f"❌ Erreur pendant l’attaque : {e}",
                    ephemeral=True,
                )
                return

            # ✅ Consommer l'objet si l’attaque a été validée ET pas de “pas_de_conso”
            if success and not action.get("no_consume", False):
                try:
                    user_inv.remove(item)
                    sauvegarder()
                except Exception:
                    pass

        except Exception as e:
            # 🧯 Dernier filet : on tente d'informer l'utilisateur quoi qu'il arrive
            try:
                await interaction.followup.send(
                    f"❌ Erreur inattendue : {e}",
                    ephemeral=True,
                )
            except Exception:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        f"❌ Erreur inattendue : {e}",
                        ephemeral=True,
                    )

    # ✅ Autocomplétion : propose uniquement les armes présentes dans l’inventaire
    @fight_slash.autocomplete("item")
    async def autocomplete_items(interaction: discord.Interaction, current: str):
        guild_id = str(interaction.guild.id)
        uid = str(interaction.user.id)
        user_inv, _, _ = get_user_data(guild_id, uid)

        types_valides = {"attaque", "attaque_chaine", "virus", "poison", "infection"}
        # On filtre : uniquement des strings/emoji et des types d'attaque
        attack_items = sorted({
            i for i in user_inv
            if isinstance(i, str) and OBJETS.get(i, {}).get("type") in types_valides
        })

        if not attack_items:
            return [app_commands.Choice(name="Aucune arme disponible", value="")]

        suggestions = []
        cur = (current or "").strip()
        for emoji in attack_items:
            if cur and cur not in emoji:
                continue

            obj = OBJETS.get(emoji, {})
            typ = obj.get("type")

            if typ == "attaque":
                label = f"{emoji} | {obj.get('degats', '?')} dmg, {int(obj.get('crit', 0)*100)}% crit"
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

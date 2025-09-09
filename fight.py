# fight.py
import asyncio
import discord
from discord import app_commands

from utils import OBJETS
from storage import get_user_data
from data import sauvegarder
from combat import apply_item_with_cooldown, apply_attack_chain

# filet de sécurité pour ne jamais bloquer "GotValis réfléchit…"
TIMEOUT_INTERNAL = 8


def register_fight_command(bot):
    @bot.tree.command(
        name="fight",
        description="Attaque un autre membre avec un objet spécifique",
    )
    @app_commands.describe(
        target="La personne à attaquer",
        item="Objet d’attaque à utiliser (emoji)",
    )
    async def fight_slash(
        interaction: discord.Interaction,
        target: discord.Member,
        item: str,
    ):
        await interaction.response.defer(thinking=True)

        try:
            guild_id = str(interaction.guild.id)
            uid = str(interaction.user.id)
            tid = str(target.id)

            # Garde-fous
            if target.bot:
                await interaction.followup.send(
                    "🤖 Tu ne peux pas attaquer un bot, même s’il a l’air louche.",
                    ephemeral=True,
                )
                return

            if interaction.user.id == target.id:
                await interaction.followup.send(
                    "❌ Tu ne peux pas t'attaquer toi-même.",
                    ephemeral=True,
                )
                return

            action = OBJETS.get(item)
            if not isinstance(action, dict):
                await interaction.followup.send(
                    "❌ Objet inconnu ou non autorisé.",
                    ephemeral=True,
                )
                return

            # Inventaire de l’attaquant (liste d’emojis/strings)
            user_inv, _, _ = get_user_data(guild_id, uid)
            if item not in user_inv:
                await interaction.followup.send(
                    "❌ Tu n’as pas cet objet dans ton inventaire.",
                    ephemeral=True,
                )
                return

            if action.get("type") not in {"attaque", "attaque_chaine", "virus", "poison", "infection"}:
                await interaction.followup.send(
                    "⚠️ Cet objet n’est pas une arme valide !",
                    ephemeral=True,
                )
                return

            # ☠️ Attaque en chaîne
            if item == "☠️":
                try:
                    _ = await asyncio.wait_for(
                        apply_attack_chain(interaction, uid, tid, item, action),
                        timeout=TIMEOUT_INTERNAL,
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

                # Retire l'objet après l’attaque en chaîne
                try:
                    user_inv.remove(item)
                    sauvegarder()
                except Exception:
                    pass

                return

            # 🔹 Attaques normales
            try:
                embed, success = await asyncio.wait_for(
                    apply_item_with_cooldown(interaction, uid, tid, item, action),
                    timeout=TIMEOUT_INTERNAL,
                )
            except asyncio.TimeoutError:
                await interaction.followup.send(
                    "⏳ L’attaque a pris trop de temps à se résoudre. Réessaie.",
                    ephemeral=True,
                )
                return
            except Exception as e:
                await interaction.followup.send(
                    f"❌ Erreur pendant l’attaque : {e}",
                    ephemeral=True,
                )
                return

            # S’il n’y a pas d’embed retourné, on envoie au moins un message court
            if embed is None:
                await interaction.followup.send(
                    f"{interaction.user.mention} lance son attaque sur {target.mention}…",
                    ephemeral=False,
                )
            else:
                await interaction.followup.send(embed=embed, ephemeral=False)

            # Retirer l'objet si succès
            if success:
                try:
                    user_inv.remove(item)
                    sauvegarder()
                except Exception:
                    pass

        except Exception as e:
            # Dernier filet : toujours répondre
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

    # ✅ Autocomplétion des objets d'attaque avec description
    @fight_slash.autocomplete("item")
    async def autocomplete_items(interaction: discord.Interaction, current: str):
        guild_id = str(interaction.guild.id)
        uid = str(interaction.user.id)
        user_inv, _, _ = get_user_data(guild_id, uid)

        attack_types = {"attaque", "attaque_chaine", "virus", "poison", "infection"}
        attack_items = sorted({i for i in user_inv if isinstance(i, str) and OBJETS.get(i, {}).get("type") in attack_types})

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

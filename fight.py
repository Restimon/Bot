# fight.py

import asyncio
import discord
from discord import app_commands
from utils import OBJETS
from storage import get_user_data
from data import sauvegarder
from combat import apply_item_with_cooldown, apply_attack_chain
from embeds import build_embed_from_item

TIMEOUT_INTERNAL = 8  # filet de sécurité


def register_fight_command(bot):
    @bot.tree.command(name="fight", description="Attaque un autre membre avec un objet spécifique")
    @app_commands.describe(target="La personne à attaquer", item="Objet d’attaque à utiliser (emoji)")
    async def fight_slash(interaction: discord.Interaction, target: discord.Member, item: str):
        await interaction.response.defer(thinking=True)

        try:
            guild_id = str(interaction.guild.id)
            uid = str(interaction.user.id)
            tid = str(target.id)

            if target.bot:
                await interaction.followup.send("🤖 Tu ne peux pas attaquer un bot.", ephemeral=True)
                return

            if interaction.user.id == target.id:
                await interaction.followup.send("❌ Tu ne peux pas t'attaquer toi-même.", ephemeral=True)
                return

            action = OBJETS.get(item)
            if not action:
                await interaction.followup.send("❌ Objet inconnu ou non autorisé.", ephemeral=True)
                return

            user_inv, _, _ = get_user_data(guild_id, uid)
            if item not in user_inv:
                await interaction.followup.send("❌ Tu n’as pas cet objet dans ton inventaire.", ephemeral=True)
                return

            if action.get("type") not in {"attaque", "attaque_chaine", "virus", "poison", "infection"}:
                await interaction.followup.send("⚠️ Cet objet n’est pas une arme valide !", ephemeral=True)
                return

            # ☠️ Attaque en chaîne
            if item == "☠️":
                try:
                    await asyncio.wait_for(
                        apply_attack_chain(interaction, uid, tid, item, action),  # (ctx, uid, tid, item, action)
                        timeout=TIMEOUT_INTERNAL
                    )
                except asyncio.TimeoutError:
                    await interaction.followup.send("⏳ L’attaque en chaîne a pris trop de temps. Réessaie.", ephemeral=True)
                    return

                # Consommer l’objet
                if item in user_inv:
                    user_inv.remove(item)
                    sauvegarder()
                return

            # 🔹 Attaque normale
            try:
                embed, success = await asyncio.wait_for(
                    apply_item_with_cooldown(interaction, uid, tid, item, action),  # (ctx, uid, tid, item, action)
                    timeout=TIMEOUT_INTERNAL
                )
            except asyncio.TimeoutError:
                await interaction.followup.send("⏳ L’attaque a pris trop de temps à se résoudre. Réessaie.", ephemeral=True)
                return

            if not embed:
                embed = build_embed_from_item(item, f"{interaction.user.mention} attaque {target.mention}…")

            await interaction.followup.send(embed=embed)

            if success and item in user_inv:
                user_inv.remove(item)
                sauvegarder()

        except Exception as e:
            # Toujours répondre
            try:
                await interaction.followup.send(f"❌ Erreur inattendue : {e}", ephemeral=True)
            except Exception:
                if not interaction.response.is_done():
                    await interaction.response.send_message(f"❌ Erreur inattendue : {e}", ephemeral=True)

    # Autocomplétion
    @fight_slash.autocomplete("item")
    async def autocomplete_items(interaction: discord.Interaction, current: str):
        guild_id = str(interaction.guild.id)
        uid = str(interaction.user.id)
        user_inv, _, _ = get_user_data(guild_id, uid)

        attack_types = {"attaque", "attaque_chaine", "virus", "poison", "infection"}
        attack_items = sorted({i for i in user_inv if OBJETS.get(i, {}).get("type") in attack_types})

        if not attack_items:
            return [app_commands.Choice(name="Aucune arme disponible", value="")]

        cur = (current or "").strip()
        suggestions = []
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

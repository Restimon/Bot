# heal.py
import time
import discord
from discord import app_commands

from utils import OBJETS
from storage import get_user_data
from data import sauvegarder, virus_status, poison_status, infection_status, regeneration_status
from embeds import build_embed_from_item
from combat import apply_item_with_cooldown  # <- pour les soins "normaux"

SPECIAL_HEAL_ITEMS = ["💉", "💕"]


def register_heal_command(bot: discord.Client):
    @bot.tree.command(name="heal", description="Soigne toi ou un autre membre avec un objet de soin")
    @app_commands.describe(
        target="Membre à soigner (ou toi-même)",
        item="Objet de soin à utiliser (emoji)"
    )
    async def heal_slash(
        interaction: discord.Interaction,
        target: discord.Member | None = None,
        item: str | None = None
    ):
        await interaction.response.defer(thinking=True)

        # ---------- Préparation ----------
        member = interaction.user
        guild_id = str(interaction.guild.id)
        uid = str(member.id)
        target = target or member
        tid = str(target.id)

        # ---------- Garde-fous ----------
        if target.bot:
            return await interaction.followup.send("❌ Tu ne peux pas soigner un bot.", ephemeral=True)

        user_inv, _, _ = get_user_data(guild_id, uid)

        if not item or item not in OBJETS:
            return await interaction.followup.send("❌ Objet inconnu ou non spécifié.", ephemeral=True)

        if item not in user_inv:
            return await interaction.followup.send(
                f"🚫 GotValis ne détecte pas {item} dans ton inventaire.", ephemeral=True
            )

        # ---------- Cas spéciaux ----------
        # 💉 Vaccin : purge statuts, uniquement sur soi
        if item == "💉":
            target = member
            tid = uid

            virus_status.setdefault(guild_id, {})
            poison_status.setdefault(guild_id, {})
            infection_status.setdefault(guild_id, {})

            effaces: list[str] = []
            if tid in virus_status[guild_id]:
                del virus_status[guild_id][tid]
                effaces.append("🦠 virus")
            if tid in poison_status[guild_id]:
                del poison_status[guild_id][tid]
                effaces.append("🧪 poison")
            if tid in infection_status[guild_id]:
                del infection_status[guild_id][tid]
                effaces.append("🧟 infection")

            # Consommation
            try:
                user_inv.remove("💉")
            except ValueError:
                pass
            sauvegarder()

            if effaces:
                description = (
                    f"{member.mention} s’est administré un vaccin.\n"
                    f"{' + '.join(effaces).capitalize()} éradiqué(s) avec succès !"
                )
            else:
                description = (
                    f"Aucun virus, poison ou infection détecté chez {member.mention}. "
                    f"L’injection était inutile."
                )

            embed = build_embed_from_item(
                "💉",
                description,
                is_heal_other=False,
                disable_gif=False,
                custom_title="📢 Vaccination GotValis"
            )
            return await interaction.followup.send(embed=embed, ephemeral=False)

        # 💕 Régénération (3 PV / 30min pendant 3h)
        if item == "💕":
            regeneration_status.setdefault(guild_id, {})[tid] = {
                "start": time.time(),
                "duration": 3 * 3600,
                "last_tick": 0,
                "source": uid,
                "channel_id": interaction.channel.id
            }

            try:
                user_inv.remove("💕")
            except ValueError:
                pass
            sauvegarder()

            # Utilise build_embed_from_item pour profiter du GIF si défini dans OBJETS
            description = (
                f"✨ {member.mention} a déclenché une régénération pour {target.mention} !\n"
                f"{target.mention} récupérera **3 PV toutes les 30 minutes pendant 3 heures.**"
            )
            embed = build_embed_from_item(
                "💕",
                description,
                is_heal_other=(target.id != member.id),
                disable_gif=False,
                custom_title="💕 Régénération activée"
            )
            return await interaction.followup.send(embed=embed, ephemeral=False)

        # ---------- Soin "classique" (OBJETS[item]['type'] == 'soin') ----------
        action = OBJETS.get(item, {})
        if action.get("type") != "soin":
            return await interaction.followup.send("⚠️ Cet objet n’est pas destiné à soigner !", ephemeral=True)

        try:
            # ⚠️ Pour un soin, apply_item_with_cooldown **retourne un embed** (il n’envoie pas lui-même)
            embed, success = await apply_item_with_cooldown(interaction, uid, tid, item, action)
        except Exception as e:
            return await interaction.followup.send(f"❌ Erreur pendant le soin : `{e}`", ephemeral=True)

        # Envoi unique (pas de doublon)
        if embed is not None:
            await interaction.followup.send(embed=embed, ephemeral=False)
        else:
            # Fallback ultra-minimal (devrait rarement arriver)
            await interaction.followup.send(
                f"{member.mention} tente de soigner {target.mention}…", ephemeral=False
            )

        # Consommation si succès et pas d’override passif (ex: Marn / Rouven)
        if success and not action.get("no_consume", False):
            try:
                user_inv.remove(item)
            except ValueError:
                pass
            sauvegarder()

    # ------- Autocomplete -------
    @heal_slash.autocomplete("item")
    async def autocomplete_items(interaction: discord.Interaction, current: str):
        guild_id = str(interaction.guild.id)
        uid = str(interaction.user.id)
        user_inv, _, _ = get_user_data(guild_id, uid)

        # Items de soin + spéciaux
        options = sorted({
            i for i in user_inv
            if (OBJETS.get(i, {}).get("type") == "soin") or (i in SPECIAL_HEAL_ITEMS)
        })

        def format_label(emoji: str) -> str:
            meta = OBJETS.get(emoji, {})
            typ = meta.get("type")
            if typ == "soin":
                return f"{emoji} {meta.get('soin', 0)} PV (🎯 {int(meta.get('crit', 0) * 100)}%)"
            if emoji == "💉":
                return f"{emoji} Vaccin : supprime virus / poison / infection"
            if emoji == "💕":
                return f"{emoji} Régénération : 3 PV / 30min pendant 3h"
            return emoji

        cur = (current or "").strip()
        suggestions = [
            app_commands.Choice(name=format_label(e), value=e)
            for e in options if (not cur or cur in e)
        ]
        return suggestions[:25]

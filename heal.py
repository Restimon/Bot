# heal.py
import discord
import time
from discord import app_commands
from utils import OBJETS
from storage import get_user_data
from data import sauvegarder, virus_status, poison_status, infection_status, regeneration_status
from embeds import build_embed_from_item
from passifs import appliquer_passif  # ✅ Ajouté pour les passifs

SPECIAL_HEAL_ITEMS = ["💉", "💕"]

def register_heal_command(bot):
    @bot.tree.command(name="heal", description="Soigne toi ou un autre membre avec un objet de soin")
    @app_commands.describe(target="Membre à soigner (ou toi-même)", item="Objet de soin à utiliser (emoji)")
    async def heal_slash(interaction: discord.Interaction, target: discord.Member = None, item: str = None):
        await interaction.response.defer(thinking=True)

        member = interaction.user
        guild_id = str(interaction.guild.id)
        uid = str(member.id)
        target = target or member
        tid = str(target.id)

        if target.bot:
            return await interaction.followup.send("❌ Tu ne peux pas soigner un bot.", ephemeral=True)

        user_inv, _, _ = get_user_data(guild_id, uid)

        if not item or item not in OBJETS:
            return await interaction.followup.send("❌ Objet inconnu ou non spécifié.", ephemeral=True)

        if item not in user_inv:
            return await interaction.followup.send(f"🚫 GotValis ne détecte pas {item} dans ton inventaire.", ephemeral=True)

        if OBJETS[item]["type"] != "soin" and item not in SPECIAL_HEAL_ITEMS:
            return await interaction.followup.send("⚠️ Cet objet n’est pas destiné à soigner !", ephemeral=True)

        if item == "💉":
            # Vaccin ne s'utilise que sur soi-même
            target = member
            tid = uid
        
            virus_status.setdefault(guild_id, {})
            poison_status.setdefault(guild_id, {})
            infection_status.setdefault(guild_id, {})
        
            effaces = []
        
            if tid in virus_status[guild_id]:
                del virus_status[guild_id][tid]
                effaces.append("🦠 virus")
            if tid in poison_status[guild_id]:
                del poison_status[guild_id][tid]
                effaces.append("🧪 poison")
            if tid in infection_status[guild_id]:
                del infection_status[guild_id][tid]
                effaces.append("🧟 infection")
        
            user_inv.remove("💉")
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
        
            return await interaction.followup.send(embed=embed)

        # 💕 Régénération
        if item == "💕":
            regeneration_status.setdefault(guild_id, {})[tid] = {
                "start": time.time(),
                "duration": 3 * 3600,
                "last_tick": 0,
                "source": uid,
                "channel_id": interaction.channel.id
            }
            user_inv.remove("💕")
            sauvegarder()
    
            embed = discord.Embed(
                title="💕 Régénération activée",
                description=(f"✨ {member.mention} a déclenché une régénération pour {target.mention} ! 💕\n\n"
                             f"{target.mention} récupère **3 PV toutes les 30 minutes pendant 3 heures.**"),
                color=discord.Color.green()
            )
            return await interaction.followup.send(embed=embed)

        # ✅ Objets de soin classiques
        from combat import apply_item_with_cooldown
        action = OBJETS.get(item)
        embed, success = await apply_item_with_cooldown(interaction, uid, tid, item, action)

        # ✅ PASSIFS après soin
        if success and action.get("type") == "soin":
            contexte = "soin"
            données_passif = {
                "guild_id": guild_id,
                "soigneur_id": uid,
                "cible_id": tid,
                "ctx": interaction,
                "objet": item,
                "valeur_soin": action.get("soin", 0)
            }
            effets = []
            result_passif_soigneur = appliquer_passif(uid, contexte, données_passif)
            result_passif_cible = appliquer_passif(tid, "soin_reçu", données_passif)

            if result_passif_soigneur:
                effets.extend(result_passif_soigneur.get("embeds", []))
            if result_passif_cible:
                effets.extend(result_passif_cible.get("embeds", []))

            for effet_embed in effets:
                await interaction.followup.send(embed=effet_embed)

        if success:
            user_inv.remove(item)
        sauvegarder()
        await interaction.followup.send(embed=embed)

    @heal_slash.autocomplete("item")
    async def autocomplete_items(interaction: discord.Interaction, current: str):
        guild_id = str(interaction.guild.id)
        uid = str(interaction.user.id)
        user_inv, _, _ = get_user_data(guild_id, uid)

        options = sorted(set(
            i for i in user_inv if OBJETS.get(i, {}).get("type") == "soin" or i in SPECIAL_HEAL_ITEMS
        ))

        def format_label(emoji):
            o = OBJETS.get(emoji, {})
            typ = o.get("type", "inconnu")
            if typ == "soin":
                return f"{emoji} {o.get('soin')} PV (🎯 {int(o.get('crit', 0) * 100)}%)"
            if emoji == "💉": return f"{emoji} Vaccin : soigne les virus, poison ou infection"
            if emoji == "💕": return f"{emoji} Régénère 3 PV / 30min pendant 3h"
            return f"{emoji}"

        return [
            app_commands.Choice(name=format_label(e), value=e)
            for e in options if current in e
        ][:25]

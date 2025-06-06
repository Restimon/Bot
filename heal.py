
import discord
import time
from discord import app_commands
from utils import OBJETS
from storage import get_user_data
from data import sauvegarder, virus_status, hp
from embeds import build_embed_from_item

SPECIAL_HEAL_ITEMS = ["💉", "🛡", "👟", "🪖", "💕", "⭐️"]

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

        # 💉 Vaccin — soigne tous les statuts
        if item == "💉":
            if tid != uid:
                return await interaction.followup.send("💉 Le vaccin ne peut être utilisé que **sur toi-même**.", ephemeral=True)

            from data import virus_status, poison_status, infection_status
            virus_status.setdefault(guild_id, {})
            poison_status.setdefault(guild_id, {})
            infection_status.setdefault(guild_id, {})

            effaces = []

            if uid in virus_status[guild_id]:
                del virus_status[guild_id][uid]
                effaces.append("🦠 virus")
            if uid in poison_status[guild_id]:
                del poison_status[guild_id][uid]
                effaces.append("🧪 poison")
            if uid in infection_status[guild_id]:
                del infection_status[guild_id][uid]
                effaces.append("🧟 infection")

            user_inv.remove("💉")
            sauvegarder()

            if effaces:
                description = f"{member.mention} s’est administré un vaccin.\n" \
                              f"{' + '.join(effaces).capitalize()} éradiqué(s) avec succès !"
            else:
                description = f"Aucun virus, poison ou infection détecté chez {member.mention}. L’injection était inutile."

            # ✅ Utilise ton build_embed_from_item
            embed = build_embed_from_item(
                "💉",
                description,
                is_heal_other=False,
                disable_gif=False,
                custom_title="📢 Vaccination GotValis"
            )

            return await interaction.followup.send(embed=embed)

        # ⭐️ Immunité
        if item == "⭐️":
            from data import immunite_status
            immunite_status.setdefault(guild_id, {})[uid] = {"start": time.time(), "duration": 2 * 3600}
            user_inv.remove("⭐️")
            sauvegarder()
            return await interaction.followup.send(embed=discord.Embed(
                title="⭐️ Immunité activée",
                description=f"{member.mention} est maintenant **invulnérable à tout dégât pendant 2 heures**.",
                color=discord.Color.gold()
            ))

        # 🛡 Bouclier
        if item == "🛡":
            from data import shields
            shields.setdefault(guild_id, {})[tid] = 20
            user_inv.remove("🛡")
            sauvegarder()

            pv = hp[guild_id].get(tid, 100)
            pb = shields[guild_id][tid]

            if uid == tid:
                ligne_1 = f"{member.mention} a utilisé un **bouclier de protection** !"
            else:
                ligne_1 = f"{member.mention} a activé un **bouclier** pour {target.mention} !"

            ligne_2 = f"🛡 Il gagne un total de **20 PB** → ❤️ {pv} PV / 🛡 {pb} PB"

            embed = discord.Embed(
                title="🛡 Bouclier activé",
                description=f"{ligne_1}\n{ligne_2}",
                color=discord.Color.blue()
            )
            embed.set_image(url="https://media.giphy.com/media/rR7wrU76zfWnf7xBDR/giphy.gif")

            return await interaction.followup.send(embed=embed)

        # 🪖 Casque
        if item == "🪖":
            from data import casque_status
            casque_status.setdefault(guild_id, {})[uid] = {"start": time.time(), "duration": 4 * 3600}
            user_inv.remove("🪖")
            sauvegarder()
            return await interaction.followup.send(embed=discord.Embed(
                title="🪖 Casque équipé",
                description=f"{member.mention} a équipé un **casque** réduisant les dégâts reçus de 50% pendant 4 heures.",
                color=discord.Color.orange()
            ))

        # 💕 Régénération
        if item == "💕":
            from data import regeneration_status
            regeneration_status.setdefault(guild_id, {})[tid] = {
                "start": time.time(),
                "duration": 3 * 3600,
                "last_tick": 0,
                "source": uid,
                "channel_id": interaction.channel.id
            }
            user_inv.remove("💕")
            sauvegarder()
            await interaction.channel.send(f"✨ {member.mention} a déclenché une régénération pour {target.mention} ! 💕")
            return await interaction.followup.send(embed=discord.Embed(
                title="💕 Régénération activée",
                description=f"{target.mention} récupère **3 PV toutes les 30 minutes pendant 3 heures.**",
                color=discord.Color.green()
            ))

        # 👟 Esquive
        if item == "👟":
            from data import esquive_bonus
            esquive_bonus.setdefault(guild_id, {})[uid] = {"start": time.time(), "duration": 3 * 3600}
            user_inv.remove("👟")
            sauvegarder()
            return await interaction.followup.send(embed=discord.Embed(
                title="👟 Esquive améliorée",
                description=f"{member.mention} bénéficie maintenant d’un **bonus d’esquive de 20% pendant 3 heures.**",
                color=discord.Color.green()
            ))

        # ✅ Objets de soin classiques
        from combat import apply_item_with_cooldown
        action = OBJETS.get(item)
        embed, success = await apply_item_with_cooldown(interaction, uid, tid, item, action)
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
                return f"{emoji} {o.get('soin')} PV (🎯 {int(o.get('crit',0)*100)}%)"
            if emoji == "💉": return f"{emoji} Vaccin : soigne les virus, poison ou infection"
            if emoji == "🛡": return f"{emoji} Bouclier : +20 PV absorbants"
            if emoji == "👟": return f"{emoji} Esquive : +20% pendant 3h"
            if emoji == "🪖": return f"{emoji} Casque : dégâts ÷2 pendant 4h"
            if emoji == "💕": return f"{emoji} Régénère 3 PV / 30min pendant 3h"
            if emoji == "⭐️": return f"{emoji} Immunité : invulnérable 2h"
            return f"{emoji}"

        return [
            app_commands.Choice(name=format_label(e), value=e)
            for e in options if current in e
        ][:25]

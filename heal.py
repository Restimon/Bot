import discord
import time
from discord import app_commands
from utils import OBJETS
from storage import get_user_data
from data import sauvegarder, virus_status

# ✅ Objets utilisables via /heal en plus des objets de soin classiques
SPECIAL_HEAL_ITEMS = ["💉", "🛡", "👟", "🪖", "💕", "⭐️"]

def register_heal_command(bot):
    @bot.tree.command(name="heal", description="Soigne toi ou un autre membre avec un objet de soin")
    @app_commands.describe(target="Membre à soigner (ou toi-même)", item="Objet de soin à utiliser (emoji)")
    async def heal_slash(interaction: discord.Interaction, target: discord.Member = None, item: str = None):
        await interaction.response.defer(thinking=True)

        guild_id = str(interaction.guild.id)
        uid = str(interaction.user.id)
        tid = str(target.id) if target else uid

        user_inv, _, _ = get_user_data(guild_id, uid)

        if not item or item not in OBJETS:
            return await interaction.followup.send("❌ Objet inconnu ou non spécifié.", ephemeral=True)

        if item not in user_inv:
            return await interaction.followup.send(f"🚫 SomniCorp ne détecte pas {item} dans ton inventaire.", ephemeral=True)

        if OBJETS[item]["type"] != "soin" and item not in SPECIAL_HEAL_ITEMS:
            return await interaction.followup.send("⚠️ Cet objet n’est pas destiné à soigner !", ephemeral=True)

        # 💉 Vaccin — utilisable uniquement sur soi-même
        if item == "💉":
            if tid != uid:
                return await interaction.followup.send("💉 Le vaccin ne peut être utilisé que **sur toi-même**.", ephemeral=True)

            virus_status.setdefault(guild_id, {})
            if uid in virus_status[guild_id]:
                del virus_status[guild_id][uid]
                description = f"💉 {interaction.user.mention} s’est administré un vaccin.\n🦠 Le virus a été **éradiqué** avec succès !"
            else:
                description = f"💉 Aucun virus détecté chez {interaction.user.mention}. L’injection était inutile."

            user_inv.remove("💉")
            sauvegarder()
            embed = discord.Embed(title="📢 Vaccination SomniCorp", description=description, color=discord.Color.green())
            return await interaction.followup.send(embed=embed)

        # ⭐️ Immunité
        if item == "⭐️":
            from data import immunite_status
            immunite_status.setdefault(guild_id, {})
            immunite_status[guild_id][uid] = {
                "start": time.time(),
                "duration": 2 * 3600
            }
            user_inv.remove("⭐️")
            sauvegarder()
            embed = discord.Embed(
                title="⭐️ Immunité activée",
                description=f"{interaction.user.mention} est maintenant **invulnérable à tout dégât pendant 2 heures**.",
                color=discord.Color.gold()
            )
            return await interaction.followup.send(embed=embed)

        # 🛡 Bouclier
        if item == "🛡":
            from data import shields
            shields.setdefault(guild_id, {})
            shields[guild_id][tid] = 20
            user_inv.remove("🛡")
            sauvegarder()
            embed = discord.Embed(
                title="🛡 Bouclier activé",
                description=f"{interaction.user.mention} a activé un **bouclier de 20 points** pour {interaction.guild.get_member(int(tid)).mention} !",
                color=discord.Color.blue()
            )
            return await interaction.followup.send(embed=embed)

        # 🪖 Casque
        if item == "🪖":
            from data import casque_bonus
            casque_bonus.setdefault(guild_id, {})
            casque_bonus[guild_id][uid] = {
                "start": time.time(),
                "duration": 4 * 3600
            }
            user_inv.remove("🪖")
            sauvegarder()
            embed = discord.Embed(
                title="🪖 Casque équipé",
                description=f"{interaction.user.mention} a équipé un **casque** qui réduit les dégâts reçus de 50% pendant 4 heures.",
                color=discord.Color.orange()
            )
            return await interaction.followup.send(embed=embed)

        # 💕 Régénération
        if item == "💕":
            from data import regeneration_status
            regeneration_status.setdefault(guild_id, {})
            regeneration_status[guild_id][tid] = {
                "start": time.time(),
                "duration": 3 * 3600,
                "last_tick": 0,
                "source": uid,
                "channel_id": interaction.channel.id
            }
            user_inv.remove("💕")
            sauvegarder()
            target_mention = interaction.guild.get_member(int(tid)).mention
            embed = discord.Embed(
                title="💕 Régénération activée",
                description=f"{target_mention} bénéficie d'une **régénération** de 3 PV toutes les 30 min pendant 3 heures.",
                color=discord.Color.green()
            )
            await interaction.channel.send(
                f"✨ {interaction.user.mention} a déclenché une régénération pour {target_mention} ! 💕"
            )
            return await interaction.followup.send(embed=embed)

        # 👟 Esquive
        if item == "👟":
            from data import esquive_bonus
            esquive_bonus.setdefault(guild_id, {})
            esquive_bonus[guild_id][uid] = {
                "start": time.time(),
                "duration": 3 * 3600
            }
            user_inv.remove("👟")
            sauvegarder()
            embed = discord.Embed(
                title="👟 Esquive améliorée !",
                description=f"{interaction.user.mention} bénéficie maintenant d’un **bonus d’esquive de 20%** pendant 3 heures.",
                color=discord.Color.green()
            )
            return await interaction.followup.send(embed=embed)

        # ✅ Objets de soin classiques
        from combat import apply_item_with_cooldown
        embed, success = await apply_item_with_cooldown(uid, tid, item, interaction)
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

        if not options:
            return [app_commands.Choice(name="Aucun objet de soin", value="")]

        return [
            app_commands.Choice(name=emoji, value=emoji)
            for emoji in options if current in emoji
        ][:25]

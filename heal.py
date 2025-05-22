import discord
from discord import app_commands
from utils import OBJETS
from storage import get_user_data
from data import sauvegarder, virus_status
from combat import apply_item_with_cooldown

# Stockage temporaire des boucliers
shields = {}

def register_heal_command(bot):
    @bot.tree.command(name="heal", description="Soigne toi ou un autre membre avec un objet de soin")
    @app_commands.describe(target="Membre à soigner (ou toi-même)", item="Objet de soin à utiliser (emoji)")
    async def heal_slash(interaction: discord.Interaction, target: discord.Member = None, item: str = None):
        guild_id = str(interaction.guild.id)
        uid = str(interaction.user.id)
        tid = str(target.id) if target else uid

        user_inv, _, _ = get_user_data(guild_id, uid)

        if not item or item not in OBJETS:
            return await interaction.response.send_message("❌ Objet inconnu ou non spécifié.", ephemeral=True)

        if item not in user_inv:
            return await interaction.response.send_message(f"🚫 SomniCorp ne détecte pas {item} dans ton inventaire.", ephemeral=True)

        if OBJETS[item]["type"] != "soin" and item != "💉" and item != "🛡":
            return await interaction.response.send_message("⚠️ Cet objet n’est pas destiné à soigner !", ephemeral=True)
        # ⭐️ Immunité : invulnérabilité pendant 2 heures
        if item == "⭐️":
            from data import immunite_status  # assure-toi que ce soit bien importé

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
            return await interaction.response.send_message(embed=embed)
        # 💉 Vaccin
        if item == "💉":
            virus_status.setdefault(guild_id, {})
            if uid in virus_status[guild_id]:
                del virus_status[guild_id][uid]
                description = f"💉 {interaction.user.mention} s’est administré un vaccin.\n🦠 Le virus a été **éradiqué** avec succès !"
            else:
                description = f"💉 Aucun virus détecté chez {interaction.user.mention}. L’injection était inutile."

            user_inv.remove("💉")
            sauvegarder()
            embed = discord.Embed(title="📢 Vaccination SomniCorp", description=description, color=discord.Color.green())
            return await interaction.response.send_message(embed=embed)

        # 🛡 Bouclier : uniquement utilisable ici
        if item == "🛡":
            from data import shields as global_shields  # Pour conserver l'effet globalement
            global_shields.setdefault(guild_id, {})
            global_shields[guild_id][tid] = 20

            user_inv.remove("🛡")
            sauvegarder()
            embed = discord.Embed(
                title="🛡 Bouclier activé",
                description=f"{interaction.user.mention} a activé un **bouclier de 20 points** pour {interaction.guild.get_member(int(tid)).mention} !",
                color=discord.Color.blue()
            )
            return await interaction.response.send_message(embed=embed)
            
        # 🪖 Casque : réduit les dégâts reçus de 50% pendant 4 heures
        if item == "🪖":
            from data import casque_bonus  # assure-toi que cette structure existe dans data.py

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
            return await interaction.response.send_message(embed=embed)
            
        # 💕 Régénération : soigne 3 PV toutes les 30 min pendant 3h
        if item == "💕":
            from data import regeneration_status  # Assure-toi que ce dict est bien importé

            regeneration_status.setdefault(guild_id, {})
            regeneration_status[guild_id][tid] = {
                "start": time.time(),
                "duration": 3 * 3600,
                "last_tick": 0,
                "source": uid,
                "channel_id": interaction.channel.id  # ✅ indispensable pour afficher les tics au bon endroit
            }

            user_inv.remove("💕")
            sauvegarder()

            embed = discord.Embed(
                title="💕 Régénération activée",
                description=f"{interaction.guild.get_member(int(tid)).mention} bénéficie d'une **régénération** de 3 PV toutes les 30 min pendant 3 heures.",
                color=discord.Color.green()
            )
            return await interaction.response.send_message(embed=embed)

        # Traitement spécial pour 👟 esquive
        if item == "👟":
            esquive_duration = 3 * 3600  # 3 heures
            from data import esquive_bonus  # assure-toi que cette structure existe dans data.py

            esquive_bonus.setdefault(guild_id, {})
            esquive_bonus[guild_id][uid] = {
                "start": time.time(),
                "duration": esquive_duration
            }

            user_inv.remove("👟")
            sauvegarder()

            embed = discord.Embed(
                title="👟 Esquive améliorée !",
                description=f"{interaction.user.mention} bénéficie maintenant d’un **bonus d’esquive de 20%** pendant 3 heures.",
                color=discord.Color.green()
            )
            return await interaction.response.send_message(embed=embed)

        # Objets classiques de soin
        embed, success = await apply_item_with_cooldown(uid, tid, item, interaction)

        if success:
            user_inv.remove(item)

        sauvegarder()
        await interaction.response.send_message(embed=embed)

    @heal_slash.autocomplete("item")
    async def autocomplete_items(interaction: discord.Interaction, current: str):
        guild_id = str(interaction.guild.id)
        uid = str(interaction.user.id)
        user_inv, _, _ = get_user_data(guild_id, uid)

        heal_items = sorted(set(i for i in user_inv if OBJETS.get(i, {}).get("type") == "soin" or i in ["💉", "🛡", "👟", "🪖"]))

        if not heal_items:
            return [app_commands.Choice(name="Aucun objet de soin", value="")]

        return [
            app_commands.Choice(name=emoji, value=emoji)
            for emoji in heal_items if current in emoji
        ][:25]

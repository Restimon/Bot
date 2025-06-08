import discord
import json
import shutil
import os

from discord.ext import commands
from discord import app_commands
from storage import hp, inventaire, leaderboard
from utils import OBJETS
from config import get_config, save_config, get_guild_config
from data import sauvegarder, virus_status, poison_status, infection_status, regeneration_status, leaderboard
from special_supply import find_or_update_valid_channel, send_special_supply_in_channel, supply_data, sauvegarder
from embeds import build_embed_from_item
from leaderboard_utils import update_leaderboard

BACKUP_DIR = "/persistent/backups"
DATA_FILE = "/persistent/data.json"

import discord
from discord import app_commands
from storage import sauvegarder, hp, inventaire, leaderboard
from config import get_guild_config, save_config
from data import virus_status, poison_status, infection_status, regeneration_status

# Protection anti double register
_admin_commands_registered = False

def register_admin_commands(bot):
    global _admin_commands_registered
    if _admin_commands_registered:
        return  # éviter double déclaration
    _admin_commands_registered = True

    # Commande SET leaderboard_channel
    @bot.tree.command(name="setleaderboardchannel", description="📌 Définit le salon pour le leaderboard économique (GotCoins).")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_leaderboard_channel(interaction: discord.Interaction, channel: discord.TextChannel):
        guild_id = str(interaction.guild.id)
        cfg = get_guild_config(guild_id)
        cfg["special_leaderboard_channel_id"] = channel.id
        cfg["special_leaderboard_message_id"] = None  # réinitialise l'ID du message
        save_config()

        await interaction.response.send_message(
            f"✅ Le salon du leaderboard GotCoins a été défini sur {channel.mention}.", ephemeral=True
        )

    # Commande GET leaderboard_channel
    @bot.tree.command(name="get_leaderboard_channel", description="📊 Voir le salon du leaderboard économique (GotCoins).")
    @app_commands.checks.has_permissions(administrator=True)
    async def get_leaderboard_channel(interaction: discord.Interaction):
        guild_id = str(interaction.guild.id)
        cfg = get_guild_config(guild_id)
        channel_id = cfg.get("special_leaderboard_channel_id")

        if channel_id:
            channel = interaction.guild.get_channel(channel_id)
            if channel:
                await interaction.response.send_message(
                    f"📍 Le salon du leaderboard est : {channel.mention} (`#{channel.name}` - ID `{channel.id}`)",
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    f"⚠️ Le salon avec l'ID `{channel_id}` n'existe plus ou est inaccessible.",
                    ephemeral=True
                )
        else:
            await interaction.response.send_message(
                "❌ Aucun salon de leaderboard n’a encore été configuré.",
                ephemeral=True
            )

    # Commande resetall
    @bot.tree.command(name="resetall", description="♻️ Réinitialise TOUS les joueurs : inventaire, PV, classement, statuts.")
    @app_commands.checks.has_permissions(administrator=True)
    async def reset_all(interaction: discord.Interaction):
        guild_id = str(interaction.guild.id)

        uids = set(inventaire.get(guild_id, {})) | set(hp.get(guild_id, {})) | set(leaderboard.get(guild_id, {}))
        for uid in uids:
            inventaire[guild_id][uid] = []
            hp[guild_id][uid] = 100
            leaderboard[guild_id][uid] = {"degats": 0, "soin": 0, "kills": 0, "morts": 0}

        # Réinitialisation des statuts
        virus_status[guild_id] = {}
        poison_status[guild_id] = {}
        infection_status[guild_id] = {}
        regeneration_status[guild_id] = {}

        sauvegarder()

        await interaction.response.send_message(
            f"♻️ Tous les joueurs ont été réinitialisés ({len(uids)} membres), y compris leurs statuts.",
            ephemeral=True
        )

    # Commande resetleaderboard
    @bot.tree.command(name="resetleaderboard", description="🏆 Réinitialise les stats de classement (GotCoins) pour TOUS les membres.")
    @app_commands.checks.has_permissions(administrator=True)
    async def reset_leaderboard(interaction: discord.Interaction):
        guild_id = str(interaction.guild.id)
        count = 0
        for uid in leaderboard.get(guild_id, {}):
            leaderboard[guild_id][uid] = {"degats": 0, "soin": 0, "kills": 0, "morts": 0}
            count += 1
        sauvegarder()
        await interaction.response.send_message(f"🏆 Classement réinitialisé pour {count} membres.", ephemeral=True)


    @bot.tree.command(name="resethp", description="Remet les PV d’un membre à 100.")
    @app_commands.describe(user="Le membre à soigner")
    @app_commands.checks.has_permissions(administrator=True)
    async def reset_hp(interaction: discord.Interaction, user: discord.Member):
        guild_id = str(interaction.guild.id)
        uid = str(user.id)
        _, user_hp, _ = get_user_data(guild_id, uid)
        hp[guild_id][uid] = 100
        sauvegarder()
        await interaction.response.send_message(f"❤️ PV de {user.mention} remis à 100.", ephemeral=True)

    @bot.tree.command(name="resetinv", description="Vide l’inventaire d’un membre.")
    @app_commands.describe(user="Le membre dont l’inventaire sera vidé")
    @app_commands.checks.has_permissions(administrator=True)
    async def reset_inventory(interaction: discord.Interaction, user: discord.Member):
        guild_id = str(interaction.guild.id)
        uid = str(user.id)
        inventaire[guild_id][uid] = []
        sauvegarder()
        await interaction.response.send_message(f"📦 Inventaire de {user.mention} vidé.", ephemeral=True)

    @bot.tree.command(name="giveitem", description="🎁 Donne un item à un membre.")
    @app_commands.describe(user="Le membre", item="Emoji de l'objet", quantity="Quantité")
    @app_commands.checks.has_permissions(administrator=True)
    async def give_item(interaction: discord.Interaction, user: discord.Member, item: str, quantity: int = 1):
        guild_id = str(interaction.guild.id)
        uid = str(user.id)
        if item not in OBJETS:
            return await interaction.response.send_message(f"❌ L’objet {item} n’existe pas.", ephemeral=True)
        user_inv, _, _ = get_user_data(guild_id, uid)
        user_inv.extend([item] * quantity)
        sauvegarder()
        await interaction.response.send_message(f"✅ {quantity} × {item} donné à {user.mention}.", ephemeral=True)

    @give_item.autocomplete("item")
    async def autocomplete_item(interaction: discord.Interaction, current: str):
        from utils import OBJETS
        print("DEBUG OBJETS :", list(OBJETS.keys()))  # Ajoute ça pour vérifier
        results = []
        for emoji, data in OBJETS.items():
            name = f"{emoji} – {data['type']}"
            if current.lower() in name.lower():
                results.append(app_commands.Choice(name=name, value=emoji))
            if len(results) >= 25:
                break
        return results
        
    @give_item.error
    async def give_item_error(interaction: discord.Interaction, error):
        if isinstance(error, app_commands.errors.MissingPermissions):
            await interaction.response.send_message("⛔ Tu dois être admin pour cette commande.", ephemeral=True)
        else:
            await interaction.response.send_message("⚠️ Une erreur est survenue.", ephemeral=True)
            
    @bot.tree.command(name="supply", description="Forcer l'envoi d'un ravitaillement spécial (Admin).")
    @commands.has_permissions(administrator=True)
    async def supply(interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        guild = interaction.guild
        gid = str(guild.id)
        config = supply_data.setdefault(gid, {})

        channel = find_or_update_valid_channel(bot, guild, config)
        if channel:
            await send_special_supply_in_channel(bot, guild, channel)
            await interaction.followup.send(f"📦 Ravitaillement spécial forcé envoyé dans {channel.mention}.", ephemeral=True)
        else:
            await interaction.followup.send("❌ Aucun salon valide trouvé pour envoyer le ravitaillement.", ephemeral=True)

    @bot.tree.command(name="forcer_lb_temp", description="🔁 Mise à jour manuelle du leaderboard spécial (test).")
    @app_commands.checks.has_permissions(administrator=True)
    async def force_leaderboard_update(interaction: discord.Interaction):
        guild = interaction.guild
        guild_id = str(guild.id)
        guild_config = get_guild_config(guild_id)

        channel_id = guild_config.get("special_leaderboard_channel_id")
        message_id = guild_config.get("special_leaderboard_message_id")

        if not channel_id:
            return await interaction.response.send_message("❌ Aucun salon de leaderboard configuré.", ephemeral=True)

        channel = guild.get_channel(channel_id)
        if not channel:
            return await interaction.response.send_message("❌ Salon introuvable ou inaccessible.", ephemeral=True)

        medals = ["🥇", "🥈", "🥉"]
        server_lb = leaderboard.get(guild_id, {})
        sorted_lb = sorted(server_lb.items(), key=lambda x: x[1]["degats"] + x[1]["soin"] + x[1].get("kills", 0) * 50 - x[1].get("morts", 0) * 25, reverse=True)

        lines = []
        rank = 0
        for uid, stats in sorted_lb:
            member = guild.get_member(int(uid))
            if not member:
                continue
            if rank >= 10:
                break

            degats = stats.get("degats", 0)
            soin = stats.get("soin", 0)
            kills = stats.get("kills", 0)
            morts = stats.get("morts", 0)
            total = degats + soin + kills * 50 - morts * 25
            current_hp = hp.get(guild_id, {}).get(uid, 100)

            prefix = medals[rank] if rank < len(medals) else f"{rank + 1}."
            lines.append(
                f"{prefix} **{member.display_name}** → "
                f"🗡️ {degats} | 💚 {soin} | 🎽 {kills} | 💀 {morts} = **{total}** points | ❤️ {current_hp} PV"
            )
            rank += 1

        content = (
            "> 🏆 __**CLASSEMENT GotValis - ÉDITION SPÉCIALE**__ 🏆\n\n" +
            "\n".join([f"> {line}" for line in lines]) +
            "\n\n 📌 Classement mis à jour automatiquement par GotValis."
        ) if lines else "*Aucune donnée disponible.*"

        try:
            if message_id:
                msg = await channel.fetch_message(message_id)
                await msg.edit(content=content)
            else:
                raise discord.NotFound(response=None, message="No message ID")
        except (discord.NotFound, discord.HTTPException):
            msg = await channel.send(content=content)
            guild_config["special_leaderboard_message_id"] = msg.id
            save_config()

        await interaction.response.send_message("✅ Leaderboard mis à jour manuellement.", ephemeral=True)

    from data import sauvegarder  # si ce n’est pas déjà fait

    @bot.tree.command(name="purge_status", description="(Admin) Supprime tous les effets de virus/poison d’un membre.")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(user="Le membre à purifier")
    async def purge_status_command(interaction: discord.Interaction, user: discord.Member):
        guild_id = str(interaction.guild.id)
        user_id = str(user.id)

        virus_status.get(guild_id, {}).pop(user_id, None)
        poison_status.get(guild_id, {}).pop(user_id, None)
        infection_status.get(guild_id, {}).pop(user_id, None)

        sauvegarder()  # 🔧 indispensable pour que la purge soit persistante et reconnue par les fonctions

        await interaction.response.send_message(
            f"🧼 Tous les effets négatifs ont été supprimés de {user.mention}. GotValis confirme la purification.",
            ephemeral=True
        )

    @bot.tree.command(name="restore", description="🔁 Restaurer une sauvegarde pour ce serveur (admin seulement)")
    @app_commands.describe(filename="Nom exact de la sauvegarde à restaurer")
    async def restore(interaction: discord.Interaction, filename: str):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Seuls les administrateurs peuvent utiliser cette commande.", ephemeral=True)

        guild_id = str(interaction.guild.id)
        backup_path = os.path.join(BACKUP_DIR, filename)

        if not os.path.exists(backup_path):
            return await interaction.response.send_message("❌ Sauvegarde introuvable.", ephemeral=True)

        try:
            with open(backup_path, "r", encoding="utf-8") as f:
                backup_data = json.load(f)

            # 🔄 Remplace uniquement les données de ce serveur
            inventaire[guild_id] = backup_data.get("inventaire", {})
            hp[guild_id] = backup_data.get("hp", {})
            leaderboard[guild_id] = backup_data.get("leaderboard", {})

            sauvegarder()
            await interaction.response.send_message(f"✅ Données du serveur restaurées depuis `{filename}`.")
        except Exception as e:
            await interaction.response.send_message(f"❌ Erreur lors de la restauration : {e}", ephemeral=True)

    @bot.tree.command(name="backups", description="📁 Liste les sauvegardes disponibles pour ce serveur")
    async def list_backups(interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Seuls les administrateurs peuvent utiliser cette commande.", ephemeral=True)

        guild_id = str(interaction.guild.id)
        prefix = f"data_backup_{guild_id}_"

        files = sorted(f for f in os.listdir(BACKUP_DIR) if f.startswith(prefix))
        if not files:
            return await interaction.response.send_message("📁 Aucune sauvegarde disponible pour ce serveur.", ephemeral=True)

        message = "**Sauvegardes de ce serveur :**\n" + "\n".join(f"`{f}`" for f in files)
        await interaction.response.send_message(message, ephemeral=True)

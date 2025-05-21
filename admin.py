import discord
import json
from discord import app_commands
from storage import inventaire, hp, leaderboard, get_user_data
from utils import OBJETS
from config import get_config, save_config, get_guild_config
from data import sauvegarder, virus_status, poison_status

def register_admin_commands(bot):
    print("📦 Enregistrement des commandes admin...")
    @bot.tree.command(name="setleaderboardchannel", description="Définit et envoie le classement dans un salon.")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_leaderboard(interaction: discord.Interaction, channel: discord.TextChannel):
        print("🚨 set_leaderboard déclenchée")
        guild_id = str(interaction.guild.id)
        await interaction.response.defer(ephemeral=True)

        config = get_config() 
        guild_config = config.setdefault(guild_id, {})
        old_channel_id = guild_config.get("special_leaderboard_channel_id")
        old_message_id = guild_config.get("special_leaderboard_message_id")

        if old_channel_id and old_message_id:
            old_channel = interaction.client.get_channel(old_channel_id)
            if old_channel:
                try:
                    old_msg = await old_channel.fetch_message(old_message_id)
                    await old_msg.delete()
                except discord.NotFound:
                    pass

        medals = ["🥇", "🥈", "🥉"]
        server_lb = leaderboard.get(guild_id, {})
        sorted_lb = sorted(server_lb.items(), key=lambda x: x[1]["degats"] + x[1]["soin"], reverse=True)

        lines = []
        rank = 0
        for uid, stats in sorted_lb:
            user = interaction.client.get_user(int(uid))
            if not user:
                continue
            if rank >= 10:
                break

            degats = stats.get("degats", 0)
            soin = stats.get("soin", 0)
            kills = stats.get("kills", 0)
            morts = stats.get("morts", 0)
            total = degats + soin + kills * 50 - morts * 25

            prefix = medals[rank] if rank < len(medals) else f"{rank + 1}."
            lines.append(
                f"{prefix} **{user.display_name}** → "
                f"🗡️ {degats} | 💚 {soin} | ☠️ {kills} | 💀 {morts} = **{total}** points"
            )

        content = (
            "🏆 __**CLASSEMENT SOMNICORP - ÉDITION SPÉCIALE**__ 🏆\n\n" +
            "\n".join(lines) +
            "\n\n📌 Classement mis à jour automatiquement par SomniCorp."
        )

        msg = await channel.send(content=content)
        guild_config["special_leaderboard_channel_id"] = channel.id
        guild_config["special_leaderboard_message_id"] = msg.id

        print("📌 Avant save_config()")  # ← AJOUTE ÇA
        save_config()
        print("💾 Après save_config()")  # ← ET ÇA

        await interaction.followup.send(f"✅ Classement envoyé dans {channel.mention}.", ephemeral=True)

    @bot.tree.command(name="get_leaderboard_channel", description="📊 Voir le salon du leaderboard spécial")
    @app_commands.checks.has_permissions(administrator=True)
    async def get_leaderboard_channel(interaction: discord.Interaction):
        guild_id = str(interaction.guild.id)
        cfg = get_guild_config(guild_id)
        channel_id = cfg.get("special_leaderboard_channel_id")

        if channel_id:
            channel = interaction.guild.get_channel(channel_id)
            if channel:
                await interaction.response.send_message(
                    f"📍 Le salon du leaderboard spécial est : {channel.mention} (`#{channel.name}` - ID `{channel.id}`)",
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    f"⚠️ Le salon avec l'ID `{channel_id}` n'existe plus ou est inaccessible.",
                    ephemeral=True
                )
        else:
            await interaction.response.send_message(
                "❌ Aucun salon de leaderboard n’a encore été configuré pour ce serveur.",
                ephemeral=True
            )

    @bot.tree.command(name="stopleaderboard", description="🛑 Supprime le message du classement spécial et arrête sa mise à jour automatique.")
    @app_commands.checks.has_permissions(administrator=True)
    async def stop_leaderboard(interaction: discord.Interaction):
        guild_id = str(interaction.guild.id)
        config = get_config()
        guild_config = config.get(guild_id, {})

        channel_id = guild_config.get("special_leaderboard_channel_id")
        message_id = guild_config.get("special_leaderboard_message_id")

        if not channel_id or not message_id:
            return await interaction.response.send_message("⚠️ Aucun leaderboard spécial actif.", ephemeral=True)

        channel = interaction.client.get_channel(channel_id)
        if channel:
            try:
                msg = await channel.fetch_message(message_id)
                await msg.delete()
            except discord.NotFound:
                pass

    # On efface les IDs du leaderboard spécial
        guild_config["special_leaderboard_channel_id"] = None
        guild_config["special_leaderboard_message_id"] = None
        save_config()

        await interaction.response.send_message("🛑 Leaderboard spécial désactivé et supprimé.", ephemeral=True)

    @bot.tree.command(name="resetall", description="Réinitialise TOUS les joueurs : inventaire, PV, classement.")
    @app_commands.checks.has_permissions(administrator=True)
    async def reset_all(interaction: discord.Interaction):
        guild_id = str(interaction.guild.id)
        uids = set(inventaire.get(guild_id, {})) | set(hp.get(guild_id, {})) | set(leaderboard.get(guild_id, {}))
        for uid in uids:
            inventaire[guild_id][uid] = []
            hp[guild_id][uid] = 100
            leaderboard[guild_id][uid] = {"degats": 0, "soin": 0}
        sauvegarder()
        await interaction.response.send_message(
            f"♻️ Tous les joueurs ont été réinitialisés ({len(uids)} membres).", ephemeral=True
        )

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

    @bot.tree.command(name="resetleaderboard", description="Réinitialise les stats de classement de TOUS les membres.")
    @app_commands.checks.has_permissions(administrator=True)
    async def reset_leaderboard(interaction: discord.Interaction):
        guild_id = str(interaction.guild.id)
        count = 0
        for uid in leaderboard.get(guild_id, {}):
            leaderboard[guild_id][uid] = {"degats": 0, "soin": 0}
            count += 1
        sauvegarder()
        await interaction.response.send_message(f"🏆 Classement réinitialisé pour {count} membres.", ephemeral=True)

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
    async def autocomplete_give_item(interaction: discord.Interaction, current: str):
        return [app_commands.Choice(name=emoji, value=emoji) for emoji in OBJETS if current in emoji][:25]

    @give_item.error
    async def give_item_error(interaction: discord.Interaction, error):
        if isinstance(error, app_commands.errors.MissingPermissions):
            await interaction.response.send_message("⛔ Tu dois être admin pour cette commande.", ephemeral=True)
        else:
            await interaction.response.send_message("⚠️ Une erreur est survenue.", ephemeral=True)
            
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
        from storage import hp  # 🩺 Pour récupérer les PV
        sorted_lb = sorted(server_lb.items(), key=lambda x: x[1]["degats"] + x[1]["soin"], reverse=True)

        lines = []
        rank = 0
        for uid, stats in sorted_lb:
            member = guild.get_member(int(uid))
            if not member:
                continue
            if rank >= 10:
                break
            total = stats["degats"] + stats["soin"]
            current_hp = hp.get(guild_id, {}).get(uid, 100)  # 🔥 Ajout des PV
            prefix = medals[rank] if rank < len(medals) else f"{rank + 1}."
            lines.append(
                f"{prefix} **{member.display_name}** → 🗡️ {stats['degats']} | 💚 {stats['soin']} = **{total}** points | ❤️ {current_hp} PV"
            )
            rank += 1

        content = (
            "🏆 __**CLASSEMENT SOMNICORP - ÉDITION SPÉCIALE**__ 🏆\n\n" +
            "\n".join(lines) +
            "\n\n📌 Mise à jour manuelle effectuée par un administrateur."
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

    @bot.tree.command(name="purge_status", description="(Admin) Supprime tous les effets de virus/poison d’un membre.")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(user="Le membre à purifier")
    async def purge_status_command(interaction: discord.Interaction, user: discord.Member):
        guild_id = str(interaction.guild.id)
        user_id = str(user.id)

        virus_status.get(guild_id, {}).pop(user_id, None)
        poison_status.get(guild_id, {}).pop(user_id, None)

        await interaction.response.send_message(
            f"🧼 Tous les effets négatifs ont été supprimés de {user.mention}. SomniCorp confirme la purification.",
            ephemeral=True
    )
    

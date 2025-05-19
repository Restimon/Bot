import discord
from discord import app_commands
from utils import inventaire, hp, leaderboard, OBJETS
from config import config, save_config
from data import sauvegarder

def register_admin_commands(bot):
    @bot.tree.command(name="setleaderboardchannel", description="Définit et envoie le classement dans un salon.")
    @discord.app_commands.checks.has_permissions(administrator=True)
    async def set_leaderboard(interaction: discord.Interaction, channel: discord.TextChannel):
        from config import save_config
        from utils import leaderboard

        - await interaction.response.send_message(f"✅ Classement envoyé dans {channel.mention}.", ephemeral=True)

        # Supprimer l'ancien leaderboard si présent
        old_channel_id = config.get("leaderboard_channel_id")
        old_message_id = config.get("leaderboard_message_id")
        if old_channel_id and old_message_id:
            old_channel = interaction.client.get_channel(old_channel_id)
            if old_channel:
                try:
                    old_msg = await old_channel.fetch_message(old_message_id)
                    await old_msg.delete()
                except discord.NotFound:
                    pass

        # Génération du message spécial (non embed)
        medals = ["🥇", "🥈", "🥉"]
        sorted_lb = sorted(
            leaderboard.items(),
            key=lambda x: x[1]["degats"] + x[1]["soin"],
            reverse=True
        )

        lines = []
        rank = 0
        for uid, stats in sorted_lb:
            user = interaction.client.get_user(int(uid))
            if not user:
                continue  # Ignore utilisateurs inconnus

            if rank >= 10:
                break

            total = stats["degats"] + stats["soin"]
            prefix = medals[rank] if rank < len(medals) else f"{rank + 1}."
            lines.append(f"{prefix} **{user.name}** → 🗡️ {stats['degats']} | 💚 {stats['soin']} = **{total}** points")
            rank += 1

        content = (
            "🏆 __**CLASSEMENT SOMNICORP - ÉDITION SPÉCIALE**__ 🏆\n\n" +
            "\n".join(lines) +
            "\n\n📌 Mise à jour automatique toutes les 5 minutes."
        )

# ...
         msg = await channel.send(content=content)
            config["leaderboard_channel_id"] = channel.id
            config["leaderboard_message_id"] = msg.id
            save_config()

# ✅ Ce message doit venir ici
            await interaction.followup.send(f"✅ Classement envoyé dans {channel.mention}.", ephemeral=True)


    @bot.tree.command(name="stopleaderboard", description="Arrête le classement auto et supprime le message.")
    @app_commands.checks.has_permissions(administrator=True)
    async def stop_leaderboard(interaction: discord.Interaction):
        channel_id = config.get("leaderboard_channel_id")
        message_id = config.get("leaderboard_message_id")

        if not channel_id or not message_id:
            return await interaction.response.send_message("⚠️ Aucun leaderboard actif.", ephemeral=True)

        channel = interaction.client.get_channel(channel_id)
        if channel:
            try:
                msg = await channel.fetch_message(message_id)
                await msg.delete()
            except discord.NotFound:
                pass

        config["leaderboard_channel_id"] = None
        config["leaderboard_message_id"] = None
        save_config()
        await interaction.response.send_message("🛑 Leaderboard désactivé et supprimé.", ephemeral=True)

    @bot.tree.command(name="resetall", description="Réinitialise TOUS les joueurs : inventaire, PV, classement.")
    @app_commands.checks.has_permissions(administrator=True)
    async def reset_all(interaction: discord.Interaction):
        uids = set(inventaire) | set(hp) | set(leaderboard)
        for uid in uids:
            inventaire[uid] = []
            hp[uid] = 100
            leaderboard[uid] = {"degats": 0, "soin": 0}

        sauvegarder()
        await interaction.response.send_message(
            f"♻️ Tous les joueurs ont été réinitialisés ({len(uids)} membres).", ephemeral=True
        )

    @bot.tree.command(name="resethp", description="Remet les PV d’un membre à 100.")
    @app_commands.describe(user="Le membre à soigner")
    @app_commands.checks.has_permissions(administrator=True)
    async def reset_hp(interaction: discord.Interaction, user: discord.Member):
        hp[str(user.id)] = 100
        sauvegarder()
        await interaction.response.send_message(f"❤️ PV de {user.mention} remis à 100.", ephemeral=True)

    @bot.tree.command(name="resetinv", description="Vide l’inventaire d’un membre.")
    @app_commands.describe(user="Le membre dont l’inventaire sera vidé")
    @app_commands.checks.has_permissions(administrator=True)
    async def reset_inventory(interaction: discord.Interaction, user: discord.Member):
        inventaire[str(user.id)] = []
        sauvegarder()
        await interaction.response.send_message(f"📦 Inventaire de {user.mention} vidé.", ephemeral=True)

    @bot.tree.command(name="resetleaderboard", description="Réinitialise les stats de classement de TOUS les membres.")
    @app_commands.checks.has_permissions(administrator=True)
    async def reset_leaderboard(interaction: discord.Interaction):
        count = 0
        for uid in leaderboard:
            leaderboard[uid] = {"degats": 0, "soin": 0}
            count += 1

        sauvegarder()
        await interaction.response.send_message(
            f"🏆 Classement réinitialisé pour {count} membres.", ephemeral=True
        )

    @bot.tree.command(name="giveitem", description="🎁 Donne un item à un membre.")
    @app_commands.describe(user="Le membre", item="Emoji de l'objet", quantity="Quantité")
    @app_commands.checks.has_permissions(administrator=True)
    async def give_item(interaction: discord.Interaction, user: discord.Member, item: str, quantity: int = 1):
        uid = str(user.id)
        if item not in OBJETS:
            return await interaction.response.send_message(
                f"❌ L’objet {item} n’existe pas.", ephemeral=True
            )

        inventaire.setdefault(uid, []).extend([item] * quantity)
        sauvegarder()
        await interaction.response.send_message(
            f"✅ {quantity} × {item} donné à {user.mention}.", ephemeral=True
        )

    @give_item.autocomplete("item")
    async def autocomplete_give_item(interaction: discord.Interaction, current: str):
        return [
            app_commands.Choice(name=emoji, value=emoji)
            for emoji in OBJETS if current in emoji
        ][:25]

    @give_item.error
    async def give_item_error(interaction: discord.Interaction, error):
        if isinstance(error, app_commands.errors.MissingPermissions):
            await interaction.response.send_message(
                "⛔ Tu dois être admin pour cette commande.", ephemeral=True)
        else:
            await interaction.response.send_message("⚠️ Une erreur est survenue.", ephemeral=True)

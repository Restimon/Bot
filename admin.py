import discord
from discord import app_commands
from utils import inventaire, hp, leaderboard, OBJETS
from config import config, save_config
from data import sauvegarder

def register_admin_commands(bot):
    @bot.tree.command(name="setleaderboardchannel", description="Définit et envoie le classement dans un salon.")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_leaderboard(interaction: discord.Interaction, channel: discord.TextChannel):
        from leaderboard import build_leaderboard_embed
        config["leaderboard_channel_id"] = channel.id
        save_config()

        embed = await build_leaderboard_embed(interaction.client)
        await channel.send(embed=embed)

        await interaction.response.send_message(
            f"✅ Salon de classement défini sur : {channel.mention}. Le leaderboard a été envoyé.",
            ephemeral=True
        )

    @bot.tree.command(name="resetall", description="Réinitialise inventaire, PV et classement d’un membre.")
    @app_commands.describe(user="Le membre à réinitialiser")
    @app_commands.checks.has_permissions(administrator=True)
    async def reset_all(interaction: discord.Interaction, user: discord.Member):
        uid = str(user.id)
        inventaire[uid] = []
        hp[uid] = 100
        leaderboard[uid] = {"degats": 0, "soin": 0}
        sauvegarder()
        await interaction.response.send_message(
            f"♻️ Données de {user.mention} réinitialisées.", ephemeral=True
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

    @bot.tree.command(name="resetleaderboard", description="Réinitialise les stats de classement d’un membre.")
    @app_commands.describe(user="Le membre à réinitialiser")
    @app_commands.checks.has_permissions(administrator=True)
    async def reset_leaderboard(interaction: discord.Interaction, user: discord.Member):
        leaderboard[str(user.id)] = {"degats": 0, "soin": 0}
        sauvegarder()
        await interaction.response.send_message(f"🏆 Stats de {user.mention} remises à zéro.", ephemeral=True)

    @bot.tree.command(name="giveitem", description="🎁 Donne un item à un membre (admin seulement).")
    @app_commands.describe(user="Le membre à qui donner l'item", item="Emoji de l'objet", quantity="Quantité")
    @app_commands.checks.has_permissions(administrator=True)
    async def give_item(interaction: discord.Interaction, user: discord.Member, item: str, quantity: int = 1):
        uid = str(user.id)

        if item not in OBJETS:
            return await interaction.response.send_message(
                f"❌ L'objet {item} n'existe pas dans OBJETS.", ephemeral=True
            )

        inventaire.setdefault(uid, []).extend([item] * quantity)
        sauvegarder()
        await interaction.response.send_message(
            f"✅ {quantity} × {item} ont été ajoutés à l’inventaire de {user.mention}.", ephemeral=True
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
                "⛔ Tu dois être administrateur pour utiliser cette commande.", ephemeral=True)
        else:
            await interaction.response.send_message("⚠️ Une erreur est survenue.", ephemeral=True)
            
    @bot.tree.command(name="stopleaderboard", description="Arrête le classement auto et supprime le message.")
    @app_commands.checks.has_permissions(administrator=True)
    async def stop_leaderboard(interaction: discord.Interaction):
        channel_id = config.get("leaderboard_channel_id")
        message_id = config.get("leaderboard_message_id")

        if not channel_id or not message_id:
            return await interaction.response.send_message(
                "⚠️ Aucun message de leaderboard actif trouvé.", ephemeral=True
            )

        channel = interaction.client.get_channel(channel_id)
        if channel:
            try:
                msg = await channel.fetch_message(message_id)
                await msg.delete()
            except discord.NotFound:
                pass  # Message déjà supprimé

        config["leaderboard_channel_id"] = None
        config["leaderboard_message_id"] = None
        save_config()

        await interaction.response.send_message("🛑 Le leaderboard a été désactivé et supprimé.", ephemeral=True)


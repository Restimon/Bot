# admin.py
import os
import json
import discord
from discord.ext import commands
from discord import app_commands

# --- Données & utilitaires de TON projet
from storage import hp, inventaire, leaderboard, get_user_data
from utils import OBJETS
from config import get_guild_config, save_config
from data import sauvegarder, virus_status, poison_status, infection_status, regeneration_status
from special_supply import (
    find_or_update_valid_channel,
    send_special_supply_in_channel,
    supply_data,
    set_special_supply_enabled,
    is_special_supply_enabled,
)

# (facultatif) utilisé dans d'autres contextes, on le garde
from embeds import build_embed_from_item

BACKUP_DIR = "/persistent/backups"
DATA_FILE = "/persistent/data.json"

os.makedirs(BACKUP_DIR, exist_ok=True)

# Protection anti double-register
_admin_commands_registered = False


def register_admin_commands(bot: commands.Bot):
    global _admin_commands_registered
    if _admin_commands_registered:
        return
    _admin_commands_registered = True

    # ===========================
    #   Leaderboard (salon)
    # ===========================
    @bot.tree.command(
        name="setleaderboardchannel",
        description="📌 Définit le salon pour le leaderboard GotValis.",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def set_leaderboard_channel(
        interaction: discord.Interaction, channel: discord.TextChannel
    ):
        guild_id = str(interaction.guild.id)
        cfg = get_guild_config(guild_id)
        cfg["special_leaderboard_channel_id"] = channel.id
        cfg["special_leaderboard_message_id"] = None  # reset message id pour forcer une (ré)création
        save_config()
        await interaction.response.send_message(
            f"✅ Salon du leaderboard défini sur {channel.mention}.", ephemeral=True
        )

    @bot.tree.command(
        name="get_leaderboard_channel",
        description="📊 Affiche le salon configuré pour le leaderboard.",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def get_leaderboard_channel(interaction: discord.Interaction):
        guild_id = str(interaction.guild.id)
        cfg = get_guild_config(guild_id)
        channel_id = cfg.get("special_leaderboard_channel_id")

        if not channel_id:
            return await interaction.response.send_message(
                "❌ Aucun salon de leaderboard n’a encore été configuré.", ephemeral=True
            )

        channel = interaction.guild.get_channel(channel_id)
        if channel:
            await interaction.response.send_message(
                f"📍 Salon du leaderboard : {channel.mention} (#{channel.name} – ID `{channel.id}`)",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                f"⚠️ Le salon avec l’ID `{channel_id}` n’existe plus ou est inaccessible.",
                ephemeral=True,
            )

    # ===========================
    #   Resets massifs
    # ===========================
    @bot.tree.command(
        name="resetall",
        description="♻️ Réinitialise inventaires, PV, classement et statuts pour TOUS les joueurs.",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def reset_all(interaction: discord.Interaction):
        guild_id = str(interaction.guild.id)

        uids = set(inventaire.get(guild_id, {})) | set(hp.get(guild_id, {})) | set(
            leaderboard.get(guild_id, {})
        )

        inventaire.setdefault(guild_id, {})
        hp.setdefault(guild_id, {})
        leaderboard.setdefault(guild_id, {})

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
            f"♻️ Réinitialisation effectuée pour **{len(uids)}** membres (inventaires, PV, leaderboard, statuts).",
            ephemeral=True,
        )

    @bot.tree.command(
        name="resetleaderboard",
        description="🏆 Réinitialise le classement (dégâts, soins, kills, morts) pour TOUS les membres.",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def reset_leaderboard(interaction: discord.Interaction):
        guild_id = str(interaction.guild.id)
        leaderboard.setdefault(guild_id, {})
        count = 0
        for uid in list(leaderboard[guild_id].keys()):
            leaderboard[guild_id][uid] = {"degats": 0, "soin": 0, "kills": 0, "morts": 0}
            count += 1
        sauvegarder()
        await interaction.response.send_message(
            f"🏆 Classement réinitialisé pour **{count}** membres.", ephemeral=True
        )

    # ===========================
    #   Resets ciblés
    # ===========================
    @bot.tree.command(name="resethp", description="❤️ Remet les PV d’un membre à 100.")
    @app_commands.describe(user="Le membre à soigner")
    @app_commands.checks.has_permissions(administrator=True)
    async def reset_hp(interaction: discord.Interaction, user: discord.Member):
        guild_id = str(interaction.guild.id)
        uid = str(user.id)
        hp.setdefault(guild_id, {})
        hp[guild_id][uid] = 100
        sauvegarder()
        await interaction.response.send_message(
            f"❤️ PV de {user.mention} remis à **100**.", ephemeral=True
        )

    @bot.tree.command(name="resetinv", description="📦 Vide l’inventaire d’un membre.")
    @app_commands.describe(user="Le membre dont l’inventaire sera vidé")
    @app_commands.checks.has_permissions(administrator=True)
    async def reset_inventory(interaction: discord.Interaction, user: discord.Member):
        guild_id = str(interaction.guild.id)
        uid = str(user.id)
        inventaire.setdefault(guild_id, {})
        inventaire[guild_id][uid] = []
        sauvegarder()
        await interaction.response.send_message(
            f"📦 Inventaire de {user.mention} vidé.", ephemeral=True
        )

    # ===========================
    #   GIVE (avec autocomplete)
    # ===========================
    @bot.tree.command(name="give", description="🎁 (ADMIN) Donner un objet à un membre")
    @app_commands.describe(
        user="Membre qui reçoit",
        item="Emoji/objet à donner",
        quantity="Quantité (par défaut 1)",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def give_slash(
        interaction: discord.Interaction,
        user: discord.Member,
        item: str,
        quantity: app_commands.Range[int, 1, 999] = 1,
    ):
        await interaction.response.defer(thinking=True)
        guild_id = str(interaction.guild.id)
        uid = str(user.id)

        inventaire.setdefault(guild_id, {})
        inv, _, _ = get_user_data(guild_id, uid)
        for _ in range(quantity):
            inv.append(item)
        sauvegarder()

        if item in OBJETS:
            await interaction.followup.send(
                f"✅ Donné **{quantity}× {item}** à {user.mention}.", ephemeral=False
            )
        else:
            await interaction.followup.send(
                f"⚠️ **{item}** n’est pas référencé dans OBJETS, mais ajouté quand même "
                f"({quantity}×) à l’inventaire de {user.mention}.",
                ephemeral=False,
            )

    @give_slash.autocomplete("item")
    async def give_item_autocomplete(inter: discord.Interaction, current: str):
        """Propose les clés (emojis) de OBJETS. Si `current` est vide -> renvoie les 25 premiers."""
        cur = (current or "").strip()

        def label_for(e: str) -> str:
            o = OBJETS.get(e, {})
            t = o.get("type", "?")
            if t == "attaque":
                return f"{e} attaque ({o.get('degats', '?')} dmg)"
            if t == "attaque_chaine":
                return f"{e} attaque en chaîne"
            if t == "virus":
                return f"{e} virus"
            if t == "poison":
                return f"{e} poison"
            if t == "infection":
                return f"{e} infection"
            if t == "soin":
                return f"{e} soin (+{o.get('soin', '?')} PV)"
            if t == "regen":
                return f"{e} régénération"
            if t == "vol":
                return f"{e} vol"
            if t == "bouclier":
                return f"{e} bouclier"
            if t == "vaccin":
                return f"{e} vaccin"
            if t == "immunite":
                return f"{e} immunité"
            return f"{e} ({t})"

        emojis = sorted(OBJETS.keys(), key=str)
        if cur:
            emojis = [e for e in emojis if cur in e]

        choices = [app_commands.Choice(name=label_for(e), value=e) for e in emojis[:25]]
        if not choices and cur:
            choices = [app_commands.Choice(name=f"Utiliser {cur} (non référencé)", value=cur)]
        return choices

    @give_slash.error
    async def give_item_error(interaction: discord.Interaction, error):
        if isinstance(error, app_commands.errors.MissingPermissions):
            await interaction.response.send_message(
                "⛔ Tu dois être **admin** pour cette commande.", ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "⚠️ Une erreur est survenue.", ephemeral=True
            )

    # ===========================
    #   Supply (spécial)
    # ===========================
    @bot.tree.command(
        name="supply",
        description="(ADMIN) Forcer l'envoi d'un ravitaillement spécial.",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def supply_cmd(interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        guild = interaction.guild
        gid = str(guild.id)
        config = supply_data.setdefault(gid, {})

        channel = find_or_update_valid_channel(bot, guild, config)
        if channel:
            await send_special_supply_in_channel(bot, guild, channel)
            await interaction.followup.send(
                f"📦 Ravitaillement spécial forcé envoyé dans {channel.mention}.",
                ephemeral=True,
            )
        else:
            await interaction.followup.send(
                "❌ Aucun salon valide trouvé pour envoyer le ravitaillement.",
                ephemeral=True,
            )

    @bot.tree.command(
        name="forcer_lb_temp",
        description="🔁 Mise à jour manuelle du leaderboard spécial (test).",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def force_leaderboard_update(interaction: discord.Interaction):
        guild = interaction.guild
        guild_id = str(guild.id)
        guild_config = get_guild_config(guild_id)

        channel_id = guild_config.get("special_leaderboard_channel_id")
        message_id = guild_config.get("special_leaderboard_message_id")

        if not channel_id:
            return await interaction.response.send_message(
                "❌ Aucun salon de leaderboard configuré.", ephemeral=True
            )

        channel = guild.get_channel(channel_id)
        if not channel:
            return await interaction.response.send_message(
                "❌ Salon introuvable ou inaccessible.", ephemeral=True
            )

        medals = ["🥇", "🥈", "🥉"]
        server_lb = leaderboard.get(guild_id, {})
        sorted_lb = sorted(
            server_lb.items(),
            key=lambda x: x[1].get("degats", 0)
            + x[1].get("soin", 0)
            + x[1].get("kills", 0) * 50
            - x[1].get("morts", 0) * 25,
            reverse=True,
        )

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
                f"💰 **{total} GotCoins** | ❤️ {current_hp} PV"
            )
            rank += 1

        embed = discord.Embed(
            title="🏆 CLASSEMENT GOTVALIS — ÉDITION SPÉCIALE 🏆",
            description="\n".join(lines) if lines else "*Aucune donnée disponible.*",
            color=discord.Color.gold(),
        )
        embed.set_footer(text="💰 Les GotCoins représentent votre richesse accumulée.")

        try:
            if message_id:
                msg = await channel.fetch_message(message_id)
                await msg.edit(content=None, embed=embed)
            else:
                raise discord.NotFound(response=None, message="No message ID")
        except (discord.NotFound, discord.HTTPException):
            msg = await channel.send(embed=embed)
            guild_config["special_leaderboard_message_id"] = msg.id
            save_config()

        await interaction.response.send_message(
            "✅ Leaderboard mis à jour manuellement.", ephemeral=True
        )

    # ===========================
    #   Purge statuts négatifs
    # ===========================
    @bot.tree.command(
        name="purge_status",
        description="(ADMIN) Supprime virus/poison/infection d’un membre.",
    )
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(user="Le membre à purifier")
    async def purge_status_command(interaction: discord.Interaction, user: discord.Member):
        guild_id = str(interaction.guild.id)
        user_id = str(user.id)

        virus_status.get(guild_id, {}).pop(user_id, None)
        poison_status.get(guild_id, {}).pop(user_id, None)
        infection_status.get(guild_id, {}).pop(user_id, None)

        sauvegarder()
        await interaction.response.send_message(
            f"🧼 Tous les effets négatifs ont été supprimés de {user.mention}.",
            ephemeral=True,
        )

    # ===========================
    #   Backups
    # ===========================
    @bot.tree.command(
        name="restore",
        description="🔁 Restaurer une sauvegarde (admin seulement)",
    )
    @app_commands.describe(filename="Nom exact du fichier de sauvegarde")
    @app_commands.checks.has_permissions(administrator=True)
    async def restore(interaction: discord.Interaction, filename: str):
        backup_path = os.path.join(BACKUP_DIR, filename)

        if not os.path.exists(backup_path):
            return await interaction.response.send_message(
                "❌ Sauvegarde introuvable.", ephemeral=True
            )

        try:
            with open(backup_path, "r", encoding="utf-8") as f:
                backup_data = json.load(f)

            guild_id = str(interaction.guild.id)
            inventaire[guild_id] = backup_data.get("inventaire", {}).get(guild_id, {})
            hp[guild_id] = backup_data.get("hp", {}).get(guild_id, {})
            leaderboard[guild_id] = backup_data.get("leaderboard", {}).get(guild_id, {})

            sauvegarder()
            await interaction.response.send_message(
                f"✅ Données de ce serveur restaurées depuis `{filename}`.", ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(
                f"❌ Erreur lors de la restauration : `{e}`", ephemeral=True
            )

    @bot.tree.command(
        name="backups",
        description="📁 Liste les sauvegardes disponibles pour ce serveur",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def list_backups(interaction: discord.Interaction):
        guild_id = str(interaction.guild.id)
        prefix = f"data_backup_{guild_id}_"

        if not os.path.isdir(BACKUP_DIR):
            return await interaction.response.send_message(
                "📁 Aucune sauvegarde disponible.", ephemeral=True
            )

        files = sorted(f for f in os.listdir(BACKUP_DIR) if f.startswith(prefix))
        if not files:
            return await interaction.response.send_message(
                "📁 Aucune sauvegarde disponible pour ce serveur.", ephemeral=True
            )

        message = "**Sauvegardes de ce serveur :**\n" + "\n".join(f"`{f}`" for f in files)
        await interaction.response.send_message(message, ephemeral=True)

    # ===========================
    #   Supply toggle + status
    # ===========================
    @bot.tree.command(
        name="supplytoggle",
        description="(ADMIN) Active/désactive la boucle de ravitaillement spécial.",
    )
    @app_commands.describe(etat="ON pour activer, OFF pour désactiver")
    @app_commands.choices(
        etat=[app_commands.Choice(name="ON", value="on"), app_commands.Choice(name="OFF", value="off")]
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def supplytoggle(interaction: discord.Interaction, etat: app_commands.Choice[str]):
        guild_id = str(interaction.guild.id)
        set_special_supply_enabled(guild_id, etat.value == "on")
        await interaction.response.send_message(
            f"📦 Boucle de ravitaillement spécial : {'✅ ACTIVE' if etat.value == 'on' else '⛔ DÉSACTIVÉE'}.",
            ephemeral=True,
        )

    @bot.tree.command(
        name="supplystatus",
        description="Affiche si la boucle de ravitaillement spécial est active pour ce serveur.",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def supplystatus(interaction: discord.Interaction):
        guild_id = str(interaction.guild.id)
        status = "✅ ACTIVE" if is_special_supply_enabled(guild_id) else "⛔ DÉSACTIVÉE"
        await interaction.response.send_message(
            f"📦 La boucle de ravitaillement spécial est actuellement : **{status}**",
            ephemeral=True,
        )

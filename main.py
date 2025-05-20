import discord
from discord.ext import commands
import asyncio
import os
from dotenv import load_dotenv

from config import load_config, config
from data import charger, sauvegarder
from utils import cooldowns, get_random_item, inventaire, hp, leaderboard, OBJETS, get_user_data
from combat import apply_item_with_cooldown
from inventory import build_inventory_embed
from leaderboard import build_leaderboard_embed
from help import register_help_commands
from daily import register_daily_command
from fight import register_fight_command
from heal import register_heal_command
from admin import register_admin_commands
from profile import register_profile_command

load_dotenv()

intents = discord.Intents.default()
intents.message_content = True
intents.messages = True
intents.reactions = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)
message_counter = 0
random_threshold = 5
last_drop_time = 0 

# ===================== Slash Commands ======================

@bot.tree.command(name="inv", description="Voir l'inventaire d'un membre")
async def inv_slash(interaction: discord.Interaction, user: discord.Member = None):
    member = user or interaction.user
    uid = str(member.id)
    embed = build_inventory_embed(uid, bot, str(interaction.guild.id))
    await interaction.response.send_message(embed=embed, ephemeral=(user is not None and user != interaction.user))

@bot.tree.command(name="leaderboard", description="Voir le classement SomniCorp")
async def leaderboard_slash(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)
    embed = await build_leaderboard_embed(bot, interaction.guild)  # ← passe la guild ici
    await interaction.followup.send(embed=embed)

# ===================== Command Registration ======================

def register_all_commands(bot):
    register_help_commands(bot)
    register_daily_command(bot)
    register_fight_command(bot)
    register_heal_command(bot)
    register_admin_commands(bot)
    register_profile_command(bot)

# ===================== Events ======================

@bot.event
async def on_ready():
    for guilde in bot.guilds:
        await bot.tree.sync(guild=guilde)

    register_all_commands(bot)

    for guild in bot.guilds:
        await bot.tree.sync(guild=guild)  # ← ligne indentée correctement

    charger()
    load_config()

    print(f"✅ SomniCorp Bot prêt. Connecté en tant que {bot.user}")
    print("🔧 Commandes slash enregistrées :")
    for command in bot.tree.get_commands():
        print(f" - /{command.name}")

    bot.loop.create_task(update_leaderboard_loop())
    bot.loop.create_task(yearly_reset_loop())

@bot.event
async def on_message(message):
    global message_counter, random_threshold, last_drop_time
    await bot.process_commands(message)

    if message.author.bot:
        return

    current_time = asyncio.get_event_loop().time()
    if current_time - last_drop_time < 15:
        return 

    message_counter += 1
    if message_counter >= random_threshold:
        item = get_random_item()
        await message.add_reaction(item)
        last_drop_time = current_time  

        collected_users = set()

        def check(reaction, user):
            return (
                reaction.message.id == message.id
                and str(reaction.emoji) == item
                and not user.bot
                and user.id not in collected_users
            )

        end_time = asyncio.get_event_loop().time() + 15
        while len(collected_users) < 3 and asyncio.get_event_loop().time() < end_time:
            try:
                reaction, user = await asyncio.wait_for(
                    bot.wait_for("reaction_add", check=check),
                    timeout=end_time - asyncio.get_event_loop().time(),
                )
                guild_id = str(message.guild.id)
                uid = str(user.id)
                user_inv, _, _ = get_user_data(guild_id, uid)
                user_inv.append(item)
                collected_users.add(user.id)
                await message.channel.send(f"✅ {user.mention} a ramassé {item} offert par SomniCorp!")
            except asyncio.TimeoutError:
                break

        if len(collected_users) < 3:
            await message.channel.send("⛔ Le dépôt de ravitaillement de SomniCorp a expiré.")

        message_counter = 0
        random_threshold = 5

# ===================== Auto-Update Leaderboard ======================

async def update_leaderboard_loop():
    await bot.wait_until_ready()
    from config import get_guild_config, save_config

    while not bot.is_closed():
        for guild in bot.guilds:
            guild_id = str(guild.id)
            guild_config = get_guild_config(guild_id)

            channel_id = guild_config.get("leaderboard_channel_id")
            message_id = guild_config.get("leaderboard_message_id")

            if not channel_id:
                continue

            channel = bot.get_channel(channel_id)
            if not channel:
                continue

            medals = ["🥇", "🥈", "🥉"]
            server_lb = leaderboard.get(guild_id, {})
            sorted_lb = sorted(server_lb.items(), key=lambda x: x[1]['degats'] + x[1]['soin'], reverse=True)
            lines = []
            rank = 0

            for uid, stats in sorted_lb:
                member = guild.get_member(int(uid))
                if not member:
                    continue
                if rank >= 10:
                    break
                total = stats['degats'] + stats['soin']
                prefix = medals[rank] if rank < len(medals) else f"{rank + 1}."
                lines.append(f"{prefix} **{member.display_name}** → 🗡️ {stats['degats']} | 💚 {stats['soin']} = **{total}** points")
                rank += 1

            text = (
                "🏆 __**CLASSEMENT SOMNICORP - ÉDITION SPÉCIALE**__ 🏆\n\n" +
                "\n".join(lines) +
                "\n\n📌 Mise à jour automatique toutes les 5 minutes."
            ) if lines else "*Aucune donnée disponible.*"

            try:
                if message_id:
                    msg = await channel.fetch_message(message_id)
                    await msg.edit(content=text)
                else:
                    raise discord.NotFound(response=None, message="No message ID")
            except (discord.NotFound, discord.HTTPException):
                msg = await channel.send(content=text)
                guild_config["leaderboard_message_id"] = msg.id
                save_config()

        await asyncio.sleep(300)

import datetime
import asyncio
import logging

async def yearly_reset_loop():
    await bot.wait_until_ready()
    while not bot.is_closed():
        now = datetime.datetime.utcnow()
        if now.month == 12 and now.day == 31 and now.hour == 23 and now.minute == 59:
            from storage import inventaire, hp, leaderboard
            from data import sauvegarder

            for gid in list(inventaire.keys()):
                inventaire[gid] = {}
            for gid in list(hp.keys()):
                hp[gid] = {}
            for gid in list(leaderboard.keys()):
                leaderboard[gid] = {}

            sauvegarder()
            print("🎉 Réinitialisation annuelle effectuée pour tous les serveurs.")
            announcement_msg = "🎊 Les statistiques ont été remises à zéro pour la nouvelle année ! Merci pour votre participation à SomniCorp."

            # Envoi du message d'annonce dans chaque salon de classement configuré
            for server_id, server_conf in config.items():
                channel_id = server_conf.get("leaderboard_channel_id")
                if not channel_id:
                    continue
                try:
                    channel = bot.get_channel(channel_id)
                    if channel:
                        await channel.send(announcement_msg)
                except Exception as e:
                    logging.error(f"❌ Impossible d'envoyer l'annonce dans le salon {channel_id} (serveur {server_id}) : {e}")

            # Attendre 60 secondes pour éviter les doublons
            await asyncio.sleep(60)
        else:
            # Vérifie toutes les 30 secondes
            await asyncio.sleep(30)


# ===================== Run ======================

bot.run(os.getenv("DISCORD_TOKEN"))

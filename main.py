import discord
from discord.ext import commands
import asyncio
import os
import atexit
import signal
import sys
import datetime

from dotenv import load_dotenv
from config import load_config, config
from data import charger, sauvegarder
from utils import cooldowns, get_random_item, OBJETS  
from storage import get_user_data  
from storage import inventaire, hp, leaderboard
from combat import apply_item_with_cooldown
from inventory import build_inventory_embed
from leaderboard import build_leaderboard_embed
from help import register_help_commands
from daily import register_daily_command
from fight import register_fight_command
from heal import register_heal_command
from admin import register_admin_commands
from profile import register_profile_command
from temp_commands import register_temp_commands

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
    try:
        await interaction.response.defer(thinking=False)
    except discord.NotFound:
        return  

    member = user or interaction.user
    guild_id = str(interaction.guild.id)
    user_id = str(member.id)

    embed = build_inventory_embed(user_id, bot, guild_id)

    await interaction.followup.send(
        embed=embed,
        ephemeral=(user is not None and user != interaction.user)
    )

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
    register_temp_commands(bot)
    
# ===================== Events ======================

@bot.event
async def on_ready():
    charger() 
    load_config()

    register_all_commands(bot)

    for guild in bot.guilds:
        await bot.tree.sync(guild=guild)

    print(f"✅ SomniCorp Bot prêt. Connecté en tant que {bot.user}")
    print("🔧 Commandes slash enregistrées :")
    for command in bot.tree.get_commands():
        print(f" - /{command.name}")

    bot.loop.create_task(update_leaderboard_loop())
    bot.loop.create_task(yearly_reset_loop())
    bot.loop.create_task(autosave_data_loop())
    bot.loop.create_task(daily_restart_loop())

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
        last_drop_time = current_time
        item = get_random_item()
        await message.add_reaction(item)  

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
    from storage import hp  # Assure-toi que c’est bien importé

    while not bot.is_closed():
        for guild in bot.guilds:
            guild_id = str(guild.id)
            guild_config = get_guild_config(guild_id)

            channel_id = guild_config.get("special_leaderboard_channel_id")
            message_id = guild_config.get("special_leaderboard_message_id")

            if not channel_id:
                continue

            channel = bot.get_channel(channel_id)
            if not channel:
                continue

            medals = ["🥇", "🥈", "🥉"]
            server_lb = leaderboard.get(guild_id, {})
            server_hp = hp.get(guild_id, {})
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
                current_hp = server_hp.get(uid, 100)
                prefix = medals[rank] if rank < len(medals) else f"{rank + 1}."
                lines.append(
                    f"{prefix} **{member.display_name}** → 🗡️ {stats['degats']} | 💚 {stats['soin']} = **{total}** points | ❤️ {current_hp} PV"
                )
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
                guild_config["special_leaderboard_message_id"] = msg.id
                save_config()

        await asyncio.sleep(60)

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

async def autosave_data_loop():
    from data import sauvegarder
    await bot.wait_until_ready()
    while not bot.is_closed():
        sauvegarder()
        await asyncio.sleep(300)

async def daily_restart_loop():
    await bot.wait_until_ready()
    while not bot.is_closed():
        now = datetime.datetime.now()
        tomorrow = now + datetime.timedelta(days=1)
        restart_time = datetime.datetime.combine(tomorrow.date(), datetime.time(23, 59, 59))

        wait_seconds = (restart_time - now).total_seconds()
        print(f"⏳ Prochain redémarrage automatique prévu dans {int(wait_seconds)} secondes.")
        await asyncio.sleep(wait_seconds)

        print("🔁 Redémarrage automatique quotidien en cours (Render)...")
        sauvegarder()
        sys.exit(0)  # ✅ Render va relancer le bot automatiquement

def on_shutdown():
    print("💾 Sauvegarde finale avant extinction du bot...")
    sauvegarder()

# Appel automatique à la fermeture normale du programme
atexit.register(on_shutdown)

# Capture manuelle de signaux comme Ctrl+C ou arrêt système
def handle_signal(sig, frame):
    on_shutdown()
    sys.exit(0)

signal.signal(signal.SIGINT, handle_signal)
signal.signal(signal.SIGTERM, handle_signal)
# ===================== Run ======================

bot.run(os.getenv("DISCORD_TOKEN"))

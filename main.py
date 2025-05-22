import discord
from discord.ext import commands
import asyncio
import os
import atexit
import signal
import sys
import datetime
import time

from dotenv import load_dotenv
from config import load_config, get_config, get_guild_config, save_config
from data import charger, sauvegarder, virus_status, poison_status, infection_status
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
from status import register_status_command
from box import register_box_command

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
@bot.command()
async def check_persistent(ctx):
    files = os.listdir("/persistent")
    await ctx.send(f"Contenu de `/persistent` :\n" + "\n".join(files) if files else "📂 Aucun fichier trouvé.")

@bot.command()
async def sync(ctx):
    await bot.tree.sync(guild=ctx.guild)
    await ctx.send("✅ Commandes slash resynchronisées avec succès.")

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
    register_status_command(bot)
    register_box_command(bot)                     
    
# ===================== Events ======================

@bot.event
async def on_ready():
    charger()
    load_config()
    register_all_commands(bot)

    try:
        await bot.tree.sync()
        print("✅ Commandes slash synchronisées globalement.")
    except Exception as e:
        print(f"❌ Erreur pendant la synchronisation des slash commands : {e}")

    print(f"✅ SomniCorp Bot prêt. Connecté en tant que {bot.user}")
    print("🔧 Commandes slash enregistrées :")
    for command in bot.tree.get_commands():
        print(f" - /{command.name}")

    bot.loop.create_task(update_leaderboard_loop())
    bot.loop.create_task(yearly_reset_loop())
    bot.loop.create_task(autosave_data_loop())
    bot.loop.create_task(daily_restart_loop())
    bot.loop.create_task(virus_damage_loop())
    bot.loop.create_task(poison_damage_loop())
    bot.loop.create_task(infection_damage_loop())
    bot.loop.create_task(regeneration_loop_start())
    
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
    from storage import hp

    while not bot.is_closed():
        print("⏳ [LOOP] Tentative de mise à jour des leaderboards spéciaux...")

        for guild in bot.guilds:
            guild_id = str(guild.id)
            guild_config = get_guild_config(guild_id)

            channel_id = guild_config.get("special_leaderboard_channel_id")
            message_id = guild_config.get("special_leaderboard_message_id")

            print(f"🔍 [{guild.name}] Config trouvée : {guild_config}")
            print(f" → Channel ID : {channel_id} | Message ID : {message_id}")

            if not channel_id:
                print(f"⚠️ Aucun salon configuré pour {guild.name}")
                continue

            channel = bot.get_channel(channel_id)
            if not channel:
                print(f"❌ Salon introuvable : {channel_id}")
                continue

            medals = ["🥇", "🥈", "🥉"]
            server_lb = leaderboard.get(guild_id, {})
            server_hp = hp.get(guild_id, {})
            sorted_lb = sorted(server_lb.items(), key=lambda x: x[1]['degats'] + x[1]['soin'], reverse=True)

            lines = []
            rank = 0

            for uid, stats in sorted_lb:
                user = bot.get_user(int(uid))
                if not user:
                    continue
                if rank >= 10:
                    break

                degats = stats.get("degats", 0)
                soin = stats.get("soin", 0)
                kills = stats.get("kills", 0)
                morts = stats.get("morts", 0)
                total = degats + soin + kills * 50 - morts * 25
                pv = hp.get(guild_id, {}).get(uid, 100)

                prefix = medals[rank] if rank < len(medals) else f"{rank + 1}."
                lines.append(
                    f"{prefix} **{user.display_name}** → "
                    f"🗡️ {degats} | 💚 {soin} | 🎽 {kills} | 💀 {morts} = **{total}** points | ❤️ {pv} PV"
                )
                rank += 1

            text = (
                "🏆 __**CLASSEMENT SOMNICORP - ÉDITION SPÉCIALE**__ 🏆\n\n" +
                "\n".join(lines) +
                "\n\n📌 Classement mis à jour automatiquement par SomniCorp."
            ) if lines else "*Aucune donnée disponible.*"

            try:
                if message_id:
                    print(f"✏️ Modification du message {message_id} dans {channel.name}")
                    msg = await channel.fetch_message(message_id)
                    await msg.edit(content=text)
                else:
                    raise discord.NotFound(response=None, message="No message ID")
            except (discord.NotFound, discord.HTTPException):
                print(f"📤 Envoi d’un nouveau message dans {channel.name}")
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

            await asyncio.sleep(60)
        else:
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
        sys.exit(0)  
        
async def virus_damage_loop():
    await bot.wait_until_ready()
    print("🦠 Boucle de dégâts viraux démarrée.")

    while not bot.is_closed():
        now = time.time()

        for guild in bot.guilds:
            gid = str(guild.id)
            if gid not in virus_status:
                continue

            for uid, status in list(virus_status[gid].items()):
                start = status.get("start")
                duration = status.get("duration")
                last_tick = status.get("last_tick", 0)
                source_id = status.get("source")
                channel_id = status.get("channel_id")

                elapsed = now - start
                tick_count = int(elapsed // 3600)

                if elapsed >= duration:
                    del virus_status[gid][uid]
                    continue

                if tick_count > last_tick:
                    dmg = 5
                    current_hp = hp[gid].get(uid, 100)
                    new_hp = max(current_hp - dmg, 0)
                    hp[gid][uid] = new_hp
                    virus_status[gid][uid]["last_tick"] = tick_count

                    # ➕ Message Embed
                    if channel_id:
                        channel = bot.get_channel(channel_id)
                        if channel:
                            embed = discord.Embed(
                                title="🦠 Dégâts de virus",
                                description=f"<@{uid}> subit **{dmg} dégâts** viraux ! (PV: {current_hp} → {new_hp})",
                                color=discord.Color.dark_purple()
                            )
                            await channel.send(embed=embed)

                    # ➕ Gain de points pour la source
                    if source_id:
                        leaderboard.setdefault(gid, {})
                        leaderboard[gid].setdefault(source_id, {"degats": 0, "soin": 0, "kills": 0, "morts": 0})
                        leaderboard[gid][source_id]["degats"] += dmg

                    print(f"🦠 {uid} a subi {dmg} dégâts viraux (HP: {current_hp} → {new_hp})")

                    if new_hp == 0:
                        hp[gid][uid] = 100
                        leaderboard.setdefault(gid, {})
                        leaderboard[gid].setdefault(uid, {"degats": 0, "soin": 0, "kills": 0, "morts": 0})
                        leaderboard[gid][uid]["degats"] = max(0, leaderboard[gid][uid]["degats"] - 25)
                        leaderboard[gid][uid]["morts"] += 1

                        if source_id:
                            leaderboard[gid].setdefault(source_id, {"degats": 0, "soin": 0, "kills": 0, "morts": 0})
                            leaderboard[gid][source_id]["degats"] += 50
                            leaderboard[gid][source_id]["kills"] += 1

                        print(f"💀 {uid} a été vaincu par un virus et revient à 100 PV.")

        await asyncio.sleep(60)

async def poison_damage_loop():
    await bot.wait_until_ready()
    print("🧪 Boucle de dégâts de poison démarrée.")

    while not bot.is_closed():
        now = time.time()

        for guild in bot.guilds:
            gid = str(guild.id)
            if gid not in poison_status:
                continue

            for uid, status in list(poison_status[gid].items()):
                start = status.get("start")
                duration = status.get("duration")
                last_tick = status.get("last_tick", 0)
                source_id = status.get("source")
                channel_id = status.get("channel_id")

                elapsed = now - start
                tick_count = int(elapsed // 1800)

                if elapsed >= duration:
                    del poison_status[gid][uid]
                    continue

                if tick_count > last_tick:
                    dmg = 3
                    current_hp = hp[gid].get(uid, 100)
                    new_hp = max(current_hp - dmg, 0)
                    hp[gid][uid] = new_hp
                    poison_status[gid][uid]["last_tick"] = tick_count

                    # ➕ Embed public
                    if channel_id:
                        channel = bot.get_channel(channel_id)
                        if channel:
                            embed = discord.Embed(
                                title="🧪 Dégâts de poison",
                                description=f"<@{uid}> subit **{dmg} dégâts** de poison ! (PV: {current_hp} → {new_hp})",
                                color=discord.Color.dark_green()
                            )
                            await channel.send(embed=embed)

                    # ➕ Gain de points
                    if source_id:
                        leaderboard.setdefault(gid, {})
                        leaderboard[gid].setdefault(source_id, {"degats": 0, "soin": 0, "kills": 0, "morts": 0})
                        leaderboard[gid][source_id]["degats"] += dmg

                    print(f"🧪 {uid} a subi {dmg} dégâts de poison (HP: {current_hp} → {new_hp})")

                    # 💀 KO
                    if new_hp == 0:
                        hp[gid][uid] = 100
                        leaderboard.setdefault(gid, {})
                        leaderboard[gid].setdefault(uid, {"degats": 0, "soin": 0, "kills": 0, "morts": 0})
                        leaderboard[gid][uid]["degats"] = max(0, leaderboard[gid][uid]["degats"] - 25)
                        leaderboard[gid][uid]["morts"] += 1

                        if source_id:
                            leaderboard[gid].setdefault(source_id, {"degats": 0, "soin": 0, "kills": 0, "morts": 0})
                            leaderboard[gid][source_id]["degats"] += 50
                            leaderboard[gid][source_id]["kills"] += 1

                        print(f"💀 {uid} a été vaincu par du poison et revient à 100 PV.")

        await asyncio.sleep(60)

async def infection_damage_loop():
    await bot.wait_until_ready()
    print("🧟 Boucle de dégâts d'infection démarrée.")

    while not bot.is_closed():
        now = time.time()

        for guild in bot.guilds:
            gid = str(guild.id)
            if gid not in infection_status:
                continue

            for uid, status in list(infection_status[gid].items()):
                start = status.get("start")
                duration = status.get("duration")
                last_tick = status.get("last_tick", 0)
                source_id = status.get("source")
                channel_id = status.get("channel_id")

                elapsed = now - start
                tick_count = int(elapsed // 1800)  # 30 minutes

                if elapsed >= duration:
                    del infection_status[gid][uid]
                    continue

                if tick_count > last_tick:
                    dmg = 2
                    current_hp = hp[gid].get(uid, 100)
                    new_hp = max(current_hp - dmg, 0)
                    hp[gid][uid] = new_hp
                    infection_status[gid][uid]["last_tick"] = tick_count

                    # Embed de dégâts envoyés dans le salon d’origine
                    if channel_id:
                        channel = bot.get_channel(channel_id)
                        if channel:
                            embed = discord.Embed(
                                title="🧟 Dégâts d'infection",
                                description=f"<@{uid}> subit **{dmg} dégâts** d'infection ! (PV: {current_hp} → {new_hp})",
                                color=discord.Color.dark_green()
                            )
                            await channel.send(embed=embed)

                    # Points pour la source
                    if source_id:
                        leaderboard.setdefault(gid, {})
                        leaderboard[gid].setdefault(source_id, {"degats": 0, "soin": 0, "kills": 0, "morts": 0})
                        leaderboard[gid][source_id]["degats"] += dmg

                    print(f"🧟 {uid} a subi {dmg} dégâts d'infection (HP: {current_hp} → {new_hp})")

                    if new_hp == 0:
                        hp[gid][uid] = 100
                        leaderboard.setdefault(gid, {})
                        leaderboard[gid].setdefault(uid, {"degats": 0, "soin": 0, "kills": 0, "morts": 0})
                        leaderboard[gid][uid]["degats"] = max(0, leaderboard[gid][uid]["degats"] - 25)
                        leaderboard[gid][uid]["morts"] += 1

                        if source_id:
                            leaderboard[gid].setdefault(source_id, {"degats": 0, "soin": 0, "kills": 0, "morts": 0})
                            leaderboard[gid][source_id]["degats"] += 50
                            leaderboard[gid][source_id]["kills"] += 1

                        print(f"💀 {uid} a été vaincu par une infection et revient à 100 PV.")

        await asyncio.sleep(60)
        
@tasks.loop(minutes=30)
async def regeneration_loop():
    now = time.time()
    for guild_id, users in list(regeneration_status.items()):
        for user_id, stat in list(users.items()):
            if now - stat["start"] > stat["duration"]:
                del regeneration_status[guild_id][user_id]
                continue

            if now - stat["last_tick"] < 1800:
                continue

            stat["last_tick"] = now
            hp.setdefault(guild_id, {})
            leaderboard.setdefault(guild_id, {})
            leaderboard[guild_id].setdefault(stat["source"], {"degats": 0, "soin": 0, "kills": 0, "morts": 0})
            hp[guild_id][user_id] = min(hp[guild_id].get(user_id, 100) + 3, 100)
            leaderboard[guild_id][stat["source"]]["soin"] += 3

            # Annonce dans le salon d'origine
            try:
                channel = bot.get_channel(stat.get("channel_id", 0))
                if channel:
                    member = await bot.fetch_user(int(user_id))
                    await channel.send(
                        embed=discord.Embed(
                            title="💕 Régénération SomniCorp",
                            description=f"{member.mention} récupère **+3 PV** grâce à l'effet de régénération.",
                            color=discord.Color.green()
                        )
                    )
            except Exception as e:
                print(f"[regeneration_loop] Erreur: {e}")

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

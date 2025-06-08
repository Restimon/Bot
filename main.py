import discord
from discord.ext import commands, tasks
import asyncio
import os
import atexit
import signal
import sys
import datetime
import time
import logging
import random

from dotenv import load_dotenv
from config import load_config, get_config, get_guild_config, save_config
from data import charger, sauvegarder, virus_status, poison_status, infection_status, regeneration_status, shields, supply_data, backup_auto_independante
from utils import get_random_item, OBJETS, handle_death  
from storage import get_user_data  
from storage import inventaire, hp, leaderboard
from combat import apply_item_with_cooldown, apply_shield
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
from embeds import build_embed_from_item
from cooldowns import is_on_cooldown
from leaderboard_utils import update_leaderboard
from item_list import register_item_command
from special_supply import update_last_active_channel, special_supply_loop
from kiss import register_kiss_command
from hug import register_hug_command
from pat import register_pat_command
from punch import register_punch_command
from slap import register_slap_command
from ahelp import register_ahelp_command
from sync_command import register_sync_command
from utilitaire import register_utilitaire_command
from lick import register_lick_command
from love import register_love_command
from bite import register_bite_command

os.makedirs("/persistent", exist_ok=True)

load_dotenv()
charger()

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
MAX_SUPPLIES_PER_DAY = 5

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

@bot.tree.command(name="leaderboard", description="Voir le classement GotValis")
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
    register_item_command(bot)
    register_kiss_command(bot)
    register_hug_command(bot)
    register_pat_command(bot)
    register_punch_command(bot)
    register_slap_command(bot)
    register_ahelp_command(bot)
    register_sync_command(bot)
    register_utilitaire_command(bot) 
    register_lick_command(bot)
    register_bite_command(bot)
    register_love_command(bot)

# ===================== Events ======================

@bot.event
async def on_ready():
    await bot.tree.sync(guild=discord.Object(id=1269384239254605856))
    print("🤖 Bot prêt. Synchronisation des commandes...")

    # Enregistrement des commandes (une seule fois)
    register_all_commands(bot)

    # Synchronisation globale (sans GUILD_ID)
    try:
        await bot.tree.sync()
        print("✅ Commandes slash synchronisées globalement.")
    except Exception as e:
        print(f"❌ Erreur de synchronisation globale : {e}")

    # Chargement des données
    now = time.time()
    charger()
    load_config()

    # Boucles de statut & ravitaillement
    asyncio.create_task(special_supply_loop(bot))
    asyncio.create_task(virus_damage_loop())
    asyncio.create_task(poison_damage_loop())
    asyncio.create_task(infection_damage_loop())

    # Présence du bot
    activity = discord.Activity(type=discord.ActivityType.watching, name="en /help | https://discord.gg/jkbfFRqzZP")
    await bot.change_presence(status=discord.Status.online, activity=activity)

    # Gestion du ravitaillement en cours (si redémarrage pendant un ravitaillement actif)

    print(f"✅ GotValis Bot prêt. Connecté en tant que {bot.user}")
    print("🔧 Commandes slash enregistrées :")
    for command in bot.tree.get_commands():
        print(f" - /{command.name}")

    # Boucles principales
    bot.loop.create_task(update_leaderboard_loop())
    bot.loop.create_task(yearly_reset_loop())
    bot.loop.create_task(autosave_data_loop())
    bot.loop.create_task(daily_restart_loop())
    asyncio.create_task(auto_backup_loop())
    regeneration_loop.start()
    
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    from special_supply import update_last_active_channel
    try:
        update_last_active_channel(message)
    except Exception as e:
        print(f"[on_message] Erreur update_last_active_channel : {e}")

    try:
        guild_id = str(message.guild.id)
        channel_id = message.channel.id
        supply_data.setdefault(guild_id, {})
        supply_data[guild_id].setdefault("channel_activity_log", {})
        supply_data[guild_id]["channel_activity_log"][channel_id] = time.time()
        sauvegarder()
    except Exception as e:
        print(f"[on_message] Erreur update channel_activity_log : {e}")

    await bot.process_commands(message)

    # 📦 Ravitaillement classique aléatoire
    global message_counter, random_threshold, last_drop_time

    message_counter += 1
    if message_counter < random_threshold:
        return

    current_time = asyncio.get_event_loop().time()
    if current_time - last_drop_time < 30:
        return

    last_drop_time = current_time
    message_counter = 0
    random_threshold = random.randint(4, 8)  # tu peux ajuster la plage si tu veux

    item = get_random_item()
    await message.add_reaction(item)
    collected_users = []

    def check(reaction, user):
        return (
            reaction.message.id == message.id
            and str(reaction.emoji) == item
            and not user.bot
            and user.id not in [u.id for u in collected_users]
        )

    end_time = current_time + 15
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
            collected_users.append(user)
        except asyncio.TimeoutError:
            break

    if collected_users:
        mention_list = "\n".join(f"✅ {user.mention}" for user in collected_users)
        embed = discord.Embed(
            title="📦 Ravitaillement récupéré",
            description=(
                f"Le dépôt de **GotValis** contenant {item} a été récupéré par :\n\n{mention_list}"
            ),
            color=0x00FFAA
        )
    else:
        embed = discord.Embed(
            title="💥 Ravitaillement détruit",
            description=f"Le dépôt de **GotValis** contenant {item} s’est **auto-détruit**. 💣",
            color=0xFF0000
        )

    await message.channel.send(embed=embed)

@bot.event
async def on_raw_reaction_add(payload):
    gid = str(payload.guild_id)
    mid = str(payload.message_id)
    uid = str(payload.user_id)

    if gid not in supply_data:
        return

    data = supply_data[gid]

    # Check si supply est bien ouvert
    if not data.get("is_open", False):
        return

    # Check si c'est le bon message
    active_msg_id = data.get("active_supply_id")
    if active_msg_id != mid:
        return

    # Check si c'est la bonne emoji
    if str(payload.emoji) != "📦":
        return

    # Check si ce n'est pas un bot
    if payload.user_id == bot.user.id:
        return

    # Ici tu ne supprimes plus la réaction !!
    # Juste log si tu veux :
    print(f"✅ Réaction validée : {payload.user_id} sur {mid} (supply actif)")
    
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

            # Tri sécurisé
            def get_score(entry):
                stats = entry[1]
                return stats.get("degats", 0) + stats.get("soin", 0)

            sorted_lb = sorted(server_lb.items(), key=get_score, reverse=True)

            lines = []
            rank = 0

            for uid, stats in sorted_lb:
                # Vérifie que uid est un entier valide
                try:
                    int_uid = int(uid)
                    user = bot.get_user(int_uid)
                    if not user:
                        continue
                except (ValueError, TypeError):
                    print(f"⚠️ UID non valide ignoré : {uid}")
                    continue

                if rank >= 10:
                    break

                degats = stats.get("degats", 0)
                soin = stats.get("soin", 0)
                kills = stats.get("kills", 0)
                morts = stats.get("morts", 0)
                total = degats + soin + kills * 50 - morts * 25
                pv = server_hp.get(uid, 100)

                prefix = medals[rank] if rank < len(medals) else f"{rank + 1}."
                lines.append(
                    f"{prefix} **{user.display_name}** → "
                    f"🗡️ {degats} | 💚 {soin} | 🎽 {kills} | 💀 {morts} = **{total}** points | ❤️ {pv} PV"
                )
                rank += 1

            content = (
                "> 🏆 __**CLASSEMENT GOTVALIS - ÉDITION SPÉCIALE**__ 🏆\n\n" +
                "\n".join([f"> {line}" for line in lines]) +
                "\n\n 📌 Classement mis à jour automatiquement par GotValis."
            ) if lines else "*Aucune donnée disponible.*"

            try:
                if message_id:
                    print(f"✏️ Modification du message {message_id} dans {channel.name}")
                    msg = await channel.fetch_message(message_id)
                    if msg.content != content:
                        await msg.edit(content=content)
                else:
                    raise discord.NotFound(response=None, message="No message ID")
            except (discord.NotFound, discord.HTTPException) as e:
                print(f"📤 Envoi d’un nouveau message dans {channel.name} ({e})")
                try:
                    msg = await channel.send(content=content)
                    guild_config["special_leaderboard_message_id"] = msg.id
                    save_config()
                except Exception as e:
                    print(f"❌ Échec de l’envoi du message dans {channel.name} : {e}")

        await asyncio.sleep(60)
        
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
            announcement_msg = "🎊 Les statistiques ont été remises à zéro pour la nouvelle année ! Merci pour votre participation à GotValis."

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
        
@tasks.loop(seconds=30)
async def virus_damage_loop():
    await bot.wait_until_ready()
    print("🦠 Boucle de dégâts viraux démarrée.")

    while not bot.is_closed():
        now = time.time()

        for guild in bot.guilds:
            gid = str(guild.id)
            await asyncio.sleep(0)

            if gid not in virus_status:
                continue

            for uid, status in list(virus_status[gid].items()):
                await asyncio.sleep(0)

                start = status.get("start")
                duration = status.get("duration")
                next_tick = status.get("next_tick", 0)
                source_id = status.get("source")
                channel_id = status.get("channel_id")

                elapsed = now - start
                if elapsed >= duration:
                    del virus_status[gid][uid]
                    continue

                if now < next_tick:
                    continue

                virus_status[gid][uid]["next_tick"] = now + 3600  # prochain tick dans 1h

                dmg = 5
                hp.setdefault(gid, {})
                shields.setdefault(gid, {})

                hp_before = hp[gid].get(uid, 100)
                pb_before = shields[gid].get(uid, 0)

                dmg_final, lost_pb, shield_broken = apply_shield(gid, uid, dmg)
                pb_after = shields[gid].get(uid, 0)
                hp_after = max(hp_before - dmg_final, 0)
                hp[gid][uid] = hp_after

                real_dmg = hp_before - hp_after

                if uid != source_id:
                    leaderboard.setdefault(gid, {}).setdefault(source_id, {"degats": 0, "soin": 0, "kills": 0, "morts": 0})
                    leaderboard[gid][source_id]["degats"] += real_dmg

                remaining = max(0, duration - elapsed)
                remaining_min = int(remaining // 60)

                try:
                    channel = bot.get_channel(channel_id)
                    if channel:
                        member = await bot.fetch_user(int(uid))
                        await asyncio.sleep(0.05)

                        if lost_pb and real_dmg == 0:
                            desc = (
                                f"🦠 {member.mention} subit **{lost_pb} dégâts** *(Virus)*.\n"
                                f"🛡️ {pb_before} - {lost_pb} PB = ❤️ {hp_after} PV / 🛡️ {pb_after} PB"
                            )
                        elif lost_pb and real_dmg > 0:
                            desc = (
                                f"🦠 {member.mention} subit **{lost_pb + real_dmg} dégâts** *(Virus)*.\n"
                                f"❤️ {hp_before} - {real_dmg} PV / 🛡️ {pb_before} - {lost_pb} PB = ❤️ {hp_after} PV / 🛡️ {pb_after} PB"
                            )
                        else:
                            desc = (
                                f"🦠 {member.mention} subit **{real_dmg} dégâts** *(Virus)*.\n"
                                f"❤️ {hp_before} - {real_dmg} PV = {hp_after} PV"
                            )

                        desc += f"\n⏳ Temps restant : **{remaining_min} min**"

                        embed = discord.Embed(description=desc, color=discord.Color.dark_purple())
                        await channel.send(embed=embed)
                        await asyncio.sleep(0.05)

                        if shield_broken:
                            await channel.send(embed=discord.Embed(
                                title="🛡 Bouclier détruit",
                                description=f"Le bouclier de {member.mention} a été **détruit** par le virus.",
                                color=discord.Color.dark_blue()
                            ))

                        if hp_after == 0:
                            handle_death(gid, uid, source_id)
                            embed_ko = discord.Embed(
                                title="💀 KO viral détecté",
                                description=(
                                    f"**GotValis** détecte une chute à 0 PV pour {member.mention}.\n"
                                    f"🦠 Effondrement dû à une **charge virale critique**.\n"
                                    f"🔄 {member.mention} est **stabilisé à 100 PV**."
                                ),
                                color=0x8800FF
                            )
                            await channel.send(embed=embed_ko)

                except Exception as e:
                    print(f"[virus_damage_loop] Erreur d’envoi embed : {e}")

        await asyncio.sleep(30)
        
@tasks.loop(seconds=30)
async def poison_damage_loop():
    await bot.wait_until_ready()
    print("🧪 Boucle de dégâts de poison démarrée.")

    while not bot.is_closed():
        now = time.time()

        for guild in bot.guilds:
            gid = str(guild.id)
            await asyncio.sleep(0)

            if gid not in poison_status:
                continue

            for uid, status in list(poison_status[gid].items()):
                await asyncio.sleep(0)

                start = status.get("start")
                duration = status.get("duration")
                next_tick = status.get("next_tick", 0)
                source_id = status.get("source")
                channel_id = status.get("channel_id")

                elapsed = now - start
                if elapsed >= duration:
                    del poison_status[gid][uid]
                    continue

                if now < next_tick:
                    continue

                poison_status[gid][uid]["next_tick"] = now + 1800  # Prochain tick dans 30 min

                # Appliquer dégâts
                dmg = 3
                hp.setdefault(gid, {})
                shields.setdefault(gid, {})

                before = hp[gid].get(uid, 100)
                pb_before = shields[gid].get(uid, 0)

                dmg_final, lost_pb, shield_broken = apply_shield(gid, uid, dmg)
                pb_after = shields[gid].get(uid, 0)
                after = max(before - dmg_final, 0)
                hp[gid][uid] = after

                real_dmg = before - after

                # Leaderboard
                if uid != source_id:
                    leaderboard.setdefault(gid, {}).setdefault(source_id, {"degats": 0, "soin": 0, "kills": 0, "morts": 0})
                    leaderboard[gid][source_id]["degats"] += real_dmg

                remaining = max(0, duration - elapsed)
                remaining_min = int(remaining // 60)

                try:
                    channel = bot.get_channel(channel_id)
                    if channel:
                        member = await bot.fetch_user(int(uid))
                        await asyncio.sleep(0.05)

                        if lost_pb and real_dmg == 0:
                            desc = (
                                f"🧪 {member.mention} subit **{lost_pb} dégâts** *(Poison)*.\n"
                                f"🛡️ {pb_before} - {lost_pb} PB = ❤️ {after} PV / 🛡️ {pb_after} PB"
                            )
                        elif lost_pb and real_dmg > 0:
                            desc = (
                                f"🧪 {member.mention} subit **{lost_pb + real_dmg} dégâts** *(Poison)*.\n"
                                f"❤️ {before} - {real_dmg} PV / 🛡️ {pb_before} - {lost_pb} PB = ❤️ {after} PV / 🛡️ {pb_after} PB"
                            )
                        else:
                            desc = (
                                f"🧪 {member.mention} subit **{real_dmg} dégâts** *(Poison)*.\n"
                                f"❤️ {before} - {real_dmg} PV = {after} PV"
                            )

                        desc += f"\n⏳ Temps restant : **{remaining_min} min**"

                        embed = discord.Embed(description=desc, color=discord.Color.dark_green())
                        await channel.send(embed=embed)
                        await asyncio.sleep(0.05)

                        if shield_broken:
                            await channel.send(embed=discord.Embed(
                                title="🛡 Bouclier détruit",
                                description=f"Le bouclier de {member.mention} a été **détruit** sous l'effet du poison.",
                                color=discord.Color.dark_blue()
                            ))

                        if after == 0:
                            handle_death(gid, uid, source_id)
                            embed_ko = discord.Embed(
                                title="💀 KO toxique détecté",
                                description=(
                                    f"**GotValis** détecte une chute à 0 PV pour {member.mention}.\n"
                                    f"🧪 Effondrement dû à une **intoxication sévère**.\n"
                                    f"🔄 {member.mention} est **stabilisé à 100 PV**."
                                ),
                                color=0x006600
                            )
                            await channel.send(embed=embed_ko)
                except Exception as e:
                    print(f"[poison_damage_loop] Erreur d’envoi embed : {e}")

        await asyncio.sleep(30)
        
@tasks.loop(seconds=30)
async def infection_damage_loop():
    await bot.wait_until_ready()
    print("🧟 Boucle de dégâts d'infection démarrée.")

    while not bot.is_closed():
        now = time.time()

        for guild in bot.guilds:
            gid = str(guild.id)
            await asyncio.sleep(0)

            if gid not in infection_status:
                continue

            for uid, status in list(infection_status[gid].items()):
                await asyncio.sleep(0)

                hp.setdefault(gid, {})
                shields.setdefault(gid, {})

                start = status.get("start")
                duration = status.get("duration")
                source_id = status.get("source")
                channel_id = status.get("channel_id")
                next_tick = status.get("next_tick", 0)

                # Supprime le statut s’il est expiré
                if now - start >= duration:
                    del infection_status[gid][uid]
                    continue

                # Ce n’est pas encore l’heure du tick
                if now < next_tick:
                    continue

                # Tick : mise à jour du prochain tick
                infection_status[gid][uid]["next_tick"] = now + 1800

                # Appliquer les dégâts
                dmg = 2
                hp_before = hp[gid].get(uid, 100)
                pb_before = shields[gid].get(uid, 0)

                dmg_final, lost_pb, shield_broken = apply_shield(gid, uid, dmg)
                pb_after = shields[gid].get(uid, 0)
                hp_after = max(hp_before - dmg_final, 0)
                hp[gid][uid] = hp_after

                real_dmg = hp_before - hp_after

                # Leaderboard
                if uid != source_id:
                    leaderboard.setdefault(gid, {}).setdefault(source_id, {"degats": 0, "soin": 0, "kills": 0, "morts": 0})
                    leaderboard[gid][source_id]["degats"] += real_dmg

                # Affichage
                remaining = max(0, duration - (now - start))
                remaining_min = int(remaining // 60)

                try:
                    channel = bot.get_channel(channel_id)
                    if channel:
                        member = await bot.fetch_user(int(uid))
                        await asyncio.sleep(0.05)

                        if lost_pb and real_dmg == 0:
                            desc = (
                                f"🧟 {member.mention} subit **{lost_pb} dégâts** *(Infection)*.\n"
                                f"🛡️ {pb_before} - {lost_pb} PB = ❤️ {hp_after} PV / 🛡️ {pb_after} PB"
                            )
                        elif lost_pb and real_dmg > 0:
                            desc = (
                                f"🧟 {member.mention} subit **{lost_pb + real_dmg} dégâts** *(Infection)*.\n"
                                f"❤️ {hp_before} - {real_dmg} PV / 🛡️ {pb_before} - {lost_pb} PB = ❤️ {hp_after} PV / 🛡️ {pb_after} PB"
                            )
                        else:
                            desc = (
                                f"🧟 {member.mention} subit **{real_dmg} dégâts** *(Infection)*.\n"
                                f"❤️ {hp_before} - {real_dmg} PV = {hp_after} PV"
                            )

                        desc += f"\n⏳ Temps restant : **{remaining_min} min**"
                        embed = discord.Embed(description=desc, color=discord.Color.dark_green())
                        await channel.send(embed=embed)
                        await asyncio.sleep(0.05)

                        if shield_broken:
                            await channel.send(embed=discord.Embed(
                                title="🛡 Bouclier détruit",
                                description=f"Le bouclier de {member.mention} a été **détruit** par l'infection.",
                                color=discord.Color.dark_blue()
                            ))

                        if hp_after == 0:
                            handle_death(gid, uid, source_id)
                            ko_embed = discord.Embed(
                                title="💀 KO infectieux détecté",
                                description=(
                                    f"**GotValis** détecte une chute à 0 PV pour {member.mention}.\n"
                                    f"🧟 Effondrement dû à une infection invasive.\n"
                                    f"🔄 Le patient est stabilisé à **100 PV**."
                                ),
                                color=0x880088
                            )
                            await channel.send(embed=ko_embed)
                except Exception as e:
                    print(f"[infection_damage_loop] Erreur d’envoi embed : {e}")

        await asyncio.sleep(30)
        
@tasks.loop(seconds=30)
async def regeneration_loop():
    now = time.time()
    for guild_id, users in list(regeneration_status.items()):
        for user_id, stat in list(users.items()):
            # Supprimer le statut s'il est expiré
            if now - stat["start"] > stat["duration"]:
                del regeneration_status[guild_id][user_id]
                continue

            # Vérifie si c’est le bon moment pour le tick
            if now < stat.get("next_tick", 0):
                continue

            # Met à jour le prochain tick
            stat["next_tick"] = now + 1800

            # Applique la régénération
            hp.setdefault(guild_id, {})
            before = hp[guild_id].get(user_id, 100)
            healed = min(3, 100 - before)
            after = min(before + healed, 100)
            hp[guild_id][user_id] = after

            # Leaderboard (si source définie)
            if "source" in stat and stat["source"]:
                leaderboard.setdefault(guild_id, {})
                leaderboard[guild_id].setdefault(stat["source"], {"degats": 0, "soin": 0, "kills": 0, "morts": 0})
                leaderboard[guild_id][stat["source"]]["soin"] += healed

            # Temps restant
            elapsed = now - stat["start"]
            remaining = max(0, stat["duration"] - elapsed)
            remaining_mn = int(remaining // 60)

            # Message
            try:
                channel = bot.get_channel(stat.get("channel_id", 0))
                if channel:
                    member = await bot.fetch_user(int(user_id))
                    embed = discord.Embed(
                        description=(
                            f"💕 {member.mention} récupère **{healed} PV** *(Régénération)*.\n"
                            f"❤️ {before} PV + {healed} PV = {after} PV\n"
                            f"⏳ Temps restant : **{remaining_mn} min**"
                        ),
                        color=discord.Color.green()
                    )
                    await channel.send(embed=embed)
            except Exception as e:
                print(f"[regeneration_loop] Erreur: {e}")

async def auto_backup_loop():
    await bot.wait_until_ready()
    print("🔄 Boucle de backup auto indépendante démarrée")
    while not bot.is_closed():
        backup_auto_independante()
        await asyncio.sleep(3600)
        
def on_shutdown():
    print("💾 Sauvegarde finale avant extinction du bot...")
    sauvegarder()

async def wait_and_close_supply(guild_id, delay):
    await asyncio.sleep(delay)
    await close_special_supply(guild_id)

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

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
from data import charger, sauvegarder, virus_status, poison_status, infection_status, regeneration_status, shields, supply_data, backup_auto_independante, weekly_message_count, weekly_message_log
from utils import get_random_item, OBJETS, handle_death  
from storage import get_user_data, inventaire, hp, leaderboard
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
from item_list import register_item_command
from special_supply import update_last_active_channel, special_supply_loop, reset_supply_flags
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
from economy import add_gotcoins, gotcoins_balance, get_balance, compute_message_gains
from stats import register_stats_command
from bank import register_bank_command

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

gotcoins_cooldowns = {}
voice_state_start_times = {}  # {guild_id: {user_id: start_time}}
voice_tracking = {}

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
    register_stats_command(bot)
    register_bank_command(bot)
    
# ===================== Events ======================

@bot.event
async def on_ready():
    await bot.tree.sync(guild=discord.Object(id=1269384239254605856))
    print("🤖 Bot prêt. Synchronisation des commandes...")
    await reset_supply_flags(bot)

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
    voice_tracking_loop.start()
    cleanup_weekly_logs.start()

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    guild_id = str(message.guild.id)
    user_id = str(message.author.id)
    channel_id = message.channel.id
    
    weekly_message_log.setdefault(guild_id, {}).setdefault(user_id, [])
    weekly_message_log[guild_id][user_id].append(time.time())

    # Puis process les commandes si besoin
    await bot.process_commands(message)

    from special_supply import update_last_active_channel
    try:
        update_last_active_channel(message)
    except Exception as e:
        print(f"[on_message] Erreur update_last_active_channel : {e}")

    try:
        supply_data.setdefault(guild_id, {})
        supply_data[guild_id].setdefault("channel_activity_log", {})
        supply_data[guild_id]["channel_activity_log"][channel_id] = time.time()
        sauvegarder()
    except Exception as e:
        print(f"[on_message] Erreur update channel_activity_log : {e}")

    # 💰 Gains passifs (GotCoins) — avec cooldown et longueur minimum
    min_message_length = 20
    cooldown_seconds = 30
    now = time.time()

    if len(message.content.strip()) >= min_message_length:
        last_gain = gotcoins_cooldowns.get(user_id, 0)
        if now - last_gain >= cooldown_seconds:
            gain = compute_message_gains(message.content)
            if gain > 0:
                add_gotcoins(guild_id, user_id, gain, category="autre")

                gotcoins_cooldowns[user_id] = now  # Cooldown mis à jour uniquement si gain
                print(f"💰 Gain {gain} GotCoins pour {message.author.display_name} (via message)")

                # Si gain actif → on ne déclenche pas de ravitaillement aléatoire
                await bot.process_commands(message)
                return
    # Sinon, pas de gain ou pas de cooldown prêt → continue vers ravitaillement

    # 📦 Ravitaillement classique aléatoire
    global message_counter, random_threshold, last_drop_time
    
    message_counter += 1
    if message_counter < random_threshold:
        await bot.process_commands(message)
        return
    
    current_time = asyncio.get_event_loop().time()
    if current_time - last_drop_time < 30:
        await bot.process_commands(message)
        return
    
    last_drop_time = current_time
    message_counter = 0
    random_threshold = random.randint(4, 8)
    
    # --- Choisir l'item ---
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
    user_rewards = {}  # pour savoir ce que chaque user a eu
    
    while len(collected_users) < 3 and asyncio.get_event_loop().time() < end_time:
        try:
            reaction, user = await asyncio.wait_for(
                bot.wait_for("reaction_add", check=check),
                timeout=end_time - asyncio.get_event_loop().time(),
            )
            uid = str(user.id)
            collected_users.append(user)
    
            # Si c'est 💰 → on donne des GotCoins, pas d'item
            if item == "💰":
                gain = random.randint(3, 12)
                add_gotcoins(guild_id, uid, gain, category="autre")
                user_rewards[user] = f"💰 +{gain} GotCoins"
            else:
                # Objet classique → inventaire
                user_inv, _, _ = get_user_data(guild_id, uid)
                user_inv.append(item)
                user_rewards[user] = f"{item}"
    
        except asyncio.TimeoutError:
            break
    
    # --- Embed final
    if collected_users:
        lines = []
        for user in collected_users:
            reward_text = user_rewards.get(user, "❓")
            lines.append(f"✅ {user.mention} a récupéré : {reward_text}")
    
        embed = discord.Embed(
            title="📦 Ravitaillement récupéré",
            description="\n".join(lines),
            color=0x00FFAA
        )
    else:
        embed = discord.Embed(
            title="💥 Ravitaillement détruit",
            description=f"Le dépôt de **GotValis** contenant {item} s’est **auto-détruit**. 💣",
            color=0xFF0000
        )
    
    await message.channel.send(embed=embed)
    
    # Terminer avec process_commands
    await bot.process_commands(message)

# ===================== Auto-Update Leaderboard ======================

async def update_leaderboard_loop():
    await bot.wait_until_ready()
    
    while not bot.is_closed():
        print("⏳ [LOOP] Mise à jour des leaderboards spéciaux (GotCoins)...")

        for guild in bot.guilds:
            guild_id = str(guild.id)
            guild_config = get_guild_config(guild_id)

            channel_id = guild_config.get("special_leaderboard_channel_id")
            message_id = guild_config.get("special_leaderboard_message_id")

            print(f"🔍 [{guild.name}] Config : {guild_config}")
            print(f" → Channel ID : {channel_id} | Message ID : {message_id}")

            if not channel_id:
                print(f"⚠️ Aucun salon configuré pour {guild.name}")
                continue

            channel = bot.get_channel(channel_id)
            if not channel:
                print(f"❌ Salon introuvable : {channel_id}")
                continue

            medals = ["🥇", "🥈", "🥉"]
            server_balance = gotcoins_balance.get(guild_id, {})
            server_hp = hp.get(guild_id, {})
            server_shields = shields.get(guild_id, {})

            # Trié par argent pur
            sorted_lb = sorted(
                server_balance.items(),
                key=lambda x: x[1],
                reverse=True
            )

            lines = []
            rank = 0

            for uid, balance in sorted_lb:
                try:
                    int_uid = int(uid)
                    member = guild.get_member(int_uid)
                    if not member:
                        continue  # Si le membre n'est plus dans le serveur, on l'ignore
                except (ValueError, TypeError):
                    print(f"⚠️ UID non valide ignoré : {uid}")
                    continue

                if rank >= 10:
                    break

                pv = server_hp.get(uid, 100)
                pb = server_shields.get(uid, 0)

                prefix = medals[rank] if rank < len(medals) else f"{rank + 1}."

                # ✅ ligne simplifiée : toujours 💰 + ❤️, et on ajoute 🛡️ seulement si > 0
                line = (
                    f"{prefix} **{member.display_name}** → 💰 **{balance} GotCoins** | "
                    f"❤️ {pv} PV"
                )

                if pb > 0:
                    line += f" / 🛡️ {pb} PB"

                lines.append(line)
                rank += 1

            embed = discord.Embed(
                title="🏆 CLASSEMENT GOTVALIS — ÉDITION SPÉCIALE 🏆",
                description="\n".join(lines) if lines else "*Aucune donnée disponible.*",
                color=discord.Color.gold()
            )

            embed.set_footer(text="💰 Les GotCoins représentent votre richesse accumulée.")

            try:
                if message_id:
                    print(f"✏️ Modification du message {message_id} dans {channel.name}")
                    msg = await channel.fetch_message(message_id)
                    await msg.edit(content=None, embed=embed)
                else:
                    raise discord.NotFound(response=None, message="No message ID")
            except (discord.NotFound, discord.HTTPException) as e:
                print(f"📤 Envoi d’un nouveau message dans {channel.name} ({e})")
                try:
                    msg = await channel.send(embed=embed)
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
                
voice_tracking.setdefault(gid, {})

@tasks.loop(seconds=30)
async def voice_tracking_loop():
    await bot.wait_until_ready()
    print("🎙️ Boucle de suivi vocal démarrée.")

    while not bot.is_closed():
        for guild in bot.guilds:
            gid = str(guild.id)
            voice_tracking.setdefault(gid, {})

            # Récupère les membres actuellement en vocal (hors bots et AFK)
            active_user_ids = set()
            for vc in guild.voice_channels:
                if vc.id == guild.afk_channel.id if guild.afk_channel else False:
                    continue

                for member in vc.members:
                    if member.bot:
                        continue

                    uid = str(member.id)
                    active_user_ids.add(uid)
                    voice_tracking[gid].setdefault(uid, {
                        "start": time.time(),
                        "last_reward": time.time()
                    })

                    tracking = voice_tracking[gid][uid]
                    elapsed = time.time() - tracking["last_reward"]

                    # Ajoute +3 GotCoins toutes les 30 min
                    if elapsed >= 1800:
                        add_gotcoins(gid, uid, 3, category="autre")
                        tracking["last_reward"] = time.time()

                        # Ajoute 1800 sec dans les stats
                        weekly_voice_time.setdefault(gid, {}).setdefault(uid, 0)
                        weekly_voice_time[gid][uid] += 1800

                        print(f"🎙️ +3 GotCoins pour {member.display_name} (30 min atteinte)")

            # Nettoyage → membres qui ne sont plus en vocal
            tracked_user_ids = set(voice_tracking[gid].keys())
            for uid in tracked_user_ids - active_user_ids:
                tracking = voice_tracking[gid][uid]
                elapsed = time.time() - tracking["last_reward"]

                # On ajoute le temps restant (moins de 30 min restant) à weekly_voice_time
                if elapsed > 0:
                    weekly_voice_time.setdefault(gid, {}).setdefault(uid, 0)
                    weekly_voice_time[gid][uid] += int(elapsed)

                    print(f"🎙️ {uid} a quitté → +{int(elapsed)} sec ajoutés (partiel)")

                # On retire le user du tracking
                del voice_tracking[gid][uid]

        await asyncio.sleep(30)

@tasks.loop(hours=1)
async def cleanup_weekly_logs():
    print("🧹 Nettoyage des logs hebdomadaires...")
    now = time.time()
    seven_days_seconds = 7 * 24 * 3600

    # Messages
    for gid, users in weekly_message_log.items():
        for uid, timestamps in users.items():
            # Ne garder que les messages des 7 derniers jours
            users[uid] = [t for t in timestamps if now - t <= seven_days_seconds]
            
async def auto_backup_loop():
    await bot.wait_until_ready()
    print("🔄 Boucle de backup auto indépendante démarrée")
    while not bot.is_closed():
        backup_auto_independante()
        await asyncio.sleep(3600)
        
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

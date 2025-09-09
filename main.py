# main.py
import os
import sys
import time
import random
import atexit
import signal
import logging
import datetime
import asyncio

import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv

from config import load_config, get_config, get_guild_config, save_config
from data import (
    charger, sauvegarder,
    virus_status, poison_status, infection_status,
    regeneration_status, shields, supply_data,
    backup_auto_independante, weekly_message_count,
    weekly_message_log, malus_degat,
    zeyra_last_survive_time, valen_seuils, burn_status
)
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
from economy import add_gotcoins, gotcoins_balance, get_balance  # ⬅️ compute_message_gains retiré
from stats import register_stats_command
from bank import register_bank_command
from passifs import appliquer_passif
from shop import register_shop_commands
from perso import setup as setup_perso
from tirage import setup as setup_tirage  # ⬅️ on utilise setup(bot) fourni par tirage.py

# --------------------------------------------------------------------
# Variables globales utilisées dans les boucles / on_message
# --------------------------------------------------------------------
gotcoins_cooldowns = {}      # {user_id: last_gain_ts}
message_counter = 0
random_threshold = random.randint(4, 8)
last_drop_time = 0.0
voice_tracking = {}          # {guild_id: {user_id: {"start": ts, "last_reward": ts}}}

# --------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------
def compute_message_gains(content: str) -> int:
    """
    Calcul simple du gain GotCoins pour un message texte.
    Ajuste librement les paliers si tu veux.
    """
    length = len(content.strip())
    if length < 20:
        return 0
    if length < 60:
        return 1
    if length < 120:
        return 2
    if length < 240:
        return 3
    return 4

# --------------------------------------------------------------------
# Préparation & bot
# --------------------------------------------------------------------
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

# ===================== Slash Commands rapides ======================

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
    embed = await build_leaderboard_embed(bot, interaction.guild)
    await interaction.followup.send(embed=embed)

# ===================== Commands texte utilitaires ===================

@bot.command()
async def check_persistent(ctx):
    files = os.listdir("/persistent")
    await ctx.send(f"Contenu de `/persistent` :\n" + "\n".join(files) if files else "📂 Aucun fichier trouvé.")

@bot.command()
async def sync(ctx):
    await bot.tree.sync(guild=ctx.guild)
    await ctx.send("✅ Commandes slash resynchronisées avec succès.")

# ===================== Enregistrement central ======================

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
    register_shop_commands(bot)
    # ⬇️ tirage: on ajoute le COG via setup_tirage dans main() (asynchrone)

# ===================== Entrée principale ===========================

async def main():
    register_all_commands(bot)
    await setup_perso(bot)
    await setup_tirage(bot)  # ⬅️ enregistre le Cog Tirage
    await bot.start(os.getenv("DISCORD_TOKEN"))

if __name__ == "__main__":
    asyncio.run(main())

# ===================== Events ======================

@bot.event
async def on_ready():
    await bot.tree.sync(guild=discord.Object(id=1269384239254605856))
    print("🤖 Bot prêt. Synchronisation des commandes...")
    await reset_supply_flags(bot)

    # Enregistrement des commandes (sécurité)
    register_all_commands(bot)

    # Synchronisation globale
    try:
        await bot.tree.sync()
        print("✅ Commandes slash synchronisées globalement.")
    except Exception as e:
        print(f"❌ Erreur de synchronisation globale : {e}")

    # Chargement des données
    charger()
    load_config()

    # Boucles de statut & ravitaillement
    asyncio.create_task(special_supply_loop(bot))
    virus_damage_loop.start()
    poison_damage_loop.start()
    infection_damage_loop.start()

    # Présence du bot
    activity = discord.Activity(type=discord.ActivityType.watching, name="en /help | https://discord.gg/jkbfFRqzZP")
    await bot.change_presence(status=discord.Status.online, activity=activity)

    print(f"✅ GotValis Bot prêt. Connecté en tant que {bot.user}")
    print("🔧 Commandes slash enregistrées :")
    for command in bot.tree.get_commands():
        print(f" - /{command.name}")

    # Boucles principales
    update_leaderboard_loop.start()
    yearly_reset_loop.start()
    autosave_data_loop.start()
    daily_restart_loop.start()
    auto_backup_loop.start()
    regeneration_loop.start()
    voice_tracking_loop.start()
    cleanup_weekly_logs.start()
    burn_damage_loop.start()

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    guild_id = str(message.guild.id)
    user_id = str(message.author.id)
    channel_id = message.channel.id

    weekly_message_log.setdefault(guild_id, {}).setdefault(user_id, [])
    weekly_message_log[guild_id][user_id].append(time.time())

    await bot.process_commands(message)

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
                # Ne pas déclencher de drop si gain actif
                await bot.process_commands(message)
                return

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
    user_rewards = {}

    while len(collected_users) < 3 and asyncio.get_event_loop().time() < end_time:
        try:
            reaction, user = await asyncio.wait_for(
                bot.wait_for("reaction_add", check=check),
                timeout=end_time - asyncio.get_event_loop().time(),
            )
            uid = str(user.id)
            collected_users.append(user)

            if item == "💰":
                gain = random.randint(3, 12)
                add_gotcoins(guild_id, uid, gain, category="autre")
                user_rewards[user] = f"💰 +{gain} GotCoins"
            else:
                user_inv, _, _ = get_user_data(guild_id, uid)
                user_inv.append(item)
                user_rewards[user] = f"{item}"

        except asyncio.TimeoutError:
            break

    if collected_users:
        lines = [f"✅ {u.mention} a récupéré : {user_rewards.get(u, '❓')}" for u in collected_users]
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
    await bot.process_commands(message)

# ===================== Loops ======================

@tasks.loop(seconds=60)
async def update_leaderboard_loop():
    await bot.wait_until_ready()
    print("⏳ [LOOP] Mise à jour des leaderboards spéciaux (GotCoins)...")

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
        server_balance = gotcoins_balance.get(guild_id, {})
        server_hp = hp.get(guild_id, {})
        server_shields = shields.get(guild_id, {})

        sorted_lb = sorted(server_balance.items(), key=lambda x: x[1], reverse=True)

        lines, rank = [], 0
        for uid, balance in sorted_lb:
            try:
                member = guild.get_member(int(uid))
                if not member:
                    continue
            except Exception:
                continue

            if rank >= 10:
                break

            pv = server_hp.get(uid, 100)
            pb = server_shields.get(uid, 0)
            prefix = medals[rank] if rank < len(medals) else f"{rank + 1}."
            line = f"{prefix} **{member.display_name}** → 💰 **{balance} GotCoins** | ❤️ {pv} PV"
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
                msg = await channel.fetch_message(message_id)
                await msg.edit(content=None, embed=embed)
            else:
                raise discord.NotFound(response=None, message="No message ID")
        except (discord.NotFound, discord.HTTPException):
            try:
                msg = await channel.send(embed=embed)
                guild_config["special_leaderboard_message_id"] = msg.id
                save_config()
            except Exception as e:
                print(f"❌ Échec de l’envoi du message dans {channel.name} : {e}")

@tasks.loop(seconds=30)
async def yearly_reset_loop():
    await bot.wait_until_ready()
    now = datetime.datetime.utcnow()
    if now.month == 12 and now.day == 31 and now.hour == 23 and now.minute == 59:
        from data import sauvegarder as data_save
        # reset
        for gid in list(inventaire.keys()):
            inventaire[gid] = {}
        for gid in list(hp.keys()):
            hp[gid] = {}
        for gid in list(leaderboard.keys()):
            leaderboard[gid] = {}
        data_save()
        print("🎉 Réinitialisation annuelle effectuée pour tous les serveurs.")
        # annonce
        config = get_config()
        announcement_msg = "🎊 Les statistiques ont été remises à zéro pour la nouvelle année ! Merci pour votre participation à GotValis."
        for server_id, server_conf in config.items():
            ch_id = server_conf.get("leaderboard_channel_id")
            if not ch_id:
                continue
            channel = bot.get_channel(ch_id)
            if channel:
                await channel.send(announcement_msg)

@tasks.loop(seconds=300)
async def autosave_data_loop():
    await bot.wait_until_ready()
    sauvegarder()

@tasks.loop(seconds=30)
async def daily_restart_loop():
    await bot.wait_until_ready()
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
            if elapsed >= duration or now < next_tick:
                if elapsed >= duration:
                    del virus_status[gid][uid]
                continue

            # purge éventuelle
            purge_result = appliquer_passif("purge_auto", {"guild_id": gid, "user_id": uid, "last_timestamp": start})
            if purge_result and purge_result.get("purger_statut"):
                del virus_status[gid][uid]
                continue

            virus_status[gid][uid]["next_tick"] = now + 3600
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
                    if lost_pb and real_dmg == 0:
                        desc = f"🦠 {member.mention} subit **{lost_pb} dégâts** *(Virus)*.\n🛡️ {pb_before} - {lost_pb} PB = ❤️ {hp_after} PV / 🛡️ {pb_after} PB"
                    elif lost_pb and real_dmg > 0:
                        desc = f"🦠 {member.mention} subit **{lost_pb + real_dmg} dégâts** *(Virus)*.\n❤️ {hp_before} - {real_dmg} PV / 🛡️ {pb_before} - {lost_pb} PB = ❤️ {hp_after} PV / 🛡️ {pb_after} PB"
                    else:
                        desc = f"🦠 {member.mention} subit **{real_dmg} dégâts** *(Virus)*.\n❤️ {hp_before} - {real_dmg} PV = {hp_after} PV"
                    desc += f"\n⏳ Temps restant : **{remaining_min} min**"
                    embed = discord.Embed(description=desc, color=discord.Color.dark_purple())
                    await channel.send(embed=embed)
                    if shield_broken:
                        await channel.send(embed=discord.Embed(
                            title="🛡 Bouclier détruit",
                            description=f"Le bouclier de {member.mention} a été **détruit** par le virus.",
                            color=discord.Color.dark_blue()
                        ))
                    if hp_after == 0:
                        handle_death(gid, uid, source_id)
                        await channel.send(embed=discord.Embed(
                            title="💀 KO viral détecté",
                            description=(f"**GotValis** détecte une chute à 0 PV pour {member.mention}.\n"
                                         f"🦠 Effondrement dû à une **charge virale critique**.\n"
                                         f"🔄 {member.mention} est **stabilisé à 100 PV**."),
                            color=0x8800FF
                        ))
            except Exception as e:
                print(f"[virus_damage_loop] Erreur d’envoi embed : {e}")

@tasks.loop(seconds=30)
async def poison_damage_loop():
    await bot.wait_until_ready()
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
            if elapsed >= duration or now < next_tick:
                if elapsed >= duration:
                    del poison_status[gid][uid]
                continue

            purge_result = appliquer_passif("purge_auto", {"guild_id": gid, "user_id": uid, "last_timestamp": start})
            if purge_result and purge_result.get("purger_statut"):
                del poison_status[gid][uid]
                continue

            poison_status[gid][uid]["next_tick"] = now + 1800
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
            if uid != source_id:
                leaderboard.setdefault(gid, {}).setdefault(source_id, {"degats": 0, "soin": 0, "kills": 0, "morts": 0})
                leaderboard[gid][source_id]["degats"] += real_dmg

            remaining = max(0, duration - elapsed)
            remaining_min = int(remaining // 60)
            try:
                channel = bot.get_channel(channel_id)
                if channel:
                    member = await bot.fetch_user(int(uid))
                    if lost_pb and real_dmg == 0:
                        desc = f"🧪 {member.mention} subit **{lost_pb} dégâts** *(Poison)*.\n🛡️ {pb_before} - {lost_pb} PB = ❤️ {after} PV / 🛡️ {pb_after} PB"
                    elif lost_pb and real_dmg > 0:
                        desc = f"🧪 {member.mention} subit **{lost_pb + real_dmg} dégâts** *(Poison)*.\n❤️ {before} - {real_dmg} PV / 🛡️ {pb_before} - {lost_pb} PB = ❤️ {after} PV / 🛡️ {pb_after} PB"
                    else:
                        desc = f"🧪 {member.mention} subit **{real_dmg} dégâts** *(Poison)*.\n❤️ {before} - {real_dmg} PV = {after} PV"
                    desc += f"\n⏳ Temps restant : **{remaining_min} min**"
                    embed = discord.Embed(description=desc, color=discord.Color.dark_green())
                    await channel.send(embed=embed)
                    if shield_broken:
                        await channel.send(embed=discord.Embed(
                            title="🛡 Bouclier détruit",
                            description=f"Le bouclier de {member.mention} a été **détruit** sous l'effet du poison.",
                            color=discord.Color.dark_blue()
                        ))
                    if after == 0:
                        handle_death(gid, uid, source_id)
                        await channel.send(embed=discord.Embed(
                            title="💀 KO toxique détecté",
                            description=(f"**GotValis** détecte une chute à 0 PV pour {member.mention}.\n"
                                         f"🧪 Effondrement dû à une **intoxication sévère**.\n"
                                         f"🔄 {member.mention} est **stabilisé à 100 PV**."),
                            color=0x006600
                        ))
            except Exception as e:
                print(f"[poison_damage_loop] Erreur d’envoi embed : {e}")

@tasks.loop(seconds=30)
async def infection_damage_loop():
    await bot.wait_until_ready()
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

            if now - start >= duration:
                del infection_status[gid][uid]
                continue
            if now < next_tick:
                continue

            purge_result = appliquer_passif("purge_auto", {"guild_id": gid, "user_id": uid, "last_timestamp": start})
            if purge_result and purge_result.get("purger_statut"):
                del infection_status[gid][uid]
                continue

            passif_result = appliquer_passif(uid, "tick_infection", {"guild_id": gid, "user_id": uid, "cible_id": uid})
            if passif_result and passif_result.get("ignore_infection_damage"):
                continue

            infection_status[gid][uid]["next_tick"] = now + 1800

            dmg = 2
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

            remaining = max(0, duration - (now - start))
            remaining_min = int(remaining // 60)
            try:
                channel = bot.get_channel(channel_id)
                if channel:
                    member = await bot.fetch_user(int(uid))
                    if lost_pb and real_dmg == 0:
                        desc = f"🧟 {member.mention} subit **{lost_pb} dégâts** *(Infection)*.\n🛡️ {pb_before} - {lost_pb} PB = ❤️ {hp_after} PV / 🛡️ {pb_after} PB"
                    elif lost_pb and real_dmg > 0:
                        desc = f"🧟 {member.mention} subit **{lost_pb + real_dmg} dégâts** *(Infection)*.\n❤️ {hp_before} - {real_dmg} PV / 🛡️ {pb_before} - {lost_pb} PB = ❤️ {hp_after} PV / 🛡️ {pb_after} PB"
                    else:
                        desc = f"🧟 {member.mention} subit **{real_dmg} dégâts** *(Infection)*.\n❤️ {hp_before} - {real_dmg} PV = {hp_after} PV"
                    desc += f"\n⏳ Temps restant : **{remaining_min} min**"
                    embed = discord.Embed(description=desc, color=discord.Color.dark_green())
                    await channel.send(embed=embed)
                    if shield_broken:
                        await channel.send(embed=discord.Embed(
                            title="🛡 Bouclier détruit",
                            description=f"Le bouclier de {member.mention} a été **détruit** par l'infection.",
                            color=discord.Color.dark_blue()
                        ))
                    if hp_after == 0:
                        handle_death(gid, uid, source_id)
                        await channel.send(embed=discord.Embed(
                            title="💀 KO infectieux détecté",
                            description=(f"**GotValis** détecte une chute à 0 PV pour {member.mention}.\n"
                                         f"🧟 Effondrement dû à une infection invasive.\n"
                                         f"🔄 Le patient est stabilisé à **100 PV**."),
                            color=0x880088
                        ))
            except Exception as e:
                print(f"[infection_damage_loop] Erreur d’envoi embed : {e}")

@tasks.loop(seconds=30)
async def regeneration_loop():
    await bot.wait_until_ready()
    now = time.time()
    for guild_id, users in list(regeneration_status.items()):
        for user_id, stat in list(users.items()):
            if now - stat["start"] > stat["duration"]:
                del regeneration_status[guild_id][user_id]
                continue
            if now < stat.get("next_tick", 0):
                continue
            stat["next_tick"] = now + 1800
            hp.setdefault(guild_id, {})
            before = hp[guild_id].get(user_id, 100)
            healed = min(3, 100 - before)
            after = min(before + healed, 100)
            hp[guild_id][user_id] = after

            if "source" in stat and stat["source"]:
                leaderboard.setdefault(guild_id, {})
                leaderboard[guild_id].setdefault(stat["source"], {"degats": 0, "soin": 0, "kills": 0, "morts": 0})
                leaderboard[guild_id][stat["source"]]["soin"] += healed

            elapsed = now - stat["start"]
            remaining = max(0, stat["duration"] - elapsed)
            remaining_mn = int(remaining // 60)

            try:
                channel = bot.get_channel(stat.get("channel_id", 0))
                if channel:
                    member = await bot.fetch_user(int(user_id))
                    embed = discord.Embed(
                        description=(f"💕 {member.mention} récupère **{healed} PV** *(Régénération)*.\n"
                                     f"❤️ {before} PV + {

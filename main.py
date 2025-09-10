# main.py
import os
import sys
import time
import random
import atexit
import signal
import datetime
import asyncio
import re

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
from status import register_status_command
from box import register_box_command
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
from economy import add_gotcoins, gotcoins_balance, get_balance
from stats import register_stats_command
from bank import register_bank_command
# ✅ nouvelle API passifs
from passifs import appliquer_passif_utilisateur as appliquer_passif
from shop import register_shop_commands
from perso import setup as setup_perso
from tirage import setup as setup_tirage
from chat_ai import register_chat_ai_command, generate_oracle_reply

# --------------------------------------------------------------------
# Variables globales
# --------------------------------------------------------------------
gotcoins_cooldowns = {}      # {user_id: last_gain_ts}
message_counter = 0
random_threshold = random.randint(4, 8)
last_drop_time = 0.0
voice_tracking = {}          # {guild_id: {user_id: {"start": ts, "last_reward": ts}}}

# Garde-fou pour éviter le double enregistrement des commandes
_commands_registered = False

# Cooldown anti-spam pour les réponses IA
ai_reply_cooldowns = {}      # {user_id: last_ai_ts}
AI_COOLDOWN_SECONDS = 15

# --------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------
def compute_message_gains(content: str) -> int:
    """Calcul simple du gain GotCoins pour un message texte."""
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

# --- Détection troll simple (heuristique locale) ----------
INSULTES_FR = {
    "fdp","enculé","pute","tg","ta gueule","connard","conne","boloss","bouffon","batard","merdeux",
    "merde","cassos","abruti","sale","clochard","débile","tarlouze","pd"
}

def detect_troll(text: str) -> tuple[str, str | None]:
    """
    Retourne ("threat","raison") si troll probable, sinon ("normal", None).
    Heuristique: insultes, excès de MAJ, spam, provoc courte.
    """
    t = text.strip()
    t_lower = t.lower()

    for w in INSULTES_FR:
        if w in t_lower:
            return "threat", f"insulte détectée: '{w}'"

    letters = re.findall(r"[A-Za-z]", t)
    if letters:
        cap_ratio = sum(1 for c in letters if c.isupper()) / max(1, len(letters))
        if cap_ratio >= 0.7 and len(letters) >= 8:
            return "threat", f"taux de MAJ élevé ({int(cap_ratio*100)}%)"

    if re.search(r"([!?*]{4,}|([A-Za-z]{2,})\2{2,})", t):
        return "threat", "répétitions/spam"

    if len(t) <= 10 and re.search(r"\b(tg|mdr|nul|ta.*gueule|1v1|ffa)\b", t_lower):
        return "threat", "provocation courte"

    return "normal", None

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
    # (pas de profile ici — ton fichier 'profile.py' est en réalité un tirage)
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
    register_chat_ai_command(bot)   # /ask
    # tirage via setup_tirage dans main()

def register_all_commands_once(bot):
    global _commands_registered
    if _commands_registered:
        print("↩️ Commands déjà enregistrées, on saute.")
        return
    register_all_commands(bot)
    _commands_registered = True

# ===================== Entrée principale ===========================

async def main():
    register_all_commands_once(bot)
    await setup_perso(bot)
    await setup_tirage(bot)  # enregistre le Cog Tirage
    await bot.start(os.getenv("DISCORD_TOKEN"))

if __name__ == "__main__":
    asyncio.run(main())

# ===================== Events ======================

@bot.event
async def on_ready():
    # Sync ciblée (facultatif si tu gardes la globale)
    try:
        await bot.tree.sync(guild=discord.Object(id=1269384239254605856))
    except Exception as e:
        print(f"⚠️ Sync ciblée échouée : {e}")

    print("🤖 Bot prêt. Synchronisation des commandes...")
    await reset_supply_flags(bot)

    # Évite le double enregistrement si on_ready est rappelé
    register_all_commands_once(bot)

    # Synchronisation globale
    try:
        await bot.tree.sync()
        print("✅ Commandes slash synchronisées globalement.")
    except Exception as e:
        print(f"❌ Erreur de synchronisation globale : {e}")

    # Chargement des données
    charger()
    load_config()

    # Boucle de ravitaillement (fonction asynchrone, pas tasks.loop)
    asyncio.create_task(special_supply_loop(bot))

    # Démarrer les loops SI PAS déjà en cours (évite doublons lors de reconnexion)
    if not virus_damage_loop.is_running():
        virus_damage_loop.start()
    if not poison_damage_loop.is_running():
        poison_damage_loop.start()
    if not infection_damage_loop.is_running():
        infection_damage_loop.start()
    if not update_leaderboard_loop.is_running():
        update_leaderboard_loop.start()
    if not autosave_data_loop.is_running():
        autosave_data_loop.start()
    if not daily_restart_loop.is_running():
        daily_restart_loop.start()
    if not auto_backup_loop.is_running():
        auto_backup_loop.start()
    if not regeneration_loop.is_running():
        regeneration_loop.start()
    if not voice_tracking_loop.is_running():
        voice_tracking_loop.start()
    if not cleanup_weekly_logs.is_running():
        cleanup_weekly_logs.start()
    if not burn_damage_loop.is_running():
        burn_damage_loop.start()

    # Présence du bot
    activity = discord.Activity(type=discord.ActivityType.watching, name="en /help | https://discord.gg/jkbfFRqzZP")
    await bot.change_presence(status=discord.Status.online, activity=activity)

    print(f"✅ GotValis Bot prêt. Connecté en tant que {bot.user}")
    print("🔧 Commandes slash enregistrées :")
    for command in bot.tree.get_commands():
        print(f" - /{command.name}")

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    guild = message.guild
    if not guild:
        # Laisser la logique IA au Cog chat_ai pour les DMs si nécessaire
        await bot.process_commands(message)
        return

    guild_id = str(guild.id)
    user_id = str(message.author.id)
    channel_id = message.channel.id

    weekly_message_log.setdefault(guild_id, {}).setdefault(user_id, [])
    weekly_message_log[guild_id][user_id].append(time.time())

    # --- IA GotValis: mention du bot ou réponse à un message du bot ---
    try:
        triggered = False

        # 1) Mention directe du bot
        if bot.user in message.mentions:
            triggered = True

        # 2) Réponse à un message du bot
        if not triggered and message.reference and message.reference.resolved:
            try:
                ref_msg = message.reference.resolved
                if ref_msg.author and ref_msg.author.id == bot.user.id:
                    triggered = True
            except Exception:
                pass

        if triggered:
            # Anti-spam par utilisateur
            last = ai_reply_cooldowns.get(user_id, 0)
            now_ts = time.time()
            if now_ts - last >= AI_COOLDOWN_SECONDS:
                ai_reply_cooldowns[user_id] = now_ts

                # Nettoie la mention dans le prompt
                prompt = (message.content
                          .replace(f"<@{bot.user.id}>", "")
                          .replace(f"<@!{bot.user.id}>", "")
                          ).strip()
                if not prompt:
                    prompt = "Énonce un bref communiqué RP GotValis™ sur l’optimisation du bonheur collectif."

                tone, reason = detect_troll(prompt)

                async with message.channel.typing():
                    try:
                        reply = await generate_oracle_reply(
                            guild.name,
                            prompt,
                            tone=("threat" if tone == "threat" else "normal"),
                            reason=reason
                        )
                    except Exception as e:
                        reply = f"⚠️ Module Oracle indisponible. Code: `{e}`"

                header = "📡 **COMMUNIQUÉ GOTVALIS™** 📡" if tone == "normal" else "⚠️ **AVIS DE CONFORMITÉ GOTVALIS™** ⚠️"
                await message.reply(f"{header}\n{reply}")
            # Ne pas retourner ici : on laisse vivre les drops/gains si besoin
    except Exception as e:
        print(f"[AI mention handler] Erreur: {e}")

    # Puis process les commandes si besoin
    await bot.process_commands(message)

    # --- Traçage d'activité de salon ---
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
                gotcoins_cooldowns[user_id] = now
                # Pas de drop si gain actif
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

            # ✅ nouvelle API
            purge_result = appliquer_passif(gid, uid, "purge_auto", {"last_timestamp": start})
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

            # ✅ nouvelle API
            purge_result = appliquer_passif(gid, uid, "purge_auto", {"last_timestamp": start})
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

            # ✅ purge auto (nouvelle API)
            purge_result = appliquer_passif(gid, uid, "purge_auto", {"last_timestamp": start})
            if purge_result and purge_result.get("purger_statut"):
                del infection_status[gid][uid]
                continue

            # ✅ tick_infection : certains persos annulent les dégâts
            passif_result = appliquer_passif(gid, uid, "tick_infection", {"cible_id": uid})
            if passif_result and passif_result.get("annuler_degats"):
                infection_status[gid][uid]["next_tick"] = now + 1800
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
                                     f"❤️ {before} PV + {healed} PV = {after} PV\n"
                                     f"⏳ Temps restant : **{remaining_mn} min**"),
                        color=discord.Color.green()
                    )
                    await channel.send(embed=embed)
            except Exception as e:
                print(f"[regeneration_loop] Erreur: {e}")

@tasks.loop(seconds=30)
async def voice_tracking_loop():
    await bot.wait_until_ready()
    from data import weekly_voice_time
    for guild in bot.guilds:
        gid = str(guild.id)
        voice_tracking.setdefault(gid, {})
        active_user_ids = set()
        for vc in guild.voice_channels:
            if guild.afk_channel and vc.id == guild.afk_channel.id:
                continue
            for member in vc.members:
                if member.bot:
                    continue
                uid = str(member.id)
                active_user_ids.add(uid)
                voice_tracking[gid].setdefault(uid, {"start": time.time(), "last_reward": time.time()})
                tracking = voice_tracking[gid][uid]
                elapsed = time.time() - tracking["last_reward"]
                if elapsed >= 1800:
                    add_gotcoins(gid, uid, 3, category="autre")
                    tracking["last_reward"] = time.time()
                    weekly_voice_time.setdefault(gid, {}).setdefault(uid, 0)
                    weekly_voice_time[gid][uid] += 1800
        tracked_user_ids = set(voice_tracking[gid].keys())
        for uid in tracked_user_ids - active_user_ids:
            tracking = voice_tracking[gid][uid]
            elapsed = time.time() - tracking["last_reward"]
            if elapsed > 0:
                weekly_voice_time.setdefault(gid, {}).setdefault(uid, 0)
                weekly_voice_time[gid][uid] += int(elapsed)
                sauvegarder()
            del voice_tracking[gid][uid]

@tasks.loop(seconds=30)
async def burn_damage_loop():
    await bot.wait_until_ready()
    now = time.time()
    for guild in bot.guilds:
        gid = str(guild.id)
        if gid not in burn_status:
            continue
        for uid, status in list(burn_status[gid].items()):
            if not status.get("actif") or now < status.get("next_tick", 0):
                continue
            # ✅ purge auto (nouvelle API)
            purge_result = appliquer_passif(gid, uid, "purge_auto", {"last_timestamp": status["start"]})
            if purge_result and purge_result.get("purger_statut"):
                del burn_status[gid][uid]
                continue

            status["ticks_restants"] -= 1
            status["next_tick"] = now + 3600
            if status["ticks_restants"] <= 0:
                del burn_status[gid][uid]
                continue

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
            source_id = status.get("source")

            if uid != source_id and source_id:
                leaderboard.setdefault(gid, {}).setdefault(source_id, {"degats": 0, "soin": 0, "kills": 0, "morts": 0})
                leaderboard[gid][source_id]["degats"] += real_dmg

            try:
                channel = bot.get_channel(status["channel_id"])
                if not channel:
                    continue
                member = await bot.fetch_user(int(uid))
                desc = (
                    f"🔥 {member.mention} subit **{real_dmg + lost_pb} dégâts** *(Brûlure)*.\n"
                    f"❤️ {hp_before} - {real_dmg} PV / 🛡️ {pb_before} - {lost_pb} PB = ❤️ {hp_after} PV / 🛡️ {pb_after} PB\n"
                    f"⏳ Brûlure restante : **{status['ticks_restants']}h**"
                )
                embed = discord.Embed(description=desc, color=discord.Color.orange())
                await channel.send(embed=embed)
                if shield_broken:
                    await channel.send(embed=discord.Embed(
                        title="🛡 Bouclier détruit",
                        description=f"Le bouclier de {member.mention} a été **détruit** par la brûlure.",
                        color=discord.Color.dark_blue()
                    ))
                if hp_after == 0:
                    handle_death(gid, uid, source_id)
                    await channel.send(embed=discord.Embed(
                        title="💀 KO par brûlure",
                        description=(f"{member.mention} a succombé à une **brûlure sévère**.\n"
                                     "🔄 Stabilisé à **100 PV**."),
                        color=0xFF5500
                    ))
            except Exception as e:
                print(f"[burn_damage_loop] Erreur : {e}")

@tasks.loop(hours=1)
async def cleanup_weekly_logs():
    print("🧹 Nettoyage des logs hebdomadaires...")
    now = time.time()
    seven_days_seconds = 7 * 24 * 3600
    for gid, users in weekly_message_log.items():
        for uid, timestamps in users.items():
            users[uid] = [t for t in timestamps if now - t <= seven_days_seconds]

@tasks.loop(hours=1)
async def auto_backup_loop():
    await bot.wait_until_ready()
    print("🔄 Boucle de backup auto indépendante démarrée")
    backup_auto_independante()

# ===================== Shutdown hooks ======================

def on_shutdown():
    print("💾 Sauvegarde finale avant extinction du bot...")
    sauvegarder()

atexit.register(on_shutdown)

def handle_signal(sig, frame):
    on_shutdown()
    sys.exit(0)

signal.signal(signal.SIGINT, handle_signal)
signal.signal(signal.SIGTERM, handle_signal)
# ===================== Run (dans main()) ====================

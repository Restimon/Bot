import discord
import random
import time
import asyncio
import datetime

from data import virus_status, poison_status, infection_status, regeneration_status, supply_data, sauvegarder
from storage import get_user_data, hp
from utils import get_random_item, OBJETS

# ========================== Mise à jour du salon actif ==========================

def update_last_active_channel(message):
    if message.author.bot:
        return

    guild_id = str(message.guild.id)

    if guild_id not in supply_data or not isinstance(supply_data[guild_id], dict):
        supply_data[guild_id] = {}

    supply_data[guild_id]["last_channel_id"] = message.channel.id
    supply_data[guild_id]["last_activity_time"] = time.time()

    # On garde un log des salons actifs
    supply_data[guild_id].setdefault("channel_activity_log", {})
    supply_data[guild_id]["channel_activity_log"][message.channel.id] = time.time()

    sauvegarder()

# ========================== Recherche de salon compatible ==========================

def find_or_update_valid_channel(bot, guild, config):
    last_id = config.get("last_channel_id")
    if last_id:
        ch = bot.get_channel(last_id)
        if ch:
            perms = ch.permissions_for(guild.me)
            if perms.send_messages and perms.add_reactions and perms.read_messages:
                return ch

    activity_log = config.get("channel_activity_log", {})
    sorted_channels = sorted(activity_log.items(), key=lambda x: x[1], reverse=True)

    for ch_id, _ in sorted_channels:
        ch = bot.get_channel(ch_id)
        if ch:
            perms = ch.permissions_for(guild.me)
            if perms.send_messages and perms.add_reactions and perms.read_messages:
                config["last_channel_id"] = ch.id
                sauvegarder()
                return ch

    for ch in guild.text_channels:
        perms = ch.permissions_for(guild.me)
        if perms.send_messages and perms.add_reactions and perms.read_messages:
            config["last_channel_id"] = ch.id
            sauvegarder()
            return ch

    return None

# ========================== Génération des récompenses ==========================

def describe_item(emoji):
    obj = OBJETS.get(emoji, {})
    t = obj.get("type")
    if t == "attaque":
        return f"🗡️ Inflige {obj['degats']} dégâts. (Crit {int(obj.get('crit', 0) * 100)}%)"
    if t == "virus":
        return "🦠 5 dégâts initiaux + 5/h pendant 6h."
    if t == "poison":
        return "🧪 3 dégâts initiaux + 3/30min pendant 3h."
    if t == "infection":
        return "🧟 5 dégâts initiaux + 2/30min pendant 3h (25% de propagation)."
    if t == "soin":
        return f"💚 Restaure {obj['soin']} PV. (Crit {int(obj.get('crit', 0) * 100)}%)"
    if t == "regen":
        return "✨ Régénère 3 PV toutes les 30min pendant 3h."
    if t == "mysterybox":
        return "📦 Boîte surprise : objets aléatoires."
    if t == "vol":
        return "🔍 Vole un objet à un autre joueur."
    if t == "vaccin":
        return "💉 Soigne le virus via /heal."
    if t == "bouclier":
        return "🛡 +20 points de bouclier."
    if t == "esquive+":
        return "👟 Augmente les chances d’esquive pendant 3h."
    if t == "reduction":
        return "🪖 Réduction de dégâts x0.5 pendant 4h."
    if t == "immunite":
        return "⭐️ Immunité totale pendant 2h."
    return "❓ Effet inconnu."

def choose_reward(user_id, guild_id):
    r = random.random()
    if r < 0.60:
        return "objet", get_random_item()
    elif r < 0.70:
        return "status", random.choice(["virus", "poison", "infection"])
    elif r < 0.80:
        return "degats", random.randint(1, 15)
    elif r < 0.95:
        return "soin", random.randint(1, 10)
    else:
        return "regen", True

async def reset_supply_flags(bot):
    print("🔄 Reset automatique des flags supply + vérification des messages.")

    for guild in bot.guilds:
        gid = str(guild.id)
        config = supply_data.setdefault(gid, {})
        active_msg_id = config.get("active_supply_id")
        last_channel_id = config.get("last_channel_id")
        is_open = config.get("is_open", False)

        if active_msg_id and last_channel_id:
            try:
                channel = bot.get_channel(last_channel_id)
                if not channel:
                    print(f"❌ [Guild {guild.name}] Salon {last_channel_id} introuvable.")
                    continue

                msg = await channel.fetch_message(int(active_msg_id))
                now = datetime.datetime.utcnow()

                # Vérifie que le message est bien un supply et récent (< 5 min)
                if (
                    msg.author == bot.user
                    and msg.embeds
                    and "Ravitaillement spécial GotValis" in msg.embeds[0].title
                ):
                    message_age_sec = (now - msg.created_at.replace(tzinfo=None)).total_seconds()
                    if message_age_sec <= 300:
                        print(f"🗑️ Suppression du message supply récent ({int(message_age_sec)}s) dans {guild.name}.")
                        await msg.delete()
                        config["active_supply_id"] = None
                        config["is_open"] = False
                        sauvegarder()
                    else:
                        print(f"⏳ Message supply trop ancien ({int(message_age_sec)}s), pas supprimé.")

                else:
                    print(f"⏭️ Message {active_msg_id} ignoré (pas un supply valide).")

            except discord.NotFound:
                print(f"⚠️ Message supply {active_msg_id} introuvable (probablement déjà supprimé).")
                config["active_supply_id"] = None
                config["is_open"] = False
                sauvegarder()

            except Exception as e:
                print(f"❌ Erreur reset supply dans {guild.name} : {e}")

        else:
            # Pas de message actif → juste reset au cas où
            config["active_supply_id"] = None
            config["is_open"] = False
            sauvegarder()

    print("✅ Reset supply terminé.")

# ========================== Envoi du supply ==========================

async def send_special_supply_in_channel(bot, guild, channel):
    now = time.time()
    gid = str(guild.id)

    embed = discord.Embed(
        title="📦 Ravitaillement spécial GotValis",
        description="Réagissez avec 📦 pour récupérer une récompense surprise !\n⏳ Disponible pendant 5 minutes, maximum 5 personnes.",
        color=discord.Color.gold()
    )
    msg = await channel.send(embed=embed)
    await msg.add_reaction("📦")

    collected_users = []
    supply_data[gid]["active_supply_id"] = str(msg.id)
    supply_data[gid]["is_open"] = True
    supply_data[gid]["collected_users"] = []
    sauvegarder()

    def check(reaction, user):
        return (
            reaction.message.id == msg.id
            and str(reaction.emoji) == "📦"
            and not user.bot
            and user.id not in [u.id for u in collected_users]
        )

    end = time.time() + 300
    while len(collected_users) < 5 and time.time() < end:
        try:
            reaction, user = await asyncio.wait_for(
                bot.wait_for("reaction_add", check=check),
                timeout=end - time.time(),
            )
            collected_users.append(user)
        except asyncio.TimeoutError:
            break

    results = []
    for user in collected_users:
        uid = str(user.id)
        reward_type, reward = choose_reward(uid, gid)

        if reward_type == "objet":
            inv, _, _ = get_user_data(gid, uid)
            inv.append(reward)
            results.append(f"🎁 {user.mention} a obtenu **{reward}** — {describe_item(reward)}")

        elif reward_type == "status":
            status_map = {
                "virus": (virus_status, "🦠", "infecté par un virus", 6 * 3600),
                "poison": (poison_status, "🧪", "empoisonné", 3 * 3600),
                "infection": (infection_status, "🧟", "infecté", 3 * 3600)
            }
            dico, emoji, label, duration = status_map[reward]

            start_now = time.time()
            dico.setdefault(gid, {})[uid] = {
                "start": start_now,
                "duration": duration,
                "last_tick": 0,
                "source": None,
                "channel_id": channel.id
            }
            results.append(f"{emoji} {user.mention} a été **{label}** !")

        elif reward_type == "degats":
            before = hp.setdefault(gid, {}).get(uid, 100)
            after = max(before - reward, 0)
            hp[gid][uid] = after
            results.append(f"💥 {user.mention} a subi **{reward} dégâts** (PV: {after})")

        elif reward_type == "soin":
            before = hp.setdefault(gid, {}).get(uid, 100)
            after = min(before + reward, 100)
            hp[gid][uid] = after
            results.append(f"💚 {user.mention} a récupéré **{reward} PV** (PV: {after})")

        elif reward_type == "regen":
            start_now = time.time()
            regeneration_status.setdefault(gid, {})[uid] = {
                "start": start_now,
                "duration": 3 * 3600,
                "last_tick": 0,
                "source": None,
                "channel_id": channel.id
            }
            results.append(f"✨ {user.mention} bénéficie d’une **régénération** pendant 3h.")

    if results:
        recap = discord.Embed(
            title="📦 Récapitulatif du ravitaillement",
            description="\n".join(results),
            color=discord.Color.green()
        )
        await channel.send(embed=recap)
    else:
        await channel.send("💣 Le ravitaillement spécial s’est auto-détruit. Aucune réaction détectée.")

    supply_data[gid]["is_open"] = False
    supply_data[gid]["active_supply_id"] = None
    sauvegarder()

# ========================== Boucle de contrôle ==========================

async def special_supply_loop(bot):
    await bot.wait_until_ready()
    print("🎁 Boucle spéciale supply démarrée (check 15 min)")

    while not bot.is_closed():
        # Check global ON/OFF
        if not is_special_supply_enabled():
            print("⚠️ Boucle supply désactivée temporairement. Skip 15 min...")
            await asyncio.sleep(900)
            continue

        now_dt = datetime.datetime.utcnow() + datetime.timedelta(hours=2)  # UTC+2 (heure FR courante)
        now_hour = now_dt.hour
        today_str = now_dt.strftime("%Y-%m-%d")

        for guild in bot.guilds:
            gid = str(guild.id)
            config = supply_data.setdefault(gid, {})
            config.setdefault("daily_supply_status", {})
            status_today = config["daily_supply_status"].setdefault(today_str, {
                "morning_sent": False,
                "afternoon_sent": False,
                "evening_sent": False
            })

            # Vérifie le créneau en cours
            if 8 <= now_hour < 12 and not status_today["morning_sent"]:
                target_slot = "morning_sent"
            elif 13 <= now_hour < 17 and not status_today["afternoon_sent"]:
                target_slot = "afternoon_sent"
            elif 18 <= now_hour < 23 and not status_today["evening_sent"]:
                target_slot = "evening_sent"
            else:
                target_slot = None

            if target_slot:
                # Définir les paliers de proba
                current_hour = now_hour
                current_minute = now_dt.minute

                # Créneaux par slot
                if target_slot == "morning_sent":
                    if current_hour == 8:
                        proba = 0.05
                    elif current_hour == 9:
                        proba = 0.15
                    elif current_hour == 10:
                        proba = 0.35
                    elif current_hour == 11:
                        proba = 0.80
                    elif current_hour == 12:
                        proba = 1.0
                    else:
                        proba = 0.0

                elif target_slot == "afternoon_sent":
                    if current_hour == 13:
                        proba = 0.05
                    elif current_hour == 14:
                        proba = 0.15
                    elif current_hour == 15:
                        proba = 0.35
                    elif current_hour == 16:
                        proba = 0.80
                    elif current_hour == 17:
                        proba = 1.0
                    else:
                        proba = 0.0

                elif target_slot == "evening_sent":
                    if current_hour == 18:
                        proba = 0.05
                    elif current_hour == 19:
                        proba = 0.15
                    elif current_hour == 20:
                        proba = 0.35
                    elif current_hour == 21:
                        proba = 0.50
                    elif current_hour == 22:
                        proba = 0.80
                    elif current_hour == 23:
                        proba = 1.0
                    else:
                        proba = 0.0

                else:
                    proba = 0.0

                print(f"[{guild.name}] Slot {target_slot} - Heure {current_hour}:{current_minute:02} → proba {proba * 100:.1f}%")

                if random.random() < proba:
                    print(f"🎁 Envoi spécial supply sur {guild.name} ({target_slot}) → déclenché !")
                    channel = find_or_update_valid_channel(bot, guild, config)
                    if channel:
                        await send_special_supply_in_channel(bot, guild, channel)
                        status_today[target_slot] = True
                        sauvegarder()
                else:
                    print(f"⏳ Supply sur {guild.name} ({target_slot}) → attente (proba pas atteinte).")

        await asyncio.sleep(900)  # toutes les 15 minutes


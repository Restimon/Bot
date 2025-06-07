import discord
import random
import time
import asyncio

from data import virus_status, poison_status, infection_status, regeneration_status, supply_data, sauvegarder
from storage import get_user_data, hp
from utils import get_random_item, OBJETS
from embeds import build_embed_from_item

# ========================== Mise à jour du salon actif ==========================

def update_last_active_channel(message):
    if message.author.bot:
        return

    guild_id = str(message.guild.id)

    if guild_id not in supply_data or not isinstance(supply_data[guild_id], dict):
        supply_data[guild_id] = {}

    supply_data[guild_id]["last_channel_id"] = message.channel.id
    supply_data[guild_id]["last_activity_time"] = time.time()
    sauvegarder()

# ========================== Description des objets ==========================

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

# ========================== Génération des récompenses ==========================

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

# ========================== Recherche de salon compatible ==========================

def find_valid_channel(bot, guild, config):
    last_id = config.get("last_channel_id")
    if last_id:
        ch = bot.get_channel(last_id)
        if ch:
            perms = ch.permissions_for(guild.me)
            if perms.send_messages and perms.add_reactions and perms.read_messages:
                return ch

    for ch in guild.text_channels:
        perms = ch.permissions_for(guild.me)
        if perms.send_messages and perms.add_reactions and perms.read_messages:
            return ch

    return None

# ========================== Envoi du ravitaillement ==========================

async def send_special_supply(bot, force=False):
    now = time.time()

    for guild in bot.guilds:
        gid = str(guild.id)
        config = supply_data.get(gid, {})

        # Vérifie cooldown (sauf si force)
        if not force:
            last_time = config.get("last_supply_time", 0)
            count_today = config.get("supply_count_today", 0)
            if now - last_time < 3600 or count_today >= 3:
                continue

        channel = find_valid_channel(bot, guild, config)
        if not channel:
            continue

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
        supply_data[gid]["collected_users"] = []  # optionnel si tu veux limiter
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
                dico.setdefault(gid, {})[uid] = {
                    "start": now,
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
                regeneration_status.setdefault(gid, {})[uid] = {
                    "start": now,
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

        supply_data[gid]["last_supply_time"] = now
        supply_data[gid]["is_open"] = False
        supply_data[gid]["supply_count_today"] = config.get("supply_count_today", 0) + 1
        sauvegarder()

def find_or_update_valid_channel(bot, guild, data):
    # 1️⃣ Essayer le last_channel_id connu
    last_id = data.get("last_channel_id")
    if last_id:
        ch = bot.get_channel(last_id)
        if ch:
            perms = ch.permissions_for(guild.me)
            if perms.send_messages and perms.add_reactions and perms.read_messages:
                return ch

    # 2️⃣ Essayons par "activité" si on a un log
    activity_log = data.get("channel_activity_log", {})
    sorted_channels = sorted(activity_log.items(), key=lambda x: x[1], reverse=True)  # tri par last_activity_time desc

    for channel_id, _ in sorted_channels:
        ch = bot.get_channel(int(channel_id))
        if ch:
            perms = ch.permissions_for(guild.me)
            if perms.send_messages and perms.add_reactions and perms.read_messages:
                # Update officiel du last_channel_id
                data["last_channel_id"] = ch.id
                data["last_activity_time"] = time.time()
                sauvegarder()
                print(f"[{guild.name}] Nouveau salon actif sélectionné (log) : #{ch.name}")
                return ch

    # 3️⃣ Sinon fallback → on essaye tout (ex: channels triés par position ou par id)
    for ch in sorted(guild.text_channels, key=lambda c: c.position):
        perms = ch.permissions_for(guild.me)
        if perms.send_messages and perms.add_reactions and perms.read_messages:
            data["last_channel_id"] = ch.id
            data["last_activity_time"] = time.time()
            sauvegarder()
            print(f"[{guild.name}] Nouveau salon actif fallback : #{ch.name}")
            return ch

    # Aucun salon trouvé
    return None


    # Aucun salon valide trouvé
    return None

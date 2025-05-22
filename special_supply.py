import random
import time
import asyncio
import discord
import json
import os
from discord.ext import tasks

from utils import OBJETS
from storage import get_user_data, hp, leaderboard
from data import virus_status, poison_status, infection_status, regeneration_status

# Variables globales
last_supply_time = 0
supply_daily_counter = {}  # {guild_id: (date, count)}
last_active_channel = {}   # {guild_id: channel_id}
SUPPLY_MIN_DELAY = 2 * 3600
SUPPLY_MAX_DELAY = 8 * 3600
SUPPLY_DATA_FILE = "supply_data.json"

def save_supply_data():
    with open(SUPPLY_DATA_FILE, "w") as f:
        json.dump({
            "supply_daily_counter": supply_daily_counter,
            "last_supply_time": last_supply_time
        }, f)

def load_supply_data():
    global supply_daily_counter, last_supply_time
    if os.path.exists(SUPPLY_DATA_FILE):
        with open(SUPPLY_DATA_FILE, "r") as f:
            data = json.load(f)
            supply_daily_counter = data.get("supply_daily_counter", {})
            last_supply_time = data.get("last_supply_time", 0)


def get_random_item():
    pool = []
    for emoji, data in OBJETS.items():
        pool.extend([emoji] * (26 - data["rarete"]))
    return random.choice(pool)

def describe_item(emoji):
    obj = OBJETS.get(emoji, {})
    typ = obj.get("type")
    if typ == "attaque":
        return f"🗡️ Inflige {obj.get('degats')} dégâts. (Crit {int(obj.get('crit', 0)*100)}%)"
    if typ == "virus":
        return "🦠 Virus : 5 dégâts initiaux + 5/h pendant 6h."
    if typ == "poison":
        return "🧪 Poison : 3 dégâts initiaux + 3/30min pendant 3h."
    if typ == "infection":
        return "🧟 Infection : 5 dégâts initiaux + 2/30min pendant 3h. 25% de propagation."
    if typ == "soin":
        return f"💚 Restaure {obj.get('soin')} PV. (Crit {int(obj.get('crit', 0)*100)}%)"
    if typ == "regen":
        return "✨ Régénère 3 PV toutes les 30min pendant 3h."
    if typ == "mysterybox":
        return "📦 Boîte surprise : 1 à 3 objets aléatoires."
    if typ == "vol":
        return "🔍 Vole un objet aléatoire à un autre joueur."
    if typ == "vaccin":
        return "💉 Utilisable via /heal pour soigner virus/poison."
    if typ == "bouclier":
        return "🛡 Ajoute un bouclier de 20 PV."
    if typ == "esquive+":
        return "👟 Augmente les chances d’esquive pendant 3h."
    if typ == "reduction":
        return "🪖 Réduit les dégâts subis de moitié pendant 4h."
    if typ == "immunite":
        return "⭐️ Immunité : ignore tous les dégâts pendant 2h."
    return "❓ Effet inconnu."

def choose_reward(user_id, guild_id):
    roll = random.random()
    if roll <= 0.75:
        return "objet", get_random_item()
    elif roll <= 0.80:
        return "status", random.choice(["poison", "virus", "infection"])
    elif roll <= 0.90:
        return "degats", random.randint(1, 15)
    else:
        return "soin", random.randint(1, 10)

async def send_special_supply(bot, force=False):
    global last_supply_time, supply_daily_counter

    now = time.time()
    today = time.strftime("%Y-%m-%d")

    for guild in bot.guilds:
        gid = str(guild.id)

        if not force:
            channel_id = last_active_channel.get(gid)
            if not channel_id:
                continue
        else:
            channel_id = last_active_channel.get(gid)
            if not channel_id:
                continue

        date, count = supply_daily_counter.get(gid, (None, 0))
        if date != today:
            supply_daily_counter[gid] = (today, 0)
        elif count >= 3 and not force:
            continue

        channel = bot.get_channel(channel_id)
        if not channel:
            continue

        embed = discord.Embed(
            title="📦 Ravitaillement spécial SomniCorp",
            description="Réagissez avec 📦 pour récupérer une récompense surprise !\n"
                        "⏳ Disponible pendant 5 minutes, maximum 5 personnes.",
            color=discord.Color.gold()
        )
        msg = await channel.send(embed=embed)
        await msg.add_reaction("📦")

        collected_users = []

        def check(reaction, user):
            return (
                reaction.message.id == msg.id
                and str(reaction.emoji) == "📦"
                and not user.bot
                and user.id not in [u.id for u in collected_users]
            )

        end_time = time.time() + 300
        while len(collected_users) < 5 and time.time() < end_time:
            try:
                reaction, user = await asyncio.wait_for(
                    bot.wait_for("reaction_add", check=check),
                    timeout=end_time - time.time(),
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
                desc = describe_item(reward)
                results.append(f"🎁 {user.mention} a obtenu **{reward}** — {desc}")
            elif reward_type == "status":
                status_map = {
                    "poison": (poison_status, "🧪", "empoisonné", 3 * 3600),
                    "virus": (virus_status, "🦠", "infecté par un virus", 6 * 3600),
                    "infection": (infection_status, "🧟", "infecté", 3 * 3600),
                }
                status_dict, emoji, label, dur = status_map[reward]
                status_dict.setdefault(gid, {})[uid] = {
                    "start": now,
                    "duration": dur,
                    "last_tick": 0,
                    "source": None,
                    "channel_id": channel.id
                }
                results.append(f"{emoji} {user.mention} a été **{label}** !")
            elif reward_type == "degats":
                before = hp[gid].get(uid, 100)
                after = max(before - reward, 0)
                hp[gid][uid] = after
                results.append(f"💥 {user.mention} a pris **{reward} dégâts** (PV: {after})")
            elif reward_type == "soin":
                before = hp[gid].get(uid, 100)
                after = min(before + reward, 100)
                hp[gid][uid] = after
                results.append(f"💚 {user.mention} a récupéré **{reward} PV** (PV: {after})")

        if results:
            await channel.send(
                embed=discord.Embed(
                    title="📦 Récapitulatif du ravitaillement spécial",
                    description="\n".join(results),
                    color=discord.Color.green()
                )
            )
        else:
            await channel.send("💥 Le ravitaillement spécial SomniCorp s’est auto-détruit. 💣")

        supply_daily_counter[gid] = (today, supply_daily_counter[gid][1] + 1)
        last_supply_time = now
        save_supply_data()

def update_last_active_channel(message):
    if message.guild and not message.author.bot:  # Ignorer les messages de bots
        last_active_channel[str(message.guild.id)] = message.channel.id

@tasks.loop(minutes=5)
async def special_supply_loop(bot):
    now = time.time()
    delay = random.randint(SUPPLY_MIN_DELAY, SUPPLY_MAX_DELAY)
    if now - last_supply_time >= delay:
        await send_special_supply(bot)

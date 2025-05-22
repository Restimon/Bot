import random
import time
import asyncio
import discord
from discord.ext import tasks

from utils import OBJETS
from storage import get_user_data, hp, leaderboard
from data import (
    virus_status,
    poison_status,
    infection_status,
    regeneration_status,
)

# Variables globales
last_supply_time = 0
supply_daily_counter = {}  # {guild_id: (date, count)}
last_active_channel = {}   # {guild_id: channel_id}
SUPPLY_MIN_DELAY = 2 * 3600
SUPPLY_MAX_DELAY = 8 * 3600

def get_random_item():
    pool = []
    for emoji, data in OBJETS.items():
        pool.extend([emoji] * (26 - data["rarete"]))
    return random.choice(pool)

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

async def send_special_supply(bot):
    global last_supply_time, supply_daily_counter

    now = time.time()
    today = time.strftime("%Y-%m-%d")

    for guild in bot.guilds:
        gid = str(guild.id)
        last_time = supply_daily_counter.get(gid, (None, 0))

        # Reset du compteur quotidien
        if last_time[0] != today:
            supply_daily_counter[gid] = (today, 0)

        # Pas d'envoi si limite atteinte
        if supply_daily_counter[gid][1] >= 3:
            continue

        # Pas de nouvelle activité
        channel_id = last_active_channel.get(gid)
        if not channel_id:
            continue

        channel = bot.get_channel(channel_id)
        if not channel:
            continue

        # Envoi du ravitaillement
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

        end_time = time.time() + 300  # 5 minutes
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
                results.append(f"🎁 {user.mention} a obtenu **{reward}**")
            elif reward_type == "status":
                if reward == "poison":
                    poison_status.setdefault(gid, {})[uid] = {
                        "start": now,
                        "duration": 3 * 3600,
                        "last_tick": 0,
                        "source": None,
                        "channel_id": channel.id
                    }
                    results.append(f"🧪 {user.mention} a été **empoisonné** !")
                elif reward == "virus":
                    virus_status.setdefault(gid, {})[uid] = {
                        "start": now,
                        "duration": 6 * 3600,
                        "last_tick": 0,
                        "source": None,
                        "channel_id": channel.id
                    }
                    results.append(f"🦠 {user.mention} a attrapé un **virus** !")
                elif reward == "infection":
                    infection_status.setdefault(gid, {})[uid] = {
                        "start": now,
                        "duration": 3 * 3600,
                        "last_tick": 0,
                        "source": None,
                        "channel_id": channel.id
                    }
                    results.append(f"🧟 {user.mention} a été **infecté** !")
            elif reward_type == "degats":
                dmg = reward
                hp.setdefault(gid, {})
                before = hp[gid].get(uid, 100)
                after = max(before - dmg, 0)
                hp[gid][uid] = after
                results.append(f"💥 {user.mention} a pris **{dmg} dégâts** (PV: {after})")
            elif reward_type == "soin":
                heal = reward
                hp.setdefault(gid, {})
                before = hp[gid].get(uid, 100)
                after = min(before + heal, 100)
                hp[gid][uid] = after
                results.append(f"💚 {user.mention} a récupéré **{heal} PV** (PV: {after})")

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

        # Mise à jour du cooldown
        supply_daily_counter[gid] = (today, supply_daily_counter[gid][1] + 1)
        last_supply_time = now

# Mise à jour automatique de l'activité
def update_last_active_channel(message):
    if message.guild:
        last_active_channel[str(message.guild.id)] = message.channel.id

# Démarre la boucle automatique
@tasks.loop(minutes=5)
async def special_supply_loop(bot):
    now = time.time()
    if now - last_supply_time >= random.randint(SUPPLY_MIN_DELAY, SUPPLY_MAX_DELAY):
        await send_special_supply(bot)

import discord
from discord.ext import commands
import asyncio
import os
from dotenv import load_dotenv

from config import load_config, config
from data import charger, sauvegarder
from utils import cooldowns, get_random_item, inventaire, hp, leaderboard, OBJETS
from combat import apply_item_with_cooldown
from inventory import build_inventory_embed
from leaderboard import build_leaderboard_embed
from help import register_help_commands
from daily import register_daily_command
from fight import register_fight_command
from heal import register_heal_command
from admin import register_admin_commands
from profile import register_profile_command

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
    member = user or interaction.user
    uid = str(member.id)
    embed = build_inventory_embed(uid, bot)
    await interaction.response.send_message(embed=embed, ephemeral=(user is not None and user != interaction.user))

@bot.tree.command(name="leaderboard", description="Voir le classement SomniCorp")
async def leaderboard_slash(interaction: discord.Interaction):
    embed = await build_leaderboard_embed(bot)  
    await interaction.response.send_message(embed=embed)

# ===================== Command Registration ======================

def register_all_commands(bot):
    register_help_commands(bot)
    register_daily_command(bot)
    register_fight_command(bot)
    register_heal_command(bot)
    register_admin_commands(bot)
    register_profile_command(bot)

# ===================== Events ======================

@bot.event
async def on_ready():
    await bot.wait_until_ready()

    register_all_commands(bot)

    await bot.tree.sync()

    charger()
    load_config()

    print(f"✅ SomniCorp Bot prêt. Connecté en tant que {bot.user}")
    print("🔧 Commandes slash enregistrées :")
    for command in bot.tree.get_commands():
        print(f" - /{command.name}")

    bot.loop.create_task(update_leaderboard_loop())

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
        item = get_random_item()
        await message.add_reaction(item)
        last_drop_time = current_time  

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
                uid = str(user.id)
                inventaire.setdefault(uid, []).append(item)
                hp.setdefault(uid, 100)
                leaderboard.setdefault(uid, {"degats": 0, "soin": 0})
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
    from utils import leaderboard
    from config import save_config

    while not bot.is_closed():
        channel_id = config.get("leaderboard_channel_id")
        message_id = config.get("leaderboard_message_id")

        if channel_id:
            channel = bot.get_channel(channel_id)
            if channel:
                # Construit le message texte du leaderboard
                medals = ["🥇", "🥈", "🥉"]
                sorted_lb = sorted(leaderboard.items(), key=lambda x: x[1]['degats'], reverse=True)
                lines = []
                rank = 0
                for uid, stats in sorted_lb[:10]:
                    user = bot.get_user(int(uid))
                    if not user:
                        continue  # Ignore les comptes inconnus/supprimés

                    prefix = medals[rank] if rank < len(medals) else f"{rank + 1}."
                    lines.append(f"{prefix} **{user.name}**  →  🗡️ {stats['degats']}   |   💚 {stats['soin']}")
                    rank += 1


                if lines:
                    text = (
                        "🏆 __**CLASSEMENT SOMNICORP - ÉDITION SPÉCIALE**__ 🏆\n\n" +
                        "\n".join(lines) +
                        "\n\n📌 Mise à jour automatique toutes les 5 minutes."
                    )
                else:
                    text = "*Aucune donnée disponible.*"

                try:
                    # Si un message est enregistré, essaie de le modifier
                    if message_id:
                        msg = await channel.fetch_message(message_id)
                        await msg.edit(content=text)
                    else:
                        raise discord.NotFound(response=None, message="No message ID")

                except (discord.NotFound, discord.HTTPException):
                    # S'il n'existe plus ou jamais envoyé : recréer un nouveau
                    msg = await channel.send(content=text)
                    config["leaderboard_message_id"] = msg.id
                    save_config()

        await asyncio.sleep(300)

# ===================== Run ======================

bot.run(os.getenv("DISCORD_TOKEN"))

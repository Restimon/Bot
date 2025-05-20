import discord
import time
from utils import get_random_item, get_user_data
from data import sauvegarder

# Structure par serveur : {guild_id: {user_id: timestamp}}
last_daily_claim = {}

@bot.tree.command(name="daily", description="Réclame ta récompense quotidienne SomniCorp")
async def daily_slash(interaction: discord.Interaction):
    guild_id = str(interaction.guild_id)
    user_id = str(interaction.user.id)
    now = time.time()

    last_daily_claim.setdefault(guild_id, {})

    last_claim = last_daily_claim[guild_id].get(user_id)
    if last_claim and now - last_claim < 86400:
        remaining = 86400 - (now - last_claim)
        hours = int(remaining // 3600)
        minutes = int((remaining % 3600) // 60)
        return await interaction.response.send_message(
            f"⏳ Tu as déjà réclamé ta récompense aujourd’hui ! Reviens dans **{hours}h {minutes}min**.",
            ephemeral=True
        )

    reward1 = get_random_item()
    reward2 = get_random_item()

    user_data = get_user_data(guild_id, user_id)
    user_data["inventory"].extend([reward1, reward2])  # ✅ bonne méthode
    last_daily_claim[guild_id][user_id] = now
    sauvegarder()

    await interaction.response.send_message(
        f"🎁 Tu as reçu : {reward1} et {reward2} !\n**SomniCorp apprécie ta loyauté.**",
        ephemeral=True
    )

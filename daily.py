import discord
import time
from utils import get_random_item, inventaire, hp, leaderboard
from data import sauvegarder

last_daily_claim = {}

def register_daily_command(bot):
    @bot.tree.command(name="daily", description="Réclame ta récompense quotidienne SomniCorp")
    async def daily_slash(interaction: discord.Interaction):
        uid = str(interaction.user.id)
        now = time.time()

        if uid in last_daily_claim and now - last_daily_claim[uid] < 86400:
            remaining = 86400 - (now - last_daily_claim[uid])
            hours = int(remaining // 3600)
            minutes = int((remaining % 3600) // 60)
            return await interaction.response.send_message(
                f"⏳ SomniCorp t'a déjà donné ta récompense aujourd'hui ! Reviens dans **{hours}h {minutes}min**.",
                ephemeral=True
            )

        reward1 = get_random_item()
        reward2 = get_random_item()
        inventaire.setdefault(uid, []).extend([reward1, reward2])
        hp.setdefault(uid, 100)
        leaderboard.setdefault(uid, {"degats": 0, "soin": 0})
        last_daily_claim[uid] = now
        sauvegarder()

        await interaction.response.send_message(
            f"🎁 Tu as reçu tes récompenses journalières : {reward1} et {reward2} !\n**Merci de ta fidélité à SomniCorp.**",
            ephemeral=True
        )

import discord
import time
from utils import get_random_item
from storage import get_user_data
from data import sauvegarder, last_daily_claim, leaderboard
from embeds import build_embed_from_item
from economy import gotcoins_stats, gotcoins_balance, add_gotcoins, init_gotcoins_stats

def register_daily_command(bot):
    @bot.tree.command(name="daily", description="Réclame ta récompense quotidienne GotValis")
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
                f"⏳ Tu as déjà réclamé ta récompense aujourd’hui offert par GotValis ! Reviens dans **{hours}h {minutes}min**.",
                ephemeral=True
            )

        # Récompenses
        reward1 = get_random_item()
        reward2 = get_random_item()

        # Inventaire
        user_inv, _, _ = get_user_data(guild_id, user_id)
        user_inv.extend([reward1, reward2])

        # GotCoins → +25
        leaderboard.setdefault(guild_id, {}).setdefault(user_id, {
            "degats": 0, "soin": 0, "kills": 0, "morts": 0
        })
        leaderboard[guild_id][user_id]["soin"] += 25

        # Enregistrer date daily
        last_daily_claim[guild_id][user_id] = now

        sauvegarder()  # sauvegarde globale

        embed = discord.Embed(
            title="🎁 Récompense quotidienne de GotValis",
            description=(
                f"{interaction.user.mention} a reçu : {reward1} et {reward2} !\n"
                f"💰 **+25 GotCoins** ajoutés à ton compte.\n"
                f"Merci pour ta fidélité à **GotValis**."
            ),
            color=discord.Color.green()
        )
        embed.set_footer(text="À réutiliser dans 24h.")

        await interaction.response.send_message(embed=embed)

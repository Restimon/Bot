import discord
import time
from utils import get_random_item, OBJETS
from storage import get_user_data
from data import sauvegarder, last_daily_claim, leaderboard
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

        # --- Récompenses ---
        reward1 = get_random_item()
        reward2 = get_random_item()

        # --- Inventaire ---
        user_inv, _, _ = get_user_data(guild_id, user_id)
        user_inv.extend([reward1, reward2])

        # --- GotCoins → +25 ---
        add_gotcoins(guild_id, user_id, 25, category="autre")

        # --- Enregistrer date daily ---
        last_daily_claim[guild_id][user_id] = now

        # --- Sauvegarde globale ---
        sauvegarder()

        # --- Construction de l'embed ---
        embed = discord.Embed(
            title="🎁 Récompense quotidienne de GotValis",
            description=f"{interaction.user.mention}, voici ta récompense :",
            color=discord.Color.green()
        )

        # --- Récompense 1 ---
        desc1 = OBJETS.get(reward1, {}).get("description", "*Pas de description*")
        embed.add_field(
            name=f"{reward1}",
            value=f"{desc1}",
            inline=False
        )

        # --- Récompense 2 ---
        desc2 = OBJETS.get(reward2, {}).get("description", "*Pas de description*")
        embed.add_field(
            name=f"{reward2}",
            value=f"{desc2}",
            inline=False
        )

        # --- GotCoins ---
        embed.add_field(
            name="💰 GotCoins",
            value="💰 **+25 GotCoins** ajoutés à ton compte.",
            inline=False
        )

        embed.set_footer(text="⏳ Disponible à nouveau dans 24h.")

        # --- Envoi ---
        await interaction.response.send_message(embed=embed)

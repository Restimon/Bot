import discord
import time
from utils import get_random_item, OBJETS
from storage import get_user_data
from data import sauvegarder, last_daily_claim
from economy import add_gotcoins
from passifs import appliquer_passif  # ✅ Intégration du système de passifs

def register_daily_command(bot):
    @bot.tree.command(name="daily", description="Réclame ta récompense quotidienne GotValis")
    async def daily_slash(interaction: discord.Interaction):
        guild_id = str(interaction.guild_id)
        user_id = str(interaction.user.id)
        now = time.time()

        last_daily_claim.setdefault(guild_id, {})

        # 🎯 Vérifie si cooldown personnalisé via passif (ex : Nyra Kell)
        cooldown_result = appliquer_passif(user_id, "daily_cooldown", {
            "guild_id": guild_id,
            "user_id": user_id
        })
        cooldown_multiplier = cooldown_result.get("cooldown_multiplicateur", 1) if cooldown_result else 1
        cooldown_duration = int(86400 * cooldown_multiplier)

        last_claim = last_daily_claim[guild_id].get(user_id)
        if last_claim and now - last_claim < cooldown_duration:
            remaining = cooldown_duration - (now - last_claim)
            hours = int(remaining // 3600)
            minutes = int((remaining % 3600) // 60)
            return await interaction.response.send_message(
                f"⏳ Tu as déjà réclamé ta récompense aujourd’hui ! Reviens dans **{hours}h {minutes}min**.",
                ephemeral=True
            )

        # 🎁 Récompenses de base
        reward1 = get_random_item()
        reward2 = get_random_item()
        gotcoins_gain = 25

        # 🧠 Passif de Lior Danen (double récompense)
        passif_result = appliquer_passif(user_id, "daily", {
            "guild_id": guild_id,
            "user_id": user_id
        })

        if passif_result and passif_result.get("double_daily"):
            reward1 = get_random_item()
            reward2 = get_random_item()
            gotcoins_gain *= 2

            bonus_embed = discord.Embed(
                title="✨ Pouvoir de Lior Danen !",
                description="🌀 Grâce à son passif, vous recevez **le double des récompenses** aujourd'hui !",
                color=discord.Color.blurple()
            )
            await interaction.followup.send(embed=bonus_embed, ephemeral=True)

        # 🧳 Ajout à l’inventaire
        user_inv, _, _ = get_user_data(guild_id, user_id)
        user_inv.extend([reward1, reward2])

        # 💰 GotCoins
        add_gotcoins(guild_id, user_id, gotcoins_gain, category="autre")

        # 🕒 Mise à jour du dernier claim
        last_daily_claim[guild_id][user_id] = now

        # 💾 Sauvegarde
        sauvegarder()

        # 📦 Texte final
        desc1 = OBJETS.get(reward1, {}).get("description", "*Pas de description*")
        desc2 = OBJETS.get(reward2, {}).get("description", "*Pas de description*")

        embed = discord.Embed(
            title="🎁 Récompense quotidienne de GotValis",
            description=(
                f"{interaction.user.mention}, voici ta récompense :\n\n"
                f"📦 {reward1} — {desc1}\n"
                f"📦 {reward2} — {desc2}\n"
                f"\n💰 +{gotcoins_gain} GotCoins\n"
                f"\n⏳ Disponible à nouveau dans {int(cooldown_duration // 3600)}h."
            ),
            color=discord.Color.green()
        )

        await interaction.response.send_message(embed=embed)

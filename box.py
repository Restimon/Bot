import random
import discord
from discord import app_commands
from storage import get_user_data
from utils import OBJETS

def register_box_command(bot):
    @bot.tree.command(name="box", description="Ouvre une boîte 📦 et reçois des objets aléatoires.")
    async def box_slash(interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)

        guild_id = str(interaction.guild.id)
        user_id = str(interaction.user.id)

        user_inv, _, _ = get_user_data(guild_id, user_id)

        if "📦" not in user_inv:
            await interaction.followup.send("❌ Tu n’as pas de 📦 à ouvrir.", ephemeral=True)
            return

        # Retire une boîte
        user_inv.remove("📦")

        # Génère du loot
        possible = [k for k in OBJETS if k != "📦"]
        mode = random.randint(1, 3)

        loot = []
        if mode == 1:
            item = random.choice(possible)
            loot = [item] * 3
        elif mode == 2:
            selected = random.sample(possible, 2)
            loot = [selected[0]] * 2 + [selected[1]]
        else:
            loot = random.sample(possible, 3)

        user_inv.extend(loot)

        # Formatage
        counts = {}
        for item in loot:
            counts[item] = counts.get(item, 0) + 1

        loot_display = "\n".join(f"{emoji} × {count}" for emoji, count in counts.items())

        embed = discord.Embed(
            title="📦 Boîte ouverte !",
            description=f"Voici ce que tu as reçu :\n{loot_display}",
            color=discord.Color.gold()
        )

        await interaction.followup.send(embed=embed)

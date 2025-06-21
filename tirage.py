import discord
import random
import json
import os

from discord import app_commands
from discord.ext import commands
from datetime import datetime, timedelta
from data import PERSONNAGES
from embeds import build_personnage_embed
from storage import get_inventory

TIRAGE_FILE = "persistent/tirages.json"

RARETE_PROBABILITES_MILLIEMES = {
    "Commun": 845,
    "Rare": 100,
    "Epique": 54,
    "Legendaire": 1
}

def get_random_rarity(probabilities=None):
    if probabilities is None:
        probabilities = RARETE_PROBABILITES_MILLIEMES
    total = sum(probabilities.values())
    tirage = random.randint(1, total)
    cumul = 0
    for rarete, poids in probabilities.items():
        cumul += poids
        if tirage <= cumul:
            return rarete
    return "Commun"

def get_random_character(rarity="Commun"):
    candidats = [data for data in PERSONNAGES.values() if data["rarete"].lower() == rarity.lower()]
    return random.choice(candidats) if candidats else None

def get_random_character_by_probability(probabilities=None):
    rarete = get_random_rarity(probabilities)
    return get_random_character(rarete)

def load_tirages():
    if not os.path.exists(TIRAGE_FILE):
        return {}
    with open(TIRAGE_FILE, "r") as f:
        return json.load(f)

def save_tirages(data):
    with open(TIRAGE_FILE, "w") as f:
        json.dump(data, f, indent=2)

class Tirage(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="tirage", description="Effectue ton tirage quotidien de personnage.")
    async def tirage(self, interaction: discord.Interaction):
        await interaction.response.defer()

        user_id = str(interaction.user.id)
        guild_id = str(interaction.guild_id)
        key = f"{guild_id}-{user_id}"

        tirages = load_tirages()
        now = datetime.utcnow()

        if key in tirages:
            last_time = datetime.fromisoformat(tirages[key])
            if now - last_time < timedelta(days=1):
                remaining = timedelta(days=1) - (now - last_time)
                hours = remaining.seconds // 3600
                minutes = (remaining.seconds % 3600) // 60
                await interaction.followup.send(
                    f"❌ Tu as déjà effectué ton tirage aujourd'hui.\nRéessaye dans **{hours}h {minutes}min**.",
                    ephemeral=True
                )
                return

        perso = get_random_character_by_probability()
        if not perso:
            await interaction.followup.send("❌ Aucun personnage disponible pour cette rareté.", ephemeral=True)
            return

        embed = build_personnage_embed(perso, user=interaction.user)

        # ✅ Ajout du personnage dans la collection
        from storage import get_inventory
        get_inventory(guild_id).setdefault(user_id, []).append({"personnage": perso["nom"]})

        tirages[key] = now.isoformat()
        save_tirages(tirages)

        try:
            image_path = perso["image"]
            image_filename = os.path.basename(image_path)
            with open(image_path, "rb") as f:
                file = discord.File(f, filename=image_filename)
                await interaction.followup.send(embed=embed, file=file)
        except Exception as e:
            await interaction.followup.send(
                f"✅ Tu as obtenu : **{perso['nom']}**\n⚠️ Impossible d’afficher l’image ({e})",
                embed=embed
            )

async def setup(bot):
    await bot.add_cog(Tirage(bot))



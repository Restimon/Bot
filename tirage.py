import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timedelta
import random
import json
import os

from data import PERSONNAGES, OBJETS  # Tu dois avoir ces dictionnaires

# ===============================
# 🎲 TIRAGE DE PERSONNAGE PAR RARETÉ
# ===============================

RARETE_PROBABILITES_MILLIEMES = {
    "Commun": 845,
    "Rare": 100,
    "Epique": 54,
    "Legendaire": 1  # ≈ 0.19 % → 50 % chance cumulée sur 1 an
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
    candidats = [nom for nom, data in PERSONNAGES.items() if data["rarete"].lower() == rarity.lower()]
    if not candidats:
        return None
    return random.choice(candidats)

def get_random_character_by_probability(probabilities=None):
    rarete = get_random_rarity(probabilities)
    return get_random_character(rarete)

# ===============================
# 🎁 TIRAGE D’OBJET
# ===============================

def get_random_object():
    return random.choice(list(OBJETS.keys()))

def get_random_object_by_type(type_):
    candidats = [nom for nom, data in OBJETS.items() if data["type"] == type_]
    return random.choice(candidats) if candidats else None

# ===============================
# 🧭 COMMANDE /tirage
# ===============================

TIRAGE_FILE = "persistent/tirages.json"

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

        personnage = get_random_character_by_probability()
        infos = PERSONNAGES.get(personnage, {})
        rarete = infos.get("rarete", "Commun")

        tirages[key] = now.isoformat()
        save_tirages(tirages)

        couleurs = {
            "Commun": 0xaaaaaa,
            "Rare": 0x4a90e2,
            "Epique": 0x9b59b6,
            "Legendaire": 0xf1c40f
        }

        embed = discord.Embed(
            title="🎲 Tirage quotidien - GotValis",
            description=f"Tu as obtenu : **{personnage}**",
            color=couleurs.get(rarete, 0xffffff)
        )
        embed.add_field(name="Rareté", value=f"`{rarete}`", inline=True)
        embed.set_footer(text="Prochain tirage disponible dans 24h.")

        await interaction.followup.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Tirage(bot))

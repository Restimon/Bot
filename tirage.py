import discord
from discord import app_commands
from discord.ext import commands

import random
import os
from datetime import datetime, timedelta

from data import PERSONNAGES, tirages, sauvegarder
from embeds import build_personnage_embed
from storage import get_inventory, ajouter_personnage
from passifs import appliquer_passif  # ✅ Ajouté

# 🎲 Probabilités de rareté (en millièmes)
RARETE_PROBABILITES_MILLIEMES = {
    "Commun": 845,
    "Rare": 100,
    "Epique": 54,
    "Legendaire": 1
}

# 🔢 Tire une rareté selon les probabilités définies
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

# 🎴 Tire un personnage d'une rareté donnée
def get_random_character(rarity="Commun"):
    candidats = [data for data in PERSONNAGES.values() if data["rarete"].lower() == rarity.lower()]
    return random.choice(candidats) if candidats else None

# 🔁 Tire un personnage selon les probabilités complètes
def get_random_character_by_probability(probabilities=None):
    rarete = get_random_rarity(probabilities)
    return get_random_character(rarete)

class Tirage(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="tirage", description="Effectue ton tirage quotidien de personnage.")
    async def tirage(self, interaction: discord.Interaction):
        await interaction.response.defer()

        user = interaction.user
        guild_id = str(interaction.guild_id)
        user_id = str(user.id)
        key = f"{guild_id}-{user_id}"
        now = datetime.utcnow()

        # ⏳ Vérifie si un tirage a déjà été effectué aujourd'hui
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

        # 🎯 Vérifie s’il y a un bonus de rareté via passif (Nael Mirren)
        bonus_passif = appliquer_passif("tirage_objet", {"guild_id": guild_id, "user_id": user_id})
        bonus_rarite = bonus_passif.get("bonus_rarite") if bonus_passif else False

        proba_modifiées = RARETE_PROBABILITES_MILLIEMES.copy()
        if bonus_rarite:
            proba_modifiées["Legendaire"] += 1
            proba_modifiées["Epique"] += 3
            proba_modifiées["Rare"] += 6
            proba_modifiées["Commun"] = max(0, proba_modifiées["Commun"] - 10)

        # 🎴 Tirage du personnage
        perso = get_random_character_by_probability(probabilities=proba_modifiées)
        if not perso:
            await interaction.followup.send("❌ Aucun personnage disponible pour cette rareté.", ephemeral=True)
            return

        # ✅ Ajout dans l'inventaire
        ajouter_personnage(guild_id, user_id, perso["nom"])

        # 💾 Mise à jour de la date de tirage + sauvegarde globale
        tirages[key] = now.isoformat()
        sauvegarder()

        # 📦 Construction de l'embed
        embed = build_personnage_embed(perso, user=user)
        embed.set_footer(text="🎴 Le personnage a été ajouté à ta collection.")
        if bonus_rarite:
            embed.add_field(name="✨ Coup de chance !", value="Le passif de **Nael Mirren** a boosté la rareté du tirage.", inline=False)

        # 🖼 Envoi avec image si disponible
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

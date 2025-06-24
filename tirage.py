import discord
from discord import app_commands
from discord.ext import commands

import random
import os
from datetime import datetime, timedelta

from data import PERSONNAGES, tirages, sauvegarder
from embeds import build_personnage_embed
from storage import get_inventory, ajouter_personnage, modifier_inventaire
from passifs import appliquer_passif

# 🎲 Probabilités de rareté
RARETE_PROBABILITES_MILLIEMES = {
    "Commun": 845,
    "Rare": 100,
    "Epique": 54,
    "Legendaire": 1
}

TICKET_EMOJI = "🎫"

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

class Tirage(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="tirage", description="Effectue un tirage de personnage (journalier ou avec un ticket).")
    async def tirage(self, interaction: discord.Interaction):
        await interaction.response.defer()

        user = interaction.user
        guild_id = str(interaction.guild_id)
        user_id = str(user.id)
        key = f"{guild_id}-{user_id}"
        now = datetime.utcnow()

        inventaire = get_inventory(guild_id, user_id)
        utilise_ticket = False

        # ⏳ Vérifie le tirage journalier
        if key in tirages:
            last_time = datetime.fromisoformat(tirages[key])
            if now - last_time < timedelta(days=1):
                # Si le journalier est déjà utilisé, on regarde s’il a un ticket
                if inventaire.get(TICKET_EMOJI, 0) > 0:
                    utilise_ticket = True
                    modifier_inventaire(guild_id, user_id, TICKET_EMOJI, -1)
                else:
                    remaining = timedelta(days=1) - (now - last_time)
                    hours = remaining.seconds // 3600
                    minutes = (remaining.seconds % 3600) // 60
                    await interaction.followup.send(
                        f"❌ Tu as déjà utilisé ton tirage journalier.\nRéessaye dans **{hours}h {minutes}min** ou utilise un {TICKET_EMOJI} Ticket de Tirage.",
                        ephemeral=True
                    )
                    return
        else:
            tirages[key] = now.isoformat()
            sauvegarder()

        # 🎯 Bonus passif (Nael Mirren)
        bonus_passif = appliquer_passif("tirage_objet", {"guild_id": guild_id, "user_id": user_id})
        bonus_rarite = bonus_passif.get("bonus_rarite") if bonus_passif else False

        proba_modifiées = RARETE_PROBABILITES_MILLIEMES.copy()
        if bonus_rarite:
            proba_modifiées["Legendaire"] += 1
            proba_modifiées["Epique"] += 3
            proba_modifiées["Rare"] += 6
            proba_modifiées["Commun"] = max(0, proba_modifiées["Commun"] - 10)

        perso = get_random_character_by_probability(probabilities=proba_modifiées)
        if not perso:
            await interaction.followup.send("❌ Aucun personnage disponible pour cette rareté.", ephemeral=True)
            return

        ajouter_personnage(guild_id, user_id, perso["nom"])

        # Embed résultat
        embed = build_personnage_embed(perso, user=user)
        if utilise_ticket:
            embed.set_footer(text="🎫 Le personnage a été obtenu grâce à un Ticket de Tirage.")
        else:
            embed.set_footer(text="🎴 Le personnage a été obtenu via le tirage journalier.")

        if bonus_rarite:
            embed.add_field(name="✨ Coup de chance !", value="Le passif de **Nael Mirren** a boosté la rareté du tirage.", inline=False)

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

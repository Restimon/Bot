# tirage.py
import os
import random
from datetime import datetime, timedelta

import discord
from discord import app_commands
from discord.ext import commands

from personnage import PERSONNAGES  # dictionnaire {nom: data}
from storage import get_inventory, ajouter_personnage
from data import sauvegarder, tirages  # tirages: dict "guild-user" -> iso datetime
from embeds import build_personnage_embed

# Optionnel: si passifs non prêts au démarrage, on ignore proprement
try:
    from passifs import appliquer_passif
except Exception:
    def appliquer_passif(*args, **kwargs):
        return None

# 🎲 Probabilités de rareté (en millièmes) — avec accents qui matchent personnage.RARETES
RARETE_PROBABILITES_MILLIEMES = {
    "Commun": 845,
    "Rare": 100,
    "Épique": 54,
    "Légendaire": 1,
}

TICKET_EMOJI = "🎟️"


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
    # PERSONNAGES est un dict nom -> data
    candidats = [p for p in PERSONNAGES.values() if p.get("rarete") == rarity]
    return random.choice(candidats) if candidats else None


def get_random_character_by_probability(probabilities=None):
    rarete = get_random_rarity(probabilities)
    return get_random_character(rarete)


def _consume_one_ticket(inv_list):
    """Retire UN 🎟️ de la liste d’inventaire si présent, renvoie True si consommé."""
    try:
        inv_list.remove(TICKET_EMOJI)
        return True
    except ValueError:
        return False


class Tirage(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="tirage",
        description="Effectue un tirage de personnage (journalier ou via un ticket 🎟️)."
    )
    async def tirage(self, interaction: discord.Interaction):
        await interaction.response.defer()

        user = interaction.user
        guild_id = str(interaction.guild_id)
        user_id = str(user.id)
        key = f"{guild_id}-{user_id}"
        now = datetime.utcnow()

        # Inventaire: dict[user_id] -> list[str]
        server_inv = get_inventory(guild_id)
        inv_list = server_inv.setdefault(user_id, [])

        utilise_ticket = False

        # ⏳ Vérifie le journalier
        if key in tirages:
            last_time = datetime.fromisoformat(tirages[key])
            if now - last_time < timedelta(days=1):
                # Journalier déjà utilisé → on consomme un ticket si on en a
                if _consume_one_ticket(inv_list):
                    utilise_ticket = True
                    # pas besoin d’appeler sauvegarder() ici, on le fera à la fin
                else:
                    remaining = timedelta(days=1) - (now - last_time)
                    hours = remaining.seconds // 3600
                    minutes = (remaining.seconds % 3600) // 60
                    await interaction.followup.send(
                        f"❌ Tu as déjà utilisé ton tirage journalier.\n"
                        f"Réessaye dans **{hours}h {minutes}min** ou utilise un {TICKET_EMOJI} Ticket de Tirage.",
                        ephemeral=True
                    )
                    return
        else:
            tirages[key] = now.isoformat()
            sauvegarder()

        # 🎯 Bonus passif (ex: Nael Mirren)
        proba_modifiées = RARETE_PROBABILITES_MILLIEMES.copy()
        try:
            bonus_passif = appliquer_passif("tirage_objet", {"guild_id": guild_id, "user_id": user_id})
        except Exception:
            bonus_passif = None
        bonus_rarite = bonus_passif.get("bonus_rarite") if isinstance(bonus_passif, dict) else False

        if bonus_rarite:
            # Petit boost: on diminue "Commun" et on augmente les autres
            proba_modifiées["Légendaire"] += 1
            proba_modifiées["Épique"] += 3
            proba_modifiées["Rare"] += 6
            proba_modifiées["Commun"] = max(0, proba_modifiées["Commun"] - 10)

        perso = get_random_character_by_probability(probabilities=proba_modifiées)
        if not perso:
            await interaction.followup.send("❌ Aucun personnage disponible pour cette rareté.", ephemeral=True)
            return

        # Ajout à la collection (stockée comme dict d’objets dans inventaire via storage.ajouter_personnage)
        ajouter_personnage(guild_id, user_id, perso["nom"])
        sauvegarder()

        # Embed résultat
        embed = build_personnage_embed(perso, user=user)
        if utilise_ticket:
            embed.set_footer(text="🎟️ Le personnage a été obtenu grâce à un Ticket de Tirage.")
        else:
            embed.set_footer(text="🎴 Le personnage a été obtenu via le tirage journalier.")

        if bonus_rarite:
            embed.add_field(
                name="✨ Coup de chance !",
                value="Un passif a **boosté la rareté** du tirage.",
                inline=False
            )

        # Image locale si dispo
        try:
            image_path = perso.get("image")
            if image_path and os.path.exists(image_path):
                image_filename = os.path.basename(image_path)
                with open(image_path, "rb") as f:
                    file = discord.File(f, filename=image_filename)
                embed.set_image(url=f"attachment://{image_filename}")
                await interaction.followup.send(embed=embed, file=file)
                return
        except Exception as e:
            # On tombe sur l’envoi sans fichier si souci I/O
            pass

        await interaction.followup.send(embed=embed)


# === Intégrations multiples (compatibilité) ===

async def setup(bot):
    """Chargement via extensions (await bot.load_extension)."""
    await bot.add_cog(Tirage(bot))


def register_tirage_command(bot):
    """Compat pour les main.py qui appellent register_tirage_command(bot)."""
    try:
        bot.add_cog(Tirage(bot))
    except TypeError:
        import asyncio
        asyncio.create_task(bot.add_cog(Tirage(bot)))

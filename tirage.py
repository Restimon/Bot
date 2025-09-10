# tirage.py
import os
import random
from datetime import datetime, timedelta

import discord
from discord import app_commands
from discord.ext import commands

from personnage import PERSONNAGES  # dict {nom: data}
from storage import get_inventory, ajouter_personnage
from data import sauvegarder, tirages  # dict: key "guild-user" -> ISO datetime string
from embeds import build_personnage_embed

# Passifs optionnels (safe import)
try:
    from passifs import appliquer_passif
except Exception:
    def appliquer_passif(*args, **kwargs):
        return None

# 🎲 Probabilités par rareté (en millièmes, total = 1000)
RARETE_PROBABILITES_MILLIEMES = {
    "Commun": 845,
    "Rare": 100,
    "Épique": 54,
    "Légendaire": 1,
}

TICKET_EMOJI = "🎟️"


def get_random_rarity(probabilities=None):
    """Retourne une rareté selon les pondérations en millièmes."""
    probs = probabilities or RARETE_PROBABILITES_MILLIEMES
    total = sum(probs.values())
    if total <= 0:
        return "Commun"
    tirage = random.randint(1, total)
    cumul = 0
    for rarete, poids in probs.items():
        cumul += max(0, int(poids))
        if tirage <= cumul:
            return rarete
    return "Commun"


def get_random_character(rarity="Commun"):
    """Prend un personnage au hasard pour une rareté donnée."""
    candidats = [p for p in PERSONNAGES.values() if p.get("rarete") == rarity]
    return random.choice(candidats) if candidats else None


def get_random_character_by_probability(probabilities=None):
    rarete = get_random_rarity(probabilities)
    return get_random_character(rarete)


def _consume_one_ticket(inv_list):
    """Retire UN 🎟️ si présent. Renvoie True si un ticket a été consommé."""
    try:
        inv_list.remove(TICKET_EMOJI)
        return True
    except ValueError:
        return False


def _cooldown_remaining_text(last_dt: datetime, now: datetime) -> str:
    """Texte lisible du temps restant avant le prochain journalier."""
    diff = (last_dt + timedelta(days=1)) - now
    secs = max(0, int(diff.total_seconds()))
    h = secs // 3600
    m = (secs % 3600) // 60
    return f"{h}h {m}min"


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

        # ⏳ Journalier déjà utilisé ?
        if key in tirages:
            try:
                last_time = datetime.fromisoformat(tirages[key])
            except Exception:
                # Si format corrompu, on reset comme non-utilisé
                last_time = None

            if last_time and (now - last_time) < timedelta(days=1):
                # Journalier en cooldown → on tente d'utiliser un ticket
                if _consume_one_ticket(inv_list):
                    utilise_ticket = True
                    # On ne touche pas au timer journalier
                else:
                    # Pas de ticket → on dit quand réessayer
                    rest = _cooldown_remaining_text(last_time, now)
                    await interaction.followup.send(
                        f"❌ Tu as déjà utilisé ton tirage journalier.\n"
                        f"Réessaye dans **{rest}** ou utilise un {TICKET_EMOJI} **Ticket de Tirage**.",
                        ephemeral=True
                    )
                    return
            else:
                # Journalier disponible à nouveau → on le consomme maintenant
                tirages[key] = now.isoformat()
        else:
            # Premier tirage journalier de ce joueur
            tirages[key] = now.isoformat()

        # 🎯 Boosts/passifs éventuels
        proba_mod = RARETE_PROBABILITES_MILLIEMES.copy()
        bonus = appliquer_passif("tirage_objet", {"guild_id": guild_id, "user_id": user_id})
        bonus_rarite = isinstance(bonus, dict) and bonus.get("bonus_rarite")

        if bonus_rarite:
            # petit boost contrôlé
            proba_mod["Légendaire"] = proba_mod.get("Légendaire", 0) + 1
            proba_mod["Épique"] = proba_mod.get("Épique", 0) + 3
            proba_mod["Rare"] = proba_mod.get("Rare", 0) + 6
            proba_mod["Commun"] = max(0, proba_mod.get("Commun", 0) - 10)

        # 🧲 Tirage d’un personnage
        perso = get_random_character_by_probability(probabilities=proba_mod)
        if not perso:
            await interaction.followup.send("❌ Aucun personnage disponible pour cette rareté.", ephemeral=True)
            return

        # Ajout à la collection
        ajouter_personnage(guild_id, user_id, perso["nom"])

        # Persistance (collection + tickets consommés + usage journalier)
        sauvegarder()

        # Embed résultat
        embed = build_personnage_embed(perso, user=user)
        if utilise_ticket:
            embed.set_footer(text="🎟️ Obtenu grâce à un Ticket de Tirage.")
        else:
            embed.set_footer(text="🎴 Obtenu via le tirage journalier.")

        if bonus_rarite:
            embed.add_field(
                name="✨ Coup de chance !",
                value="Un passif a **boosté la rareté** du tirage.",
                inline=False
            )

        # Image locale si dispo
        image_path = perso.get("image")
        if image_path and os.path.exists(image_path):
            try:
                filename = os.path.basename(image_path)
                file = discord.File(image_path, filename=filename)
                embed.set_image(url=f"attachment://{filename}")
                await interaction.followup.send(embed=embed, file=file)
                return
            except Exception:
                pass  # on retombe sur l’envoi sans fichier

        await interaction.followup.send(embed=embed)


# === Intégrations ===
async def setup(bot):
    """Chargement en extension: await bot.load_extension('tirage')"""
    await bot.add_cog(Tirage(bot))


def register_tirage_command(bot):
    """Compat si tu préfères un appel simple dans main()."""
    try:
        bot.add_cog(Tirage(bot))
    except TypeError:
        import asyncio
        asyncio.create_task(bot.add_cog(Tirage(bot)))

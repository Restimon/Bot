# tirage.py
import os
import random
from datetime import datetime, timedelta

import discord
from discord import app_commands
from discord.ext import commands

from personnage import PERSONNAGES  # dict {nom: data}
from storage import get_inventory, ajouter_personnage
from data import sauvegarder, tirages  # tirages: dict "guild-user" -> iso datetime
from embeds import build_personnage_embed

# Passifs optionnels (tolérant si non dispo au démarrage)
try:
    from passifs import appliquer_passif
except Exception:
    def appliquer_passif(*args, **kwargs):
        return None

# 🎲 Probabilités de rareté (en millièmes)
RARETE_PROBABILITES_MILLIEMES = {
    "Commun": 845,
    "Rare": 100,
    "Épique": 54,
    "Légendaire": 1,
}

TICKET_EMOJI = "🎟️"


def _fmt_remaining(td: timedelta) -> str:
    total_min = int(td.total_seconds() // 60)
    if total_min >= 120:
        h = total_min // 60
        m = total_min % 60
        return f"{h}h {m}min" if m else f"{h}h"
    return f"{total_min} min"


def _get_random_rarity(probabilities=None):
    """Retourne une rareté selon les poids (en millièmes)."""
    if probabilities is None:
        probabilities = RARETE_PROBABILITES_MILLIEMES
    total = sum(probabilities.values())
    if total <= 0:
        return "Commun"
    r = random.randint(1, total)
    acc = 0
    for rarete, poids in probabilities.items():
        acc += poids
        if r <= acc:
            return rarete
    return "Commun"


def _pick_character_by_rarity(rarity="Commun"):
    """Choisit un personnage d’une rareté donnée."""
    candidats = [p for p in PERSONNAGES.values() if p.get("rarete") == rarity]
    return random.choice(candidats) if candidats else None


def _draw_one_character(guild_id: str, user_id: str, use_ticket: bool = False):
    """
    Effectue le tirage (avec éventuel boost de passifs),
    renvoie (perso_dict, used_probabilities, bonus_rarite_bool).
    """
    # Probabilités modifiables (ex: Nael Mirren, etc.)
    proba = dict(RARETE_PROBABILITES_MILLIEMES)
    bonus_rarite = False

    try:
        bonus = appliquer_passif("tirage_objet", {"guild_id": guild_id, "user_id": user_id})
        bonus_rarite = isinstance(bonus, dict) and bonus.get("bonus_rarite", False)
    except Exception:
        bonus_rarite = False

    if bonus_rarite:
        # Petit bonus de chance
        proba["Légendaire"] += 1
        proba["Épique"] += 3
        proba["Rare"] += 6
        proba["Commun"] = max(0, proba["Commun"] - 10)

    rarity = _get_random_rarity(proba)
    perso = _pick_character_by_rarity(rarity)
    return perso, proba, bonus_rarite


def _consume_one_ticket(inv_list: list) -> bool:
    """Retire UN 🎟️ de l’inventaire si présent."""
    try:
        inv_list.remove(TICKET_EMOJI)
        return True
    except ValueError:
        return False


class _UseTicketView(discord.ui.View):
    """Vue avec bouton pour confirmer l’usage d’un ticket si journalier indisponible."""
    def __init__(self, *, timeout: float = 30.0, on_confirm):
        super().__init__(timeout=timeout)
        self.on_confirm = on_confirm
        self.confirmed = False

    @discord.ui.button(label="Utiliser 1 🎟️ Ticket", style=discord.ButtonStyle.primary, emoji="🎟️")
    async def use_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.confirmed = True
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)
        await self.on_confirm(interaction)


class Tirage(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="tirage",
        description="Effectue un tirage de personnage (journalier s’il est disponible, sinon avec un ticket 🎟️)."
    )
    async def tirage(self, interaction: discord.Interaction):
        await interaction.response.defer()

        user = interaction.user
        guild_id = str(interaction.guild_id)
        user_id = str(user.id)
        key = f"{guild_id}-{user_id}"
        now = datetime.utcnow()

        # Inventaire du serveur et du joueur (liste d’emojis/objets)
        server_inv = get_inventory(guild_id)
        inv_list = server_inv.setdefault(user_id, [])

        # --- 1) Journalier disponible ? ---
        daily_available = True
        if key in tirages:
            try:
                last_time = datetime.fromisoformat(tirages[key])
                daily_available = (now - last_time) >= timedelta(days=1)
            except Exception:
                # Si la date est corrompue → on considère dispo
                daily_available = True

        # --- 2) Si journalier dispo → on tire tout de suite ---
        if daily_available:
            perso, _, bonus_rarite = _draw_one_character(guild_id, user_id, use_ticket=False)
            if not perso:
                await interaction.followup.send("❌ Aucun personnage disponible à tirer pour le moment.", ephemeral=True)
                return

            # Marque le journalier comme utilisé maintenant
            tirages[key] = now.isoformat()
            # Ajoute à la collection
            ajouter_personnage(guild_id, user_id, perso["nom"])
            sauvegarder()

            # Embed résultat
            embed = build_personnage_embed(perso, user=user)
            embed.set_footer(text="🎴 Obtenu via le tirage journalier.")
            if bonus_rarite:
                embed.add_field(name="✨ Coup de chance !", value="Un passif a **boosté la rareté** du tirage.", inline=False)

            # Image locale si dispo
            image_path = perso.get("image")
            if image_path and os.path.exists(image_path):
                file = discord.File(image_path, filename=os.path.basename(image_path))
                embed.set_image(url=f"attachment://{os.path.basename(image_path)}")
                await interaction.followup.send(embed=embed, file=file)
            else:
                await interaction.followup.send(embed=embed)
            return

        # --- 3) Journalier PAS dispo → proposer d’utiliser un ticket si dispo ---
        ticket_count = inv_list.count(TICKET_EMOJI)
        if ticket_count <= 0:
            # Indiquer le temps restant
            try:
                last_time = datetime.fromisoformat(tirages[key])
                remaining = timedelta(days=1) - (now - last_time)
                if remaining.total_seconds() < 0:
                    remaining = timedelta(0)
            except Exception:
                remaining = timedelta(0)

            await interaction.followup.send(
                f"❌ Ton tirage journalier n’est pas encore dispo.\n"
                f"⏳ Il sera disponible dans **{_fmt_remaining(remaining)}**.\n\n"
                f"💡 Achète des **tickets {TICKET_EMOJI}** dans `/shop` pour tirer même quand le journalier est en CD.",
                ephemeral=True
            )
            return

        # Vue + bouton “Utiliser 1 ticket”
        async def on_confirm(use_interaction: discord.Interaction):
            # Re-sécurise l’inventaire (si autre action entre-temps)
            server_inv2 = get_inventory(guild_id)
            inv_list2 = server_inv2.setdefault(user_id, [])
            if not _consume_one_ticket(inv_list2):
                await use_interaction.followup.send("❌ Ticket introuvable. Réessaie.", ephemeral=True)
                return

            # Tirage via ticket
            perso, _, bonus_rarite = _draw_one_character(guild_id, user_id, use_ticket=True)
            if not perso:
                await use_interaction.followup.send("❌ Aucun personnage disponible à tirer pour le moment.", ephemeral=True)
                return

            # Ajout à la collection (note : le ticket n’affecte PAS le cooldown journalier)
            ajouter_personnage(guild_id, user_id, perso["nom"])
            sauvegarder()

            embed = build_personnage_embed(perso, user=user)
            embed.set_footer(text="🎟️ Obtenu via un Ticket de Tirage.")
            if bonus_rarite:
                embed.add_field(name="✨ Coup de chance !", value="Un passif a **boosté la rareté** du tirage.", inline=False)

            image_path = perso.get("image")
            if image_path and os.path.exists(image_path):
                file = discord.File(image_path, filename=os.path.basename(image_path))
                embed.set_image(url=f"attachment://{os.path.basename(image_path)}")
                await use_interaction.followup.send(embed=embed, file=file)
            else:
                await use_interaction.followup.send(embed=embed)

        view = _UseTicketView(on_confirm=on_confirm)
        # Message de proposition
        try:
            last_time = datetime.fromisoformat(tirages[key])
            remaining = timedelta(days=1) - (now - last_time)
            if remaining.total_seconds() < 0:
                remaining = timedelta(0)
        except Exception:
            remaining = timedelta(0)

        await interaction.followup.send(
            f"🕒 Ton tirage journalier sera dispo dans **{_fmt_remaining(remaining)}**.\n"
            f"🎟️ Tickets en inventaire : **{ticket_count}**\n\n"
            f"Veux-tu **utiliser 1 ticket** pour tirer maintenant ?",
            view=view,
            ephemeral=True
        )


# === Intégrations ===
async def setup(bot):
    await bot.add_cog(Tirage(bot))

def register_tirage_command(bot):
    # compat pour main.py qui ne charge pas via extensions
    try:
        bot.add_cog(Tirage(bot))
    except TypeError:
        import asyncio
        asyncio.create_task(bot.add_cog(Tirage(bot)))

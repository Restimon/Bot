# perso.py
# ─────────────────────────────────────────────────────────────────────────────
# Commande /perso : affiche un personnage de la collection d'un joueur
# par **numéro** (l’ordre correspond à /collection : tri par rareté → faction → nom).
# ─────────────────────────────────────────────────────────────────────────────

import os
import discord
from discord import app_commands
from discord.ext import commands

from personnage import PERSONNAGES, RARETES, FACTION_ORDER
from storage import get_collection
from embeds import build_personnage_embed


# ─────────────────────────────────────────────────────────────────────────────
# Helpers internes
# ─────────────────────────────────────────────────────────────────────────────

def _tri_key(p: dict):
    """Clé de tri : (rareté, faction, nom) avec garde-fous."""
    try:
        r_idx = RARETES.index(p.get("rarete", "Commun"))
    except ValueError:
        r_idx = 999

    try:
        f_idx = FACTION_ORDER.index(p.get("faction", ""))
    except ValueError:
        f_idx = 999

    return (r_idx, f_idx, p.get("nom", ""))


# Liste globale triée une fois (réduit le CPU à chaque /perso)
_ALL_PERSONNAGES_SORTED = sorted(PERSONNAGES.values(), key=_tri_key)


def _materialiser_collection_ordonnee(collection: dict) -> list[dict]:
    """
    À partir de la collection {nom: quantité}, génère une liste **dupliquée**
    des persos dans l’ordre global pré-calculé.
    Exemple : {"Kael Dris": 2} → [Kael, Kael] aux positions où Kael apparaît.
    """
    if not isinstance(collection, dict) or not collection:
        return []

    out: list[dict] = []
    for p in _ALL_PERSONNAGES_SORTED:
        nom = p.get("nom")
        qte = int(collection.get(nom, 0) or 0)
        if qte > 0:
            out.extend([p] * qte)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Cog
# ─────────────────────────────────────────────────────────────────────────────

class Perso(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="perso",
        description="Affiche un personnage de ta collection (ou celle d’un autre joueur) par numéro."
    )
    @app_commands.describe(
        index="Numéro du personnage (dans l’ordre de ta /collection)",
        user="Joueur cible (optionnel)"
    )
    async def perso(
        self,
        interaction: discord.Interaction,
        index: int,
        user: discord.Member | None = None
    ):
        await interaction.response.defer()

        target = user or interaction.user
        user_id = str(target.id)
        guild_id = str(interaction.guild_id)

        # 1) Récupérer la collection de l’utilisateur
        collection = get_collection(guild_id, user_id)  # {nom: quantité}
        if not collection:
            await interaction.followup.send(
                f"❌ {target.mention} n’a **aucun personnage** dans sa collection.",
                ephemeral=True
            )
            return

        # 2) Construire la liste matérialisée (duplication par quantité)
        full_list = _materialiser_collection_ordonnee(collection)
        total = len(full_list)
        if total == 0:
            await interaction.followup.send(
                f"❌ {target.mention} n’a **aucun personnage** dans sa collection.",
                ephemeral=True
            )
            return

        # 3) Vérifier l’index (1-based)
        if not (1 <= index <= total):
            await interaction.followup.send(
                f"❌ Numéro invalide. {target.display_name} possède **{total}** personnage(s).",
                ephemeral=True
            )
            return

        perso = full_list[index - 1]

        # 4) Construire l’embed
        embed = build_personnage_embed(perso, user=target)

        # 5) Joindre l’image locale si dispo (fallback : embed sans fichier)
        image_path = perso.get("image")
        if image_path and os.path.exists(image_path):
            try:
                filename = os.path.basename(image_path)
                file = discord.File(image_path, filename=filename)
                embed.set_image(url=f"attachment://{filename}")
                await interaction.followup.send(embed=embed, file=file)
                return
            except Exception:
                # En cas d’erreur I/O, on envoie sans fichier
                pass

        await interaction.followup.send(embed=embed)

    # ── Autocomplétion d’index : affiche "i. Nom" jusqu’à 25 entrées
    @perso.autocomplete("index")
    async def index_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str
    ):
        target = interaction.namespace.user or interaction.user
        user_id = str(target.id)
        guild_id = str(interaction.guild_id)

        collection = get_collection(guild_id, user_id)
        if not collection:
            return []

        names: list[str] = []
        for p in _ALL_PERSONNAGES_SORTED:
            nom = p["nom"]
            qte = int(collection.get(nom, 0) or 0)
            if qte > 0:
                names.extend([nom] * qte)

        cur = (current or "").strip()
        # On ne renvoie que des Choice(value=int) comme attendu par la cmd
        choices: list[app_commands.Choice[int]] = []
        for i, nom in enumerate(names, start=1):
            if cur and cur not in str(i):
                continue
            choices.append(app_commands.Choice(name=f"{i}. {nom}", value=i))
            if len(choices) >= 25:
                break

        return choices


async def setup(bot: commands.Bot):
    await bot.add_cog(Perso(bot))

# perso.py
import os
import discord
from discord import app_commands
from discord.ext import commands

from personnage import PERSONNAGES, RARETES, FACTION_ORDER
from storage import get_collection
from embeds import build_personnage_embed


def _all_personnages_sorted():
    """
    Retourne la liste de TOUS les persos triés par:
      1) rareté (ordre RARETES)
      2) faction (ordre FACTION_ORDER)
      3) nom (alphabétique)
    """
    # Regrouper par rareté
    by_rarity = {r: [] for r in RARETES}
    for p in PERSONNAGES.values():
        by_rarity.setdefault(p["rarete"], []).append(p)

    out = []
    for rarete in RARETES:
        group = by_rarity.get(rarete, [])
        # Tri faction puis nom
        group.sort(key=lambda p: (FACTION_ORDER.index(p["faction"]), p["nom"]))
        out.extend(group)
    return out


class Perso(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="perso",
        description="Affiche un personnage de ta collection (ou celle d’un autre joueur) par numéro."
    )
    @app_commands.describe(
        index="Numéro du personnage (dans l’ordre de ta /collection)",
        user="Joueur cible (optionnel)"
    )
    async def perso(self, interaction: discord.Interaction, index: int, user: discord.Member = None):
        await interaction.response.defer()

        target = user or interaction.user
        user_id = str(target.id)
        guild_id = str(interaction.guild_id)

        # Collection du joueur: {nom: count}
        collection = get_collection(guild_id, user_id)
        if not collection:
            await interaction.followup.send("❌ Ce joueur n’a aucun personnage dans sa collection.", ephemeral=True)
            return

        # Construire la liste complète triée, dupliquant selon la quantité possédée
        full_list = []
        for perso in _all_personnages_sorted():
            nom = perso["nom"]
            nb = collection.get(nom, 0)
            if nb > 0:
                full_list.extend([perso] * nb)

        if not (1 <= index <= len(full_list)):
            await interaction.followup.send(
                f"❌ Numéro invalide. {target.display_name} possède **{len(full_list)}** personnage(s).",
                ephemeral=True
            )
            return

        perso = full_list[index - 1]
        embed = build_personnage_embed(perso, user=target)

        # Image locale si dispo
        image_path = perso.get("image")
        if image_path and os.path.exists(image_path):
            image_filename = os.path.basename(image_path)
            try:
                file = discord.File(image_path, filename=image_filename)
                embed.set_image(url=f"attachment://{image_filename}")
                await interaction.followup.send(embed=embed, file=file)
                return
            except Exception:
                pass  # on retombe sur l’envoi sans fichier si souci I/O

        await interaction.followup.send(embed=embed)

    # Autocomplétion dynamique sur l’index
    @perso.autocomplete("index")
    async def index_autocomplete(self, interaction: discord.Interaction, current: str):
        target = interaction.namespace.user or interaction.user
        user_id = str(target.id)
        guild_id = str(interaction.guild_id)

        collection = get_collection(guild_id, user_id)
        if not collection:
            return []

        # Recrée la liste des noms selon le tri + duplication
        names = []
        for p in _all_personnages_sorted():
            nom = p["nom"]
            nb = collection.get(nom, 0)
            if nb > 0:
                names.extend([nom] * nb)

        # Filtre simple: l’utilisateur tape un bout de chiffre → propose
        cur = (current or "").strip()
        choices = []
        for i, nom in enumerate(names, start=1):
            if cur and cur not in str(i):
                continue
            choices.append(app_commands.Choice(name=f"{i}. {nom}", value=i))
            if len(choices) >= 25:
                break

        return choices


async def setup(bot):
    await bot.add_cog(Perso(bot))

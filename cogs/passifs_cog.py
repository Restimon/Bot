# cogs/passifs_cog.py
from __future__ import annotations

import discord
from discord.ext import commands
from discord import app_commands
from typing import List, Optional

# Données personnages / passifs
from personnage import PERSONNAGES, trouver, get_tous_les_noms, PASSIF_CODE_MAP


# ─────────────────────────────────────────────────────────────
# Autocomplete (⚠️ doit être async pour Discord)
# ─────────────────────────────────────────────────────────────
async def autocomplete_personnages(interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
    current = (current or "").strip()
    noms = get_tous_les_noms()
    if not current:
        subset = noms[:20]
    else:
        subset = []
        cur_lower = current.lower()
        for n in noms:
            if cur_lower in n.lower():
                subset.append(n)
            if len(subset) >= 20:
                break
        if not subset:
            subset = noms[:10]
    return [app_commands.Choice(name=n, value=n) for n in subset]


# ─────────────────────────────────────────────────────────────
# Cog
# ─────────────────────────────────────────────────────────────
class PassifsCog(commands.Cog):
    """Exploration des personnages et de leurs passifs (lecture seule)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="passifs_info", description="Affiche la fiche d’un personnage et son passif.")
    @app_commands.describe(personnage="Nom exact ou partiel")
    @app_commands.autocomplete(personnage=autocomplete_personnages)
    async def passifs_info(self, interaction: discord.Interaction, personnage: str):
        await interaction.response.defer(ephemeral=True)

        p = trouver(personnage) or PERSONNAGES.get(personnage)
        if not p:
            return await interaction.followup.send("❌ Personnage introuvable.", ephemeral=True)

        nom = p.get("nom", "Inconnu")
        rarete = p.get("rarete", "?")
        faction = p.get("faction", "?")
        passif = p.get("passif", {}) or {}
        passif_nom = passif.get("nom", "?")
        passif_effet = passif.get("effet", "")

        # Code interne pratique (si mappé)
        internal_code = PASSIF_CODE_MAP.get(passif_nom, "")

        emb = discord.Embed(
            title=f"🎴 {nom}",
            color=discord.Color.purple()
        )
        emb.add_field(name="Rareté", value=str(rarete), inline=True)
        emb.add_field(name="Faction", value=str(faction), inline=True)
        emb.add_field(name="Passif", value=f"**{passif_nom}**\n> {passif_effet}", inline=False)
        if internal_code:
            emb.set_footer(text=f"Code interne: {internal_code}")

        await interaction.followup.send(embed=emb, ephemeral=True)

    @app_commands.command(name="passifs_search", description="Recherche des personnages par mot-clé.")
    @app_commands.describe(mot_cle="Une partie du nom")
    async def passifs_search(self, interaction: discord.Interaction, mot_cle: str):
        await interaction.response.defer(ephemeral=True)
        mot = (mot_cle or "").strip().lower()
        if not mot:
            return await interaction.followup.send("Tape un mot-clé pour filtrer.", ephemeral=True)

        noms = get_tous_les_noms()
        matches = [n for n in noms if mot in n.lower()][:20]
        if not matches:
            return await interaction.followup.send("Aucun résultat.", ephemeral=True)

        lines = "\n".join(f"• {n}" for n in matches)
        emb = discord.Embed(title="Résultats", description=lines, color=discord.Color.blurple())
        await interaction.followup.send(embed=emb, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(PassifsCog(bot))

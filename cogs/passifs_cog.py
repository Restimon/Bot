# cogs/passifs_cog.py
from __future__ import annotations

from typing import List, Optional

import discord
from discord import app_commands
from discord.ext import commands

from personnage import PERSONNAGES, trouver, get_tous_les_noms
from passifs import get_equipped_name, init_passifs_db
# (Optionnel) pour debug : nom->code
from personnage import PASSIF_CODE_MAP


class PassifsCog(commands.Cog):
    """Outils autour des passifs (consultation, recherche)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ─────────────────────────────────────────────────────────
    # /passifinfo — affiche TON personnage équipé + passif
    # ─────────────────────────────────────────────────────────
    @app_commands.command(name="passifinfo", description="Affiche ton personnage équipé et son passif.")
    async def passifinfo(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        name = await get_equipped_name(interaction.user.id)
        if not name:
            await interaction.followup.send("❌ Aucun personnage équipé. Utilise `/equip`.", ephemeral=True)
            return
        p = PERSONNAGES.get(name)
        if not p:
            await interaction.followup.send("❌ Données introuvables pour ce personnage.", ephemeral=True)
            return

        emb = discord.Embed(
            title=f"🎴 {p['nom']}",
            description=(
                f"**Rareté** : {p.get('rarete','?')}\n"
                f"**Faction** : {p.get('faction','?')}\n"
                f"**Passif** : **{p.get('passif',{}).get('nom','?')}**\n"
                f"> {p.get('passif',{}).get('effet','')}"
            ),
            color=discord.Color.gold()
        )
        await interaction.followup.send(embed=emb, ephemeral=True)

    # ─────────────────────────────────────────────────────────
    # /passifwhois — affiche le perso équipé d’un membre
    # ─────────────────────────────────────────────────────────
    @app_commands.command(name="passifwhois", description="Affiche le personnage équipé d’un membre.")
    @app_commands.describe(membre="Le membre à inspecter.")
    async def passifwhois(self, interaction: discord.Interaction, membre: Optional[discord.Member] = None):
        await interaction.response.defer(ephemeral=True)
        target = membre or interaction.user
        name = await get_equipped_name(target.id)
        if not name:
            await interaction.followup.send(f"ℹ️ **{target.display_name}** n’a aucun personnage équipé.", ephemeral=True)
            return
        p = PERSONNAGES.get(name)
        if not p:
            await interaction.followup.send("❌ Données introuvables pour ce personnage.", ephemeral=True)
            return

        emb = discord.Embed(
            title=f"🧭 {target.display_name} — {p['nom']}",
            description=(
                f"**Rareté** : {p.get('rarete','?')}\n"
                f"**Faction** : {p.get('faction','?')}\n"
                f"**Passif** : **{p.get('passif',{}).get('nom','?')}**\n"
                f"> {p.get('passif',{}).get('effet','')}"
            ),
            color=discord.Color.green()
        )
        await interaction.followup.send(embed=emb, ephemeral=True)

    # ─────────────────────────────────────────────────────────
    # /passifsearch — recherche dans la base des personnages
    # (avec autocomplete ASYNC, pas de lambda)
    # ─────────────────────────────────────────────────────────
    @app_commands.command(name="passifsearch", description="Recherche un personnage (affiche son passif).")
    @app_commands.describe(personnage="Nom exact ou partiel")
    @app_commands.autocomplete(personnage=lambda i, cur: _autocomplete_personnages(cur))
    async def passifsearch(self, interaction: discord.Interaction, personnage: str):
        await interaction.response.defer(ephemeral=True)

        p = trouver(personnage) or PERSONNAGES.get(personnage)
        if not p:
            await interaction.followup.send("❌ Personnage introuvable.", ephemeral=True)
            return

        emb = discord.Embed(
            title=f"🔎 {p['nom']}",
            description=(
                f"**Rareté** : {p.get('rarete','?')}\n"
                f"**Faction** : {p.get('faction','?')}\n"
                f"**Passif** : **{p.get('passif',{}).get('nom','?')}**\n"
                f"> {p.get('passif',{}).get('effet','')}"
            ),
            color=discord.Color.blurple()
        )
        # debug : affiche le code interne si mappé
        try:
            pname = p.get("passif", {}).get("nom")
            if pname in PASSIF_CODE_MAP:
                emb.set_footer(text=f"Code interne: {PASSIF_CODE_MAP[pname]}")
        except Exception:
            pass

        await interaction.followup.send(embed=emb, ephemeral=True)


# ─────────────────────────────────────────────────────────────
# Autocomplete (ASYNC obligatoire)
# ─────────────────────────────────────────────────────────────
async def _autocomplete_personnages(current: str) -> List[app_commands.Choice[str]]:
    cur = (current or "").strip().lower()
    noms = get_tous_les_noms()
    out: List[app_commands.Choice[str]] = []
    if not cur:
        for n in noms[:25]:
            out.append(app_commands.Choice(name=n, value=n))
        return out

    for n in noms:
        if cur in n.lower():
            out.append(app_commands.Choice(name=n, value=n))
        if len(out) >= 25:
            break
    return out


async def setup(bot: commands.Bot):
    await init_passifs_db()
    await bot.add_cog(PassifsCog(bot))

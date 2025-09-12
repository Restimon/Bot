# cogs/equip_cog.py
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands
from typing import List, Optional

from personnage import PERSONNAGES, trouver, get_tous_les_noms
from passifs import (
    init_passifs_db,
    set_equipped,
    get_equipped_name,
)
# Facultatif : si tu veux afficher le code interne du passif
from personnage import PASSIF_CODE_MAP  # déjà importé par passifs.py aussi


class EquipCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ─────────────────────────────────────────────────────────
    # Slash: /equip <personnage>
    # ─────────────────────────────────────────────────────────
    @app_commands.command(name="equip", description="Équipe un personnage pour activer son passif.")
    @app_commands.describe(personnage="Nom exact ou partiel (auto-complétion).")
    @app_commands.autocomplete(personnage=lambda i, cur: autocomplete_personnages(cur))
    async def equip(self, interaction: discord.Interaction, personnage: str):
        await interaction.response.defer(ephemeral=True)

        # Recherche conviviale
        p = trouver(personnage) or PERSONNAGES.get(personnage)
        if not p:
            await interaction.followup.send("❌ Personnage introuvable. Vérifie l’orthographe.", ephemeral=True)
            return

        ok = await set_equipped(interaction.user.id, p["nom"])
        if not ok:
            await interaction.followup.send("❌ Impossible d'équiper ce personnage.", ephemeral=True)
            return

        # Embed de confirmation
        emb = discord.Embed(
            title=f"✅ Équipé : {p['nom']}",
            description=(
                f"**Rareté** : {p.get('rarete','?')}\n"
                f"**Faction** : {p.get('faction','?')}\n"
                f"**Passif** : **{p.get('passif',{}).get('nom','?')}**\n"
                f"> {p.get('passif',{}).get('effet','')}"
            ),
            color=discord.Color.blurple()
        )
        # Si tu as un lien accessible publiquement, tu peux mettre emb.set_thumbnail(url=...)
        # Ici c'est un chemin local, donc on n'ajoute pas d'image Discord.
        await interaction.followup.send(embed=emb, ephemeral=True)

    # ─────────────────────────────────────────────────────────
    # Slash: /unequip
    # ─────────────────────────────────────────────────────────
    @app_commands.command(name="unequip", description="Déséquipe ton personnage (désactive les passifs).")
    async def unequip(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        # Unequip = set_equipped vers un placeholder ? On supprime l'entrée.
        # On va simplement supprimer l’entrée dans la table.
        # passifs.py n’a pas de remove: faisons-le ici proprement.
        removed = await _remove_equipped(interaction.user.id)
        if not removed:
            await interaction.followup.send("ℹ️ Tu n’avais aucun personnage équipé.", ephemeral=True)
            return

        await interaction.followup.send("🗑️ Personnage déséquipé. Passifs désactivés.", ephemeral=True)

    # ─────────────────────────────────────────────────────────
    # Slash: /passif (affiche son perso équipé)
    # ─────────────────────────────────────────────────────────
    @app_commands.command(name="passif", description="Affiche ton personnage équipé et son passif.")
    async def passif(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        name = await get_equipped_name(interaction.user.id)
        if not name:
            await interaction.followup.send("❌ Aucun personnage équipé. Utilise `/equip`.", ephemeral=True)
            return
        p = PERSONNAGES.get(name)
        if not p:
            await interaction.followup.send("❌ Données du personnage introuvables.", ephemeral=True)
            return

        emb = discord.Embed(
            title=f"🎴 Équipement : {p['nom']}",
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
    # Slash: /whois @membre
    # ─────────────────────────────────────────────────────────
    @app_commands.command(name="whois", description="Affiche le personnage équipé d’un membre.")
    @app_commands.describe(membre="Le membre à inspecter.")
    async def whois(self, interaction: discord.Interaction, membre: Optional[discord.Member] = None):
        await interaction.response.defer(ephemeral=True)
        target = membre or interaction.user
        name = await get_equipped_name(target.id)
        if not name:
            await interaction.followup.send(f"ℹ️ **{target.display_name}** n’a aucun personnage équipé.", ephemeral=True)
            return
        p = PERSONNAGES.get(name)
        if not p:
            await interaction.followup.send("❌ Données du personnage introuvables.", ephemeral=True)
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


# ─────────────────────────────────────────────────────────────
# Helpers d’auto-complétion et DB utils
# ─────────────────────────────────────────────────────────────

async def autocomplete_personnages(current: str) -> List[app_commands.Choice[str]]:
    """
    Auto-complétion simple : filtre par substring insensitive via `trouver`.
    """
    current = (current or "").strip()
    noms = get_tous_les_noms()
    # Si rien saisi → top N (limité à 20 par Discord)
    if not current:
        subset = noms[:20]
    else:
        # Filtre par substring "conviviale"
        subset = []
        cur_lower = current.lower()
        for n in noms:
            if cur_lower in n.lower():
                subset.append(n)
            if len(subset) >= 20:
                break
        # fallback : si rien, propose quelques noms quand même
        if not subset:
            subset = noms[:10]
    return [app_commands.Choice(name=n, value=n) for n in subset]


# Petite utilitaire locale : suppression d’équipement
async def _remove_equipped(user_id: int) -> bool:
    import aiosqlite
    DB_PATH = "gotvalis.sqlite3"
    async with aiosqlite.connect(DB_PATH) as db:
        # check exist
        async with db.execute("SELECT 1 FROM player_equipment WHERE user_id=?", (str(user_id),)) as cur:
            row = await cur.fetchone()
        if not row:
            return False
        await db.execute("DELETE FROM player_equipment WHERE user_id=?", (str(user_id),))
        await db.commit()
    return True


# ─────────────────────────────────────────────────────────────
# Setup (chargé par main.py)
# ─────────────────────────────────────────────────────────────

async def setup(bot: commands.Bot):
    # Init DB passifs au chargement du cog
    await init_passifs_db()
    await bot.add_cog(EquipCog(bot))

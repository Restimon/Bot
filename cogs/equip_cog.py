# cogs/equip_cog.py
from __future__ import annotations

from typing import List, Optional

import aiosqlite
import discord
from discord import app_commands
from discord.ext import commands

from personnage import PERSONNAGES, trouver, get_tous_les_noms
from passifs import init_passifs_db, set_equipped, get_equipped_name, get_equipped_code


DB_PATH = "gotvalis.sqlite3"


class EquipCog(commands.Cog):
    """Équiper / déséquiper un personnage et afficher le passif actif."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ─────────────────────────────────────────────────────────
    # /equip <personnage>
    # ─────────────────────────────────────────────────────────
    @app_commands.command(
        name="equip",
        description="Équipe un personnage pour activer son passif.",
    )
    @app_commands.describe(personnage="Nom exact ou partiel (auto-complétion)")
    async def equip(self, interaction: discord.Interaction, personnage: str):
        await interaction.response.defer(ephemeral=True)

        # Recherche tolérante (slug / casse / partial)
        p = trouver(personnage) or PERSONNAGES.get(personnage)
        if not p:
            return await interaction.followup.send(
                "❌ Personnage introuvable. Vérifie l’orthographe ou utilise l’auto-complétion.",
                ephemeral=True,
            )

        ok = await set_equipped(interaction.user.id, p["nom"])
        if not ok:
            return await interaction.followup.send(
                "❌ Impossible d’équiper ce personnage.",
                ephemeral=True,
            )

        emb = discord.Embed(
            title=f"✅ Équipé : {p['nom']}",
            description=(
                f"**Rareté** : {p.get('rarete','?')}\n"
                f"**Faction** : {p.get('faction','?')}\n"
                f"**Passif** : **{p.get('passif',{}).get('nom','?')}**\n"
                f"> {p.get('passif',{}).get('effet','')}"
            ),
            color=discord.Color.blurple(),
        )

        # Si l'image est une URL publique, on l'affiche
        img = str(p.get("image") or "")
        if img.startswith("http://") or img.startswith("https://"):
            emb.set_thumbnail(url=img)

        await interaction.followup.send(embed=emb, ephemeral=True)

    # Auto-completion du nom de personnage
    @equip.autocomplete("personnage")
    async def _equip_autocomplete(
        self, itx: discord.Interaction, current: str
    ) -> List[app_commands.Choice[str]]:
        noms = get_tous_les_noms()
        cur = (current or "").strip().lower()
        if cur:
            noms = [n for n in noms if cur in n.lower()]
        return [app_commands.Choice(name=n, value=n) for n in noms[:25]]

    # ─────────────────────────────────────────────────────────
    # /unequip
    # ─────────────────────────────────────────────────────────
    @app_commands.command(
        name="unequip",
        description="Déséquipe ton personnage (désactive les passifs).",
    )
    async def unequip(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        removed = await _remove_equipped(interaction.user.id)
        if not removed:
            return await interaction.followup.send(
                "ℹ️ Tu n’avais aucun personnage équipé.",
                ephemeral=True,
            )
        await interaction.followup.send(
            "🗑️ Personnage déséquipé. Passifs désactivés.",
            ephemeral=True,
        )

    # ─────────────────────────────────────────────────────────
    # /passif — affiche TON perso équipé & son passif
    # ─────────────────────────────────────────────────────────
    @app_commands.command(
        name="passif",
        description="Affiche ton personnage équipé et son passif.",
    )
    async def passif(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        name = await get_equipped_name(interaction.user.id)
        if not name:
            return await interaction.followup.send(
                "❌ Aucun personnage équipé. Utilise `/equip`.",
                ephemeral=True,
            )

        p = PERSONNAGES.get(name)
        if not p:
            return await interaction.followup.send(
                "❌ Données du personnage introuvables.",
                ephemeral=True,
            )

        code = await get_equipped_code(interaction.user.id) or "—"

        emb = discord.Embed(
            title=f"🎴 {p['nom']} — `{code}`",
            description=(
                f"**Rareté** : {p.get('rarete','?')}\n"
                f"**Faction** : {p.get('faction','?')}\n"
                f"**Passif** : **{p.get('passif',{}).get('nom','?')}**\n"
                f"> {p.get('passif',{}).get('effet','')}"
            ),
            color=discord.Color.gold(),
        )

        img = str(p.get("image") or "")
        if img.startswith("http://") or img.startswith("https://"):
            emb.set_thumbnail(url=img)

        await interaction.followup.send(embed=emb, ephemeral=True)

    # ─────────────────────────────────────────────────────────
    # /whois — affiche le perso équipé d’un autre membre
    # ─────────────────────────────────────────────────────────
    @app_commands.command(
        name="whois",
        description="Affiche le personnage équipé d’un membre.",
    )
    @app_commands.describe(membre="Le membre à inspecter")
    async def whois(
        self, interaction: discord.Interaction, membre: Optional[discord.Member] = None
    ):
        await interaction.response.defer(ephemeral=True)
        target = membre or interaction.user
        name = await get_equipped_name(target.id)
        if not name:
            return await interaction.followup.send(
                f"ℹ️ **{target.display_name}** n’a aucun personnage équipé.",
                ephemeral=True,
            )

        p = PERSONNAGES.get(name)
        if not p:
            return await interaction.followup.send(
                "❌ Données du personnage introuvables.",
                ephemeral=True,
            )

        code = await get_equipped_code(target.id) or "—"

        emb = discord.Embed(
            title=f"🧭 {target.display_name} — {p['nom']} (`{code}`)",
            description=(
                f"**Rareté** : {p.get('rarete','?')}\n"
                f"**Faction** : {p.get('faction','?')}\n"
                f"**Passif** : **{p.get('passif',{}).get('nom','?')}**\n"
                f"> {p.get('passif',{}).get('effet','')}"
            ),
            color=discord.Color.green(),
        )

        img = str(p.get("image") or "")
        if img.startswith("http://") or img.startswith("https://"):
            emb.set_thumbnail(url=img)

        await interaction.followup.send(embed=emb, ephemeral=True)


# ─────────────────────────────────────────────────────────────
# Helpers DB
# ─────────────────────────────────────────────────────────────
async def _remove_equipped(user_id: int) -> bool:
    """Supprime l’entrée d’équipement (désactive les passifs)."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT 1 FROM player_equipment WHERE user_id=?",
            (str(user_id),),
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return False
        await db.execute(
            "DELETE FROM player_equipment WHERE user_id=?",
            (str(user_id),),
        )
        await db.commit()
    return True


# ─────────────────────────────────────────────────────────────
# Setup
# ─────────────────────────────────────────────────────────────
async def setup(bot: commands.Bot):
    # S’assure que la DB des passifs existe
    await init_passifs_db()
    await bot.add_cog(EquipCog(bot))

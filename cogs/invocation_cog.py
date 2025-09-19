# cogs/invocation_cog.py
from __future__ import annotations

import os
from pathlib import Path
from typing import List, Tuple, Optional

import aiosqlite
import discord
from discord import app_commands
from discord.ext import commands

# Pool & tirage depuis data/personnage.py (tes fonctions/données)
try:
    from data.personnage import tirage_personnage  # -> (rarete: str, perso: dict)
except Exception as e:
    tirage_personnage = None  # type: ignore

# DB partagée avec le reste du bot
try:
    from economy_db import DB_PATH as DB_PATH  # type: ignore
except Exception:
    DB_PATH = "gotvalis.sqlite3"

# ──────────────────────────────────────────────────────────────
# Tickets (même table que /daily)
# ──────────────────────────────────────────────────────────────
CREATE_TICKETS_SQL = """
CREATE TABLE IF NOT EXISTS tickets (
    user_id INTEGER PRIMARY KEY,
    count   INTEGER NOT NULL
);
"""

async def _ensure_tables():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(CREATE_TICKETS_SQL)
        await db.commit()

async def _get_tickets(uid: int) -> int:
    await _ensure_tables()
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT count FROM tickets WHERE user_id=?", (uid,))
        row = await cur.fetchone(); await cur.close()
        return int(row[0]) if row else 0

async def _add_tickets(uid: int, delta: int) -> int:
    """Ajoute (ou retire) des tickets et retourne le nouveau total."""
    await _ensure_tables()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO tickets(user_id, count) VALUES(?, 0) "
            "ON CONFLICT(user_id) DO NOTHING",
            (uid,),
        )
        await db.execute("UPDATE tickets SET count = MAX(0, count + ?) WHERE user_id=?", (delta, uid))
        await db.commit()
        cur = await db.execute("SELECT count FROM tickets WHERE user_id=?", (uid,))
        row = await cur.fetchone(); await cur.close()
        return int(row[0]) if row else 0

# ──────────────────────────────────────────────────────────────
# Utilitaire image locale -> pièce jointe
# ──────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent  # racine du projet (où se trouve /assets généralement)

def _image_file_for_character(perso: dict) -> Optional[discord.File]:
    """
    Si 'image' dans le dict du personnage pointe vers un fichier local existant,
    on renvoie un discord.File pour l'attacher et pouvoir set_image(attachment://...).
    """
    path_str = str(perso.get("image") or "").strip()
    if not path_str:
        return None
    # Chemin relatif à la racine du projet
    img_path = (PROJECT_ROOT / path_str).resolve()
    # Sécurité: l'image doit rester dans le projet
    try:
        project_real = PROJECT_ROOT.resolve()
        if project_real not in img_path.parents and img_path != project_real:
            return None
    except Exception:
        pass
    if not img_path.exists() or not img_path.is_file():
        return None
    # Nom de fichier sûr pour l'attachment
    safe_name = img_path.name
    try:
        return discord.File(str(img_path), filename=safe_name)
    except Exception:
        return None

# ──────────────────────────────────────────────────────────────
# Cog
# ──────────────────────────────────────────────────────────────
class Invocation(commands.Cog):
    """Invoque un personnage défini dans data/personnage.py en consommant des tickets."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="invocation", description="Utilise tes tickets pour invoquer un personnage.")
    @app_commands.describe(tirages="Nombre d'invocations (1–10)")
    async def invocation(self, interaction: discord.Interaction, tirages: app_commands.Range[int, 1, 10] = 1):
        if not interaction.guild:
            return await interaction.response.send_message("Commande utilisable en serveur uniquement.", ephemeral=True)

        if tirage_personnage is None:
            return await interaction.response.send_message("⚠️ Le module `data/personnage.py` est introuvable ou invalide.", ephemeral=True)

        await interaction.response.defer(ephemeral=False)

        uid = interaction.user.id
        have = await _get_tickets(uid)
        if have < tirages:
            return await interaction.followup.send(
                f"❌ Pas assez de tickets. Il te faut **{tirages}**, tu en as **{have}**."
            )

        # Consomme d'abord (anti double-clic)
        await _add_tickets(uid, -tirages)

        # Tirages
        results: List[Tuple[str, dict]] = []
        for _ in range(tirages):
            r, p = tirage_personnage()  # r = "Rare/Épique/..." ; p = dict perso
            if not p:  # sécurité
                continue
            results.append((r, p))

        remaining = await _get_tickets(uid)

        # Embed résultat
        e = discord.Embed(title="🔮 Résultat de l’invocation", color=discord.Color.purple())
        lines = [f"• **{p.get('nom', 'Inconnu')}** — *{r}*" for (r, p) in results]
        e.description = "\n".join(lines) if lines else "Aucun résultat."

        e.add_field(name="🎟 Tickets", value=f"−{tirages} (reste: {remaining})", inline=True)

        # Image si tirage unique et image dispo
        files: List[discord.File] = []
        if len(results) == 1:
            img_file = _image_file_for_character(results[0][1])
            if img_file:
                files.append(img_file)
                e.set_image(url=f"attachment://{img_file.filename}")

        if files:
            await interaction.followup.send(embed=e, files=files)
        else:
            await interaction.followup.send(embed=e)

async def setup(bot: commands.Bot):
    await bot.add_cog(Invocation(bot))

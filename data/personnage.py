# cogs/invocation_cog.py
from __future__ import annotations

import os
from pathlib import Path
from typing import List, Tuple, Optional

import aiosqlite
import discord
from discord import app_commands
from discord.ext import commands

# --- Tirage & utils depuis data/personnage.py ---
try:
    from data.personnage import tirage_personnage, generer_slug  # type: ignore
except Exception:
    tirage_personnage = None  # type: ignore
    generer_slug = lambda s: s  # type: ignore

# --- DB partagée ---
try:
    from economy_db import DB_PATH as DB_PATH  # type: ignore
except Exception:
    DB_PATH = "gotvalis.sqlite3"

# --- Tables (tickets déjà utilisées par /daily) ---
CREATE_TICKETS_SQL = """
CREATE TABLE IF NOT EXISTS tickets (
    user_id INTEGER PRIMARY KEY,
    count   INTEGER NOT NULL
);
"""
CREATE_OWNED_SQL = """
CREATE TABLE IF NOT EXISTS gacha_owned (
    user_id INTEGER NOT NULL,
    char_id TEXT    NOT NULL,
    PRIMARY KEY (user_id, char_id)
);
"""
CREATE_EQUIPPED_SQL = """
CREATE TABLE IF NOT EXISTS equipped_character (
    user_id INTEGER PRIMARY KEY,
    char_id TEXT NOT NULL
);
"""

async def _ensure_tables():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(CREATE_TICKETS_SQL)
        await db.execute(CREATE_OWNED_SQL)
        await db.execute(CREATE_EQUIPPED_SQL)
        await db.commit()

async def _get_tickets(uid: int) -> int:
    await _ensure_tables()
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT count FROM tickets WHERE user_id=?", (uid,))
        row = await cur.fetchone(); await cur.close()
        return int(row[0]) if row else 0

async def _add_tickets(uid: int, delta: int) -> int:
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

async def _own_char(uid: int, char_slug: str) -> bool:
    """True si nouveau, False si doublon."""
    await _ensure_tables()
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute("INSERT INTO gacha_owned(user_id, char_id) VALUES (?, ?)", (uid, char_slug))
            await db.commit()
            return True
        except Exception:
            return False

async def _count_owned(uid: int) -> int:
    await _ensure_tables()
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT COUNT(*) FROM gacha_owned WHERE user_id=?", (uid,))
        row = await cur.fetchone(); await cur.close()
        return int(row[0]) if row else 0

async def _get_equipped(uid: int) -> Optional[str]:
    await _ensure_tables()
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT char_id FROM equipped_character WHERE user_id=?", (uid,))
        row = await cur.fetchone(); await cur.close()
        return str(row[0]) if row and row[0] else None

async def _set_equipped(uid: int, char_slug: str):
    await _ensure_tables()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO equipped_character(user_id, char_id) VALUES (?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET char_id=excluded.char_id",
            (uid, char_slug),
        )
        await db.commit()

# --- Gestion image locale/URL ---
PROJECT_ROOT = Path(__file__).resolve().parent.parent  # racine du projet

def _image_attachment_for(perso: dict) -> tuple[Optional[discord.File], Optional[str]]:
    """
    Retourne (file, url) :
      - si 'image' est un chemin local existant → (discord.File, attachment://...)
      - si 'image' est une URL http(s)        → (None, url)
      - sinon                                  → (None, None)
    """
    img = str(perso.get("image") or "").strip()
    if not img:
        return None, None
    if img.startswith("http://") or img.startswith("https://"):
        return None, img

    img_path = (PROJECT_ROOT / img).resolve()
    try:
        project_real = PROJECT_ROOT.resolve()
        if project_real not in img_path.parents and img_path != project_real:
            return None, None
    except Exception:
        return None, None
    if not img_path.exists() or not img_path.is_file():
        return None, None

    f = discord.File(str(img_path), filename=img_path.name)
    return f, f"attachment://{img_path.name}"

# ============================================================================

class Invocation(commands.Cog):
    """Invoque un personnage défini dans data/personnage.py en consommant des tickets."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="invocation", description="Utilise tes tickets pour invoquer un personnage.")
    @app_commands.describe(tirages="Nombre d'invocations (1–10)")
    async def invocation(self, interaction: discord.Interaction, tirages: app_commands.Range[int, 1, 10] = 1):
        if not interaction.guild:
            return await interaction.response.send_message("Commande serveur uniquement.", ephemeral=True)

        if tirage_personnage is None:
            return await interaction.response.send_message("⚠️ `data/personnage.py` introuvable ou invalide.", ephemeral=True)

        await interaction.response.defer(ephemeral=False)

        uid = interaction.user.id
        have = await _get_tickets(uid)
        if have < tirages:
            return await interaction.followup.send(
                f"❌ Pas assez de tickets. Il te faut **{tirages}**, tu en as **{have}**."
            )

        # Consommer (anti double-clic)
        await _add_tickets(uid, -tirages)

        # Tirages via data/personnage.tirage_personnage()
        results: List[Tuple[str, dict, bool]] = []  # (rarete, perso, is_new)
        new_count = 0
        for _ in range(tirages):
            rarete, perso = tirage_personnage()  # ex: "Rare", {nom, rarete, image, ...}
            if not perso or not perso.get("nom"):
                continue
            slug = generer_slug(perso["nom"])
            is_new = await _own_char(uid, slug)
            if is_new:
                new_count += 1
            results.append((rarete, perso, is_new))

        remaining = await _get_tickets(uid)
        owned_total = await _count_owned(uid)

        # Auto-equip si rien d'équipé
        equipped_before = await _get_equipped(uid)
        equip_line = "🧬 Personnage équipé inchangé."
        if equipped_before is None and results:
            first_slug = generer_slug(results[0][1]["nom"])
            await _set_equipped(uid, first_slug)
            equip_line = f"🧬 **Équipé automatiquement** : {results[0][1]['nom']}"

        # Embed
        e = discord.Embed(title="🔮 Résultat de l’invocation", color=discord.Color.purple())
        lines = []
        for rarete, p, is_new in results:
            tag = " — 🆕" if is_new else ""
            lines.append(f"{p.get('nom','Inconnu')} — *{rarete}*{tag}")
        e.description = "\n".join(lines) if lines else "Aucun résultat."

        e.add_field(name="🎟 Tickets", value=f"−{tirages} (reste: {remaining})", inline=True)
        e.add_field(name="📚 Collection", value=f"{owned_total} possédés (+{new_count} nouveaux)", inline=True)
        e.add_field(name="Équipement", value=equip_line, inline=False)
        e.set_footer(text="Astuce: /invocation 10 pour une multi.")

        files: List[discord.File] = []
        if len(results) == 1:
            f, url = _image_attachment_for(results[0][1])
            if f:
                files.append(f); e.set_image(url=url)  # attachment://...
            elif url:
                e.set_image(url=url)

        if files:
            await interaction.followup.send(embed=e, files=files)
        else:
            await interaction.followup.send(embed=e)

    @app_commands.command(name="invocation_pool", description="Affiche quelques personnages invocables.")
    async def invocation_pool(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        # Petit aperçu : on fait 8 tirages “virtuels” pour illustrer les raretés
        if tirage_personnage is None:
            return await interaction.followup.send("⚠️ `data/personnage.py` introuvable.", ephemeral=True)
        seen = []
        for _ in range(20):
            r, p = tirage_personnage()
            if p and p.get("nom") and p["nom"] not in seen:
                seen.append(p["nom"])
            if len(seen) >= 8:
                break
        if not seen:
            return await interaction.followup.send("Aucun personnage détecté dans le module.", ephemeral=True)
        e = discord.Embed(title="📜 Pool d’invocation (échantillon)", description="\n".join(f"• {n}" for n in seen), color=discord.Color.green())
        await interaction.followup.send(embed=e, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Invocation(bot))

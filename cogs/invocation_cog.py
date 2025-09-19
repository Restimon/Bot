# cogs/invocation_cog.py
from __future__ import annotations

from pathlib import Path
from typing import List, Tuple, Optional

import aiosqlite
import discord
from discord import app_commands
from discord.ext import commands

# ── données & tirage depuis data/personnage.py (OBLIGATOIRE) ────────────────
try:
    from data.personnage import (
        PERSONNAGES_LIST,
        tirage_personnage,      # -> (rarete: str, perso: dict)
        generer_slug,           # -> str
    )
except Exception:
    PERSONNAGES_LIST = None      # type: ignore
    tirage_personnage = None     # type: ignore
    generer_slug = lambda s: s   # type: ignore

# ── DB partagée ─────────────────────────────────────────────────────────────
try:
    from economy_db import DB_PATH as DB_PATH  # type: ignore
except Exception:
    DB_PATH = "gotvalis.sqlite3"

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

# ── images (assets/personnage/*.png en local OU URL) ────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent

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

# ── sécurité : on REFUSE si data/personnage.py n’est pas lisible ────────────
def _must_have_personnages() -> Optional[str]:
    if PERSONNAGES_LIST is None or not isinstance(PERSONNAGES_LIST, list) or len(PERSONNAGES_LIST) == 0:
        return "Le module `data/personnage.py` est introuvable ou la liste `PERSONNAGES_LIST` est vide."
    if tirage_personnage is None or not callable(tirage_personnage):
        return "La fonction `tirage_personnage()` est introuvable dans `data/personnage.py`."
    return None

# ============================================================================

class Invocation(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="invocation", description="Utilise tes tickets pour invoquer un personnage.")
    @app_commands.describe(tirages="Nombre d'invocations (1–10)")
    async def invocation(self, interaction: discord.Interaction, tirages: app_commands.Range[int, 1, 10] = 1):
        if not interaction.guild:
            return await interaction.response.send_message("Commande serveur uniquement.", ephemeral=True)

        err = _must_have_personnages()
        if err:
            return await interaction.response.send_message(f"⚠️ {err}", ephemeral=True)

        await interaction.response.defer(ephemeral=False)

        uid = interaction.user.id
        have = await _get_tickets(uid)
        if have < tirages:
            return await interaction.followup.send(
                f"❌ Pas assez de tickets. Il te faut **{tirages}**, tu en as **{have}**."
            )

        # anti double-clic
        await _add_tickets(uid, -tirages)

        results: List[Tuple[str, dict, bool]] = []
        new_count = 0
        for _ in range(tirages):
            rarete, perso = tirage_personnage()  # -> ("Rare", { "nom": ..., "image": ..., "passif": {...} })
            if not perso or not perso.get("nom"):
                continue
            slug = generer_slug(perso["nom"])
            is_new = await _own_char(uid, slug)
            if is_new:
                new_count += 1
            results.append((rarete, perso, is_new))

        remaining = await _get_tickets(uid)
        owned_total = await _count_owned(uid)

        # auto-equip si rien
        equip_line = "🧬 Personnage équipé inchangé."
        if results and (await _get_equipped(uid)) is None:
            first_slug = generer_slug(results[0][1]["nom"])
            await _set_equipped(uid, first_slug)
            equip_line = f"🧬 **Équipé automatiquement** : {results[0][1]['nom']}"

        # embed
        e = discord.Embed(title="🔮 Résultat de l’invocation", color=discord.Color.purple())

        # Tirage unique → on affiche nom + description + capacité + image
        files: List[discord.File] = []
        if len(results) == 1:
            rarete, p, is_new = results[0]
            nom = p.get("nom", "Inconnu")
            faction = p.get("faction", "—")
            desc = p.get("description", "—")
            passif = p.get("passif") or {}
            cap_nom = passif.get("nom", "Capacité")
            cap_effet = passif.get("effet", "—")

            nouveau = " — 🆕" if is_new else ""
            e.description = f"**{nom}** — *{rarete}* ({faction}){nouveau}"
            e.add_field(name="Description", value=desc, inline=False)
            e.add_field(name="Capacité", value=f"**{cap_nom}**\n{cap_effet}", inline=False)

            f, url = _image_attachment_for(p)
            if f:
                files.append(f); e.set_image(url=url)
            elif url:
                e.set_image(url=url)

        else:
            # Multi → liste compacte
            lines = []
            for rarete, p, is_new in results:
                tag = " — 🆕" if is_new else ""
                lines.append(f"{p.get('nom','Inconnu')} — *{rarete}*{tag}")
            e.description = "\n".join(lines) if lines else "Aucun résultat."

        # Infos tickets / collection / équipement
        e.add_field(name="🎟 Tickets", value=f"−{tirages} (reste: {remaining})", inline=True)
        e.add_field(name="📚 Collection", value=f"{owned_total} possédés (+{new_count} nouveaux)", inline=True)
        e.add_field(name="Équipement", value=equip_line, inline=False)
        e.set_footer(text="Astuce: /invocation 10 pour une multi.")

        if files:
            await interaction.followup.send(embed=e, files=files)
        else:
            await interaction.followup.send(embed=e)

    @app_commands.command(name="invocation_pool", description="Affiche quelques personnages invocables.")
    async def invocation_pool(self, interaction: discord.Interaction):
        err = _must_have_personnages()
        if err:
            return await interaction.response.send_message(f"⚠️ {err}", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        sample = [p.get("nom") for p in PERSONNAGES_LIST[:10] if isinstance(p, dict) and p.get("nom")]
        e = discord.Embed(
            title="📜 Pool d’invocation (aperçu)",
            description="\n".join(f"• {n}" for n in sample) if sample else "—",
            color=discord.Color.green(),
        )
        await interaction.followup.send(embed=e, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Invocation(bot))

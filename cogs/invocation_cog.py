# cogs/invocation_cog.py
from __future__ import annotations

from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any

import aiosqlite
import discord
from discord import app_commands
from discord.ext import commands

# ─────────────────────────────────────────────────────────────
# Chargement ROBUSTE des personnages & utilitaires de tirage
# ─────────────────────────────────────────────────────────────
# On essaie d'abord data/personnage.py (package "data"),
# puis on retombe sur le fichier racine personnage.py.
PERSONNAGES_LIST: List[Dict[str, Any]] = []
_generer_slug = None
_tirage_personnage = None

# 1) Tentative: data.personnage
try:
    from data.personnage import PERSONNAGES_LIST as _DATA_LIST  # type: ignore
    PERSONNAGES_LIST = list(_DATA_LIST or [])
except Exception as e:
    print(f"[invocation_cog] Import data.personnage KO → {e!r}")

# 2) Fallback: personnage.py (racine)
if not PERSONNAGES_LIST:
    try:
        from personnage import PERSONNAGES as _PERSOS_DICT  # type: ignore
        PERSONNAGES_LIST = [dict(p) for p in _PERSOS_DICT.values()]
        for p in PERSONNAGES_LIST:
            p.setdefault("invocable", True)
        print(f"[invocation_cog] Fallback OK: PERSONNAGES_LIST depuis personnage.py ({len(PERSONNAGES_LIST)})")
    except Exception as e2:
        print(f"[invocation_cog] Fallback personnage.py KO → {e2!r}")

# 3) Utils: generer_slug / tirage_personnage (depuis personnage.py si dispo)
try:
    from personnage import generer_slug as _generer_slug  # type: ignore
except Exception:
    pass
try:
    from personnage import tirage_personnage as _tirage_personnage  # type: ignore
except Exception:
    pass

def generer_slug(name: str) -> str:
    if callable(_generer_slug):
        return _generer_slug(name)  # type: ignore
    # mini version locale (sans accents)
    import unicodedata
    s = unicodedata.normalize("NFKD", str(name))
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.lower().strip().replace(" ", "-")
    return "".join(ch for ch in s if ch.isalnum() or ch == "-")

def tirage_personnage() -> Tuple[str, Dict[str, Any]]:
    if callable(_tirage_personnage):
        return _tirage_personnage()  # type: ignore
    # fallback simple: choisit un perso aléatoire et déduit sa rareté
    import random
    if not PERSONNAGES_LIST:
        return "Commun", {}
    p = random.choice(PERSONNAGES_LIST)
    return str(p.get("rarete", "Commun")), p

# ─────────────────────────────────────────────────────────────
# DB partagée (même fichier que /daily, /economy, etc.)
# ─────────────────────────────────────────────────────────────
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

async def _own_char(uid: int, char_slug: str) -> bool:
    """Enregistre un perso possédé ; True si nouveau, False si doublon."""
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

# ─────────────────────────────────────────────────────────────
# Utils image tolérants: assets/personnage(s)/, accents, apostrophes
# ─────────────────────────────────────────────────────────────
import unicodedata

PROJECT_ROOT = Path(__file__).resolve().parent.parent

def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return s.lower().strip()

def _try_file(p: Path) -> Optional[Path]:
    try:
        if p.exists() and p.is_file():
            return p
    except Exception:
        pass
    return None

def _find_by_name(name: str) -> Optional[Path]:
    bases = [PROJECT_ROOT / "assets" / "personnage",
             PROJECT_ROOT / "assets" / "personnages"]
    targets = {_norm(name), _norm(name).replace(" ", "-"), _norm(name).replace(" ", "")}
    for base in bases:
        if not base.exists():
            continue
        for img in base.glob("*.png"):
            if _norm(img.stem) in targets:
                return img
    return None

def _image_file_for(perso: dict, suffix: str = "") -> Tuple[Optional[discord.File], Optional[str]]:
    """
    Retourne (file, safe_filename_or_url).
    - URL http(s) -> (None, url)
    - Fichier local -> (discord.File, 'inv{suffix or _1}.png') pour set_image('attachment://...')
    """
    img = str(perso.get("image") or "").strip()
    name = str(perso.get("nom") or "").strip()

    # URL directe
    if img.startswith("http://") or img.startswith("https://"):
        return None, img

    # Chemin exact (+ correction 'personnage' -> 'personnages')
    candidate: Optional[Path] = None
    if img:
        p = (PROJECT_ROOT / img).resolve()
        candidate = _try_file(p)
        if not candidate and "/personnage/" in img.replace("\\", "/"):
            p2 = (PROJECT_ROOT / img.replace("/personnage/", "/personnages/")).resolve()
            candidate = _try_file(p2)

    # Fallback par nom
    if not candidate and name:
        candidate = _find_by_name(name)

    if candidate:
        safe = f"inv{suffix or '_1'}.png"  # nom garanti sans espace/accent
        return discord.File(str(candidate), filename=safe), safe

    return None, None

# ─────────────────────────────────────────────────────────────
# Sanity check
# ─────────────────────────────────────────────────────────────
def _must_have_personnages() -> Optional[str]:
    if not isinstance(PERSONNAGES_LIST, list) or len(PERSONNAGES_LIST) == 0:
        return "Le module `data/personnage.py` est introuvable (ou vide) **et** le fallback `personnage.py` a échoué."
    return None

# ============================================================================

class Invocation(commands.Cog):
    """Invoque un personnage défini dans data/personnage.py (ou fallback racine) en consommant des tickets."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        print(f"[invocation_cog] personnages chargés: {len(PERSONNAGES_LIST)}")

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

        # Tirages
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

        # Auto-equip si rien
        equip_line = "🧬 Personnage équipé inchangé."
        if results and (await _get_equipped(uid)) is None:
            first_slug = generer_slug(results[0][1]["nom"])
            await _set_equipped(uid, first_slug)
            equip_line = f"🧬 **Équipé automatiquement** : {results[0][1]['nom']}"

        embeds: List[discord.Embed] = []
        files: List[discord.File] = []

        # Tirage unique → 1 embed détaillé (image en bas)
        if len(results) == 1:
            rarete, p, is_new = results[0]
            nom = p.get("nom", "Inconnu")
            faction = p.get("faction", "—")
            desc = p.get("description", "—")
            passif = p.get("passif") or {}
            cap_nom = passif.get("nom", "Capacité")
            cap_effet = passif.get("effet", "—")

            e = discord.Embed(title="🔮 Résultat de l’invocation", color=discord.Color.purple())
            nouveau = " — 🆕" if is_new else ""
            e.description = f"**{nom}** — *{rarete}* ({faction}){nouveau}"
            e.add_field(name="Description", value=desc, inline=False)
            e.add_field(name="Capacité", value=f"**{cap_nom}**\n{cap_effet}", inline=False)
            e.add_field(name="🎟 Tickets", value=f"−{tirages} (reste: {remaining})", inline=True)
            e.add_field(name="📚 Collection", value=f"{owned_total} possédés (+{new_count} nouveaux)", inline=True)
            e.add_field(name="Équipement", value=equip_line, inline=False)
            e.set_footer(text="Astuce: /invocation 10 pour une multi.")

            f, safe_name_or_url = _image_file_for(p, suffix="_1")
            if f and safe_name_or_url:
                files.append(f)
                e.set_image(url=f"attachment://{safe_name_or_url}")
            elif safe_name_or_url and (safe_name_or_url.startswith("http://") or safe_name_or_url.startswith("https://")):
                e.set_image(url=safe_name_or_url)

            embeds.append(e)

        # Multi → 1 embed PAR tirage (max 10)
        else:
            for idx, (rarete, p, is_new) in enumerate(results, start=1):
                nom = p.get("nom", "Inconnu")
                faction = p.get("faction", "—")
                desc = p.get("description", "—")
                passif = p.get("passif") or {}
                cap_nom = passif.get("nom", "Capacité")
                cap_effet = passif.get("effet", "—")

                e = discord.Embed(title=f"🔮 Invocation #{idx}", color=discord.Color.purple())
                nouveau = " — 🆕" if is_new else ""
                e.description = f"**{nom}** — *{rarete}* ({faction}){nouveau}"
                e.add_field(name="Description", value=desc, inline=False)
                e.add_field(name="Capacité", value=f"**{cap_nom}**\n{cap_effet}", inline=False)

                if idx == 1:
                    e.add_field(name="🎟 Tickets", value=f"−{tirages} (reste: {remaining})", inline=True)
                    e.add_field(name="📚 Collection", value=f"{owned_total} possédés (+{new_count} nouveaux)", inline=True)
                    e.add_field(name="Équipement", value=equip_line, inline=False)
                    e.set_footer(text="Astuce: /invocation 10 pour une multi.")

                f, safe_name_or_url = _image_file_for(p, suffix=f"_{idx}")
                if f and safe_name_or_url:
                    files.append(f)
                    e.set_image(url=f"attachment://{safe_name_or_url}")
                elif safe_name_or_url and (safe_name_or_url.startswith("http://") or safe_name_or_url.startswith("https://")):
                    e.set_image(url=safe_name_or_url)

                embeds.append(e)

        # Envoi (≤10 embeds et ≤10 fichiers par message)
        if files:
            await interaction.followup.send(embeds=embeds, files=files)
        else:
            await interaction.followup.send(embeds=embeds)

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

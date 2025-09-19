# cogs/invocation_cog.py
from __future__ import annotations

import random
from typing import Dict, Any, List, Optional, Tuple

import discord
from discord import app_commands
from discord.ext import commands
import aiosqlite

# DB partagée
try:
    from economy_db import DB_PATH as DB_PATH  # type: ignore
except Exception:
    DB_PATH = "gotvalis.sqlite3"


# ──────────────────────────────────────────────────────────────
# Lecture du pool depuis data/personnage.py (+ fallback)
# ──────────────────────────────────────────────────────────────
def _load_personnages() -> List[Dict[str, Any]]:
    """
    Retourne une liste standardisée:
      [{id, name, emoji, rarity, image?}, ...]
    Lit data/personnage.py en acceptant plusieurs noms/canons:
      PERSONNAGES / PERSONNAGE_POOL / POOL / CHARACTERS / LISTE / ALL...
    Chaque entrée peut être un dict avec clés {id, nom/name, emoji/icon, rarete/rarity, image/banner}.
    """
    catalog: Dict[str, Dict[str, Any]] = {}

    try:
        from data import personnage as P  # type: ignore
        candidates = [
            getattr(P, "PERSONNAGES", None),
            getattr(P, "PERSONNAGE_POOL", None),
            getattr(P, "PERSONNAGE", None),
            getattr(P, "POOL", None),
            getattr(P, "CHARACTERS", None),
            getattr(P, "LISTE", None),
            getattr(P, "ALL", None),
        ]
        for data in candidates:
            if not data:
                continue
            if isinstance(data, dict):
                it = data.items()
            elif isinstance(data, list):
                it = [(None, e) for e in data]
            else:
                continue

            for key, meta in it:
                if not isinstance(meta, dict):
                    continue
                cid = str(meta.get("id") or key or meta.get("key") or meta.get("nom") or meta.get("name") or "?")
                if cid == "?":
                    continue
                catalog[cid] = {
                    "id": cid,
                    "name": meta.get("name") or meta.get("nom") or str(cid),
                    "emoji": meta.get("emoji") or meta.get("icon") or "",
                    "rarity": int(meta.get("rarity") or meta.get("rarete") or 10),
                    "image": meta.get("image") or meta.get("banner") or None,
                }
    except Exception:
        pass

    if catalog:
        return list(catalog.values())

    # Fallback si le module est vide/absent
    return [
        {"id": "alpha", "name": "Alpha", "emoji": "🐺", "rarity": 8,  "image": None},
        {"id": "beta",  "name": "Beta",  "emoji": "🦅", "rarity": 15, "image": None},
        {"id": "gamma", "name": "Gamma", "emoji": "🐉", "rarity": 30, "image": None},
    ]


# ──────────────────────────────────────────────────────────────
# SQLite helpers
# ──────────────────────────────────────────────────────────────
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
            "INSERT INTO tickets(user_id, count) "
            "SELECT ?, 0 WHERE NOT EXISTS(SELECT 1 FROM tickets WHERE user_id=?)",
            (uid, uid),
        )
        await db.execute("UPDATE tickets SET count = MAX(0, count + ?) WHERE user_id=?", (delta, uid))
        await db.commit()
        cur = await db.execute("SELECT count FROM tickets WHERE user_id=?", (uid,))
        row = await cur.fetchone(); await cur.close()
        return int(row[0]) if row else 0

async def _own_char(uid: int, char_id: str) -> bool:
    """Ajoute un perso; True si nouveau, False si doublon."""
    await _ensure_tables()
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute("INSERT INTO gacha_owned(user_id, char_id) VALUES (?, ?)", (uid, char_id))
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

async def _set_equipped(uid: int, char_id: str):
    await _ensure_tables()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO equipped_character(user_id, char_id) VALUES (?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET char_id=excluded.char_id",
            (uid, char_id),
        )
        await db.commit()


# ──────────────────────────────────────────────────────────────
# Tirage pondéré
# ──────────────────────────────────────────────────────────────
def _weight_from_rarity(r: int) -> int:
    """Plus la rareté est grande → plus c'est rare. Poids = max(1, 100 - r)."""
    try:
        r = int(r)
    except Exception:
        r = 10
    return max(1, 100 - r)

def _pick_character(pool: List[Dict[str, Any]]) -> Dict[str, Any]:
    weights = [_weight_from_rarity(p.get("rarity", 10)) for p in pool]
    return random.choices(pool, weights=weights, k=1)[0]


# ──────────────────────────────────────────────────────────────
# Cog principal
# ──────────────────────────────────────────────────────────────
class Invocation(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.pool: List[Dict[str, Any]] = _load_personnages()

    @app_commands.command(name="invocation", description="Utilise tes tickets pour invoquer un personnage.")
    @app_commands.describe(tirages="Nombre d'invocations (1–10)")
    async def invocation(self, interaction: discord.Interaction, tirages: app_commands.Range[int, 1, 10] = 1):
        await interaction.response.defer(ephemeral=False)

        if not self.pool:
            await interaction.followup.send("⚠️ Aucun personnage disponible pour l’invocation.")
            return

        uid = interaction.user.id
        have = await _get_tickets(uid)
        if have < tirages:
            await interaction.followup.send(f"❌ Pas assez de tickets. Il te faut **{tirages}**, tu en as **{have}**.")
            return

        # Consommer d’abord (anti double-click)
        await _add_tickets(uid, -tirages)

        obtained: List[Tuple[Dict[str, Any], bool]] = []
        new_count = 0
        for _ in range(tirages):
            c = _pick_character(self.pool)
            is_new = await _own_char(uid, c["id"])
            if is_new:
                new_count += 1
            obtained.append((c, is_new))

        remaining = await _get_tickets(uid)
        owned_total = await _count_owned(uid)

        # Auto-équipement si aucun perso équipé
        equipped_before = await _get_equipped(uid)
        if equipped_before is None and obtained:
            first = obtained[0][0]
            await _set_equipped(uid, first["id"])
            equipped_line = f"🧬 **Équipé automatiquement** : {first.get('emoji','')} {first.get('name')}"
        else:
            equipped_line = "🧬 Personnage équipé inchangé."

        # Embed
        e = discord.Embed(title="🔮 Résultat de l’invocation", color=discord.Color.purple())
        lines = []
        for c, is_new in obtained:
            flag = "🆕" if is_new else "♻️ doublon"
            lines.append(f"{c.get('emoji','')} **{c.get('name')}** — {flag}")
        e.description = "\n".join(lines)
        e.add_field(name="🎟 Tickets", value=f"−{tirages} (reste: {remaining})", inline=True)
        e.add_field(name="📚 Collection", value=f"{owned_total} possédés (+{new_count} nouveaux)", inline=True)
        e.add_field(name="Équipement", value=equipped_line, inline=False)

        # Image si tirage unique et illustré
        if tirages == 1 and obtained[0][0].get("image"):
            e.set_image(url=obtained[0][0]["image"])

        e.set_footer(text="Astuce: /invocation 10 pour une multi.")
        await interaction.followup.send(embed=e)

    @app_commands.command(name="invocation_pool", description="Affiche la liste des personnages invocables.")
    async def invocation_pool(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if not self.pool:
            await interaction.followup.send("⚠️ Pool vide.")
            return
        by = sorted(self.pool, key=lambda c: int(c.get("rarity", 10)))
        lines = [f"{c.get('emoji','')} **{c.get('name')}** — rareté {c.get('rarity', '?')}" for c in by][:30]
        e = discord.Embed(title="📜 Pool d’invocation (top 30)", description="\n".join(lines), color=discord.Color.green())
        await interaction.followup.send(embed=e, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Invocation(bot))

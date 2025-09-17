# cogs/daily_cog.py
import random
import time
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

import aiosqlite

# --- DB modernes (déjà existantes dans ton projet)
from economy_db import add_balance, get_balance
from inventory_db import add_item

# --- Tirage & emojis depuis utils.py
try:
    from utils import get_random_items as _get_random_items  # doit renvoyer une liste de noms d'objets
except Exception:
    _get_random_items = None

try:
    from utils import get_item_emoji as _utils_item_emoji
except Exception:
    _utils_item_emoji = None

_UTILS_ITEMS = None
if _utils_item_emoji is None:
    try:
        from utils import ITEMS as _UTILS_ITEMS  # dict éventuel dans utils.py
    except Exception:
        _UTILS_ITEMS = None


def _item_emoji(name: str) -> str:
    """Renvoie l'emoji d'un item d'après utils.py (fonction ou dict), sinon fallback."""
    # 1) fonction utilitaire dédiée
    if _utils_item_emoji:
        try:
            em = _utils_item_emoji(name)
            if isinstance(em, str) and em.strip():
                return em
        except Exception:
            pass
    # 2) dict catalogue
    if isinstance(_UTILS_ITEMS, dict):
        meta = _UTILS_ITEMS.get(name) or _UTILS_ITEMS.get(name.lower())
        if isinstance(meta, dict):
            em = meta.get("emoji") or meta.get("icon") or meta.get("emote")
            if isinstance(em, str) and em.strip():
                return em
    # 3) fallback simple
    FALLBACK = {
        "Bouclier": "🛡️",
        "Casque": "🥽",
        "Potion de soin": "🩹",
        "Régénération": "⚡",
        "Poison": "☠️",
        "Virus": "🧬",
        "Immunité": "🛡️",
        "Évasion +": "💨",
        "Vol à la tire": "🧤",
        "Mystery Box": "🎁",
        "Ticket": "🎟️",
        "🎟️ Ticket": "🎟️",
    }
    return FALLBACK.get(name, name)


# ===============================
# Config Daily
# ===============================
DAILY_COOLDOWN_H = 24
STREAK_WINDOW_H = 48
TICKET_EMOJI = "🎟️"

# ===============================
# Base SQLite (même DB que le reste du projet)
# ===============================
try:
    from economy_db import DB_PATH as DB_PATH  # utilise le même fichier SQLite
except Exception:
    DB_PATH = "gotvalis.sqlite3"

CREATE_DAILIES_SQL = """
CREATE TABLE IF NOT EXISTS dailies (
    user_id    INTEGER PRIMARY KEY,
    last_ts    REAL NOT NULL,
    streak     INTEGER NOT NULL
);
"""

# Tickets séparés de l'inventaire (PLUS dans les objets)
CREATE_TICKETS_SQL = """
CREATE TABLE IF NOT EXISTS tickets (
    user_id INTEGER PRIMARY KEY,
    count   INTEGER NOT NULL
);
"""

# Dans certains utils, le tirage peut renvoyer "ticket" par erreur : on les ban.
TICKET_NAMES = {"Ticket", "ticket", "🎟️ Ticket", "🎟️", "Daily Ticket", "daily ticket"}


def _now() -> float:
    return time.time()


def _pick_items(n: int) -> list[str]:
    """Tire n objets via utils.py si possible, sinon fallback. Jamais de 'ticket' ici."""
    items: list[str] = []
    if _get_random_items:
        try:
            cand = _get_random_items(n)
            if isinstance(cand, list):
                items = [x for x in cand if isinstance(x, str) and x not in TICKET_NAMES]
        except Exception:
            items = []
    if not items:
        pool = [
            "Mystery Box", "Potion de soin", "Poison", "Virus", "Bouclier", "Casque",
            "Évasion +", "Immunité", "Régénération", "Vol à la tire"
        ]
        items = random.sample(pool, k=min(n, len(pool)))
    # s'assure que la taille est n
    if len(items) > n:
        items = items[:n]
    elif len(items) < n:
        # complète aléatoirement sans ticket
        pool = [p for p in [
            "Mystery Box", "Potion de soin", "Poison", "Virus", "Bouclier", "Casque",
            "Évasion +", "Immunité", "Régénération", "Vol à la tire"
        ] if p not in items]
        while len(items) < n and pool:
            items.append(pool.pop(random.randrange(len(pool))))
    return items


class Daily(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._ready = False

    async def _ensure_tables(self):
        if self._ready:
            return
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(CREATE_DAILIES_SQL)
            await db.execute(CREATE_TICKETS_SQL)
            await db.commit()
        self._ready = True

    async def _get_daily_row(self, uid: int):
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute("SELECT last_ts, streak FROM dailies WHERE user_id = ?", (uid,))
            row = await cur.fetchone()
            await cur.close()
        return row  # (last_ts, streak) or None

    async def _set_daily_row(self, uid: int, last_ts: float, streak: int):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO dailies(user_id, last_ts, streak) VALUES(?,?,?) "
                "ON CONFLICT(user_id) DO UPDATE SET last_ts=excluded.last_ts, streak=excluded.streak",
                (uid, last_ts, streak)
            )
            await db.commit()

    # --- Tickets: stock séparé (pas dans l'inventaire)
    async def _add_tickets(self, uid: int, amount: int = 1):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO tickets(user_id, count) VALUES(?, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET count = tickets.count + ?",
                (uid, amount, amount)
            )
            await db.commit()

    async def _get_tickets(self, uid: int) -> int:
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute("SELECT count FROM tickets WHERE user_id = ?", (uid,))
            row = await cur.fetchone()
            await cur.close()
        return int(row[0]) if row else 0

    @app_commands.command(name="daily", description="Récupère ta récompense quotidienne.")
    async def daily(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False, thinking=False)
        await self._ensure_tables()

        uid = interaction.user.id
        now = _now()

        # --- Cooldown / streak SQL
        row = await self._get_daily_row(uid)
        last_ts = row[0] if row else None
        prev_streak = row[1] if row else 0

        if last_ts is not None:
            elapsed_h = (now - last_ts) / 3600
            if elapsed_h < DAILY_COOLDOWN_H:
                remaining = DAILY_COOLDOWN_H - elapsed_h
                hours = int(remaining)
                minutes = int((remaining - hours) * 60)
                embed = discord.Embed(
                    title="⏳ Daily non disponible",
                    description=f"Reviens dans **{hours}h {minutes}m**.",
                    color=discord.Color.orange()
                )
                await interaction.followup.send(embed=embed)
                return

        # streak update (fenêtre 48h)
        if last_ts is None:
            streak = 1
        else:
            since_last_h = (now - last_ts) / 3600
            streak = (max(1, prev_streak) + 1) if since_last_h <= STREAK_WINDOW_H else 1

        # --- Récompenses
        base_coins = 20
        streak_bonus = min(streak, 25)
        coins_gain = base_coins + streak_bonus

        # 1 ticket (séparé de l'inventaire) + 2 items (pas de ticket)
        items = _pick_items(2)

        # --- Écritures DB
        await add_balance(uid, coins_gain, reason="daily")
        coins_after = await get_balance(uid)

        # Tickets: stock séparé
        await self._add_tickets(uid, 1)
        # Objets: seulement les deux tirés (pas de ticket)
        for it in items:
            await add_item(uid, it, 1)

        # Persist daily row
        await self._set_daily_row(uid, now, streak)

        # --- Embed (GotCoins sur la ligne 1, Tickets+Objets sur la ligne 2)
        embed = discord.Embed(
            title="🎁 Récompense quotidienne",
            description=f"Streak : **{streak}** (bonus +{streak_bonus})",
            color=discord.Color.green()
        )

        # Ligne 1 : pleine largeur
        embed.add_field(name="GotCoins gagnés", value=f"+{coins_gain}", inline=False)

        # Ligne 2 : deux colonnes
        tickets_after = await self._get_tickets(uid)
        embed.add_field(name="Tickets", value=f"{TICKET_EMOJI}×1 (total: {tickets_after})", inline=True)

        obj_emojis = " ".join(_item_emoji(n) for n in items) or "—"
        embed.add_field(name="Objets", value=obj_emojis, inline=True)

        # Ligne 3 : pleine largeur (solde)
        embed.add_field(name="Solde actuel", value=str(coins_after), inline=False)

        if last_ts:
            dt = datetime.fromtimestamp(last_ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            embed.set_footer(text=f"Dernier daily: {dt}")

        await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Daily(bot))

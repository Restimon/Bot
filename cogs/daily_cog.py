# cogs/daily_cog.py
import random
import time
from datetime import datetime, timezone
from typing import List, Tuple, Dict, Any

import discord
from discord import app_commands
from discord.ext import commands
import aiosqlite

# --- DB projets
from economy_db import add_balance, get_balance
from inventory_db import add_item

# --- Catalogue/ tirage depuis utils.py
try:
    # renvoie p.ex. ["🛡", "🧪"] (les noms SONT les emojis)
    from utils import get_random_items as _get_random_items  # type: ignore
except Exception:
    _get_random_items = None

try:
    from utils import ITEMS as ITEM_CATALOG  # dict: { "🛡": {...}, "🩹": {...}, ... }
except Exception:
    ITEM_CATALOG: Dict[str, Dict[str, Any]] = {}

# ===============================
# Config
# ===============================
DAILY_COOLDOWN_H = 24
STREAK_WINDOW_H = 48
TICKET_EMOJI = "🎟️"

# Même DB que le reste
try:
    from economy_db import DB_PATH as DB_PATH  # type: ignore
except Exception:
    DB_PATH = "gotvalis.sqlite3"

CREATE_DAILIES_SQL = """
CREATE TABLE IF NOT EXISTS dailies (
    user_id    INTEGER PRIMARY KEY,
    last_ts    REAL NOT NULL,
    streak     INTEGER NOT NULL
);
"""

# Tickets stockés séparément (pas en inventaire)
CREATE_TICKETS_SQL = """
CREATE TABLE IF NOT EXISTS tickets (
    user_id INTEGER PRIMARY KEY,
    count   INTEGER NOT NULL
);
"""

# Valeurs à filtrer si jamais le tirage utils renvoie un "ticket"
TICKET_NAMES = {"🎟️", "🎟️ Ticket", "Ticket", "ticket", "Daily Ticket", "daily ticket"}


# ===============================
# Helpers SQL
# ===============================
def _now() -> float:
    return time.time()

async def _ensure_tables():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(CREATE_DAILIES_SQL)
        await db.execute(CREATE_TICKETS_SQL)
        await db.commit()

async def _get_daily_row(uid: int):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT last_ts, streak FROM dailies WHERE user_id = ?", (uid,))
        row = await cur.fetchone()
        await cur.close()
    return row  # (last_ts, streak) or None

async def _set_daily_row(uid: int, last_ts: float, streak: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO dailies(user_id, last_ts, streak) VALUES(?,?,?) "
            "ON CONFLICT(user_id) DO UPDATE SET last_ts=excluded.last_ts, streak=excluded.streak",
            (uid, last_ts, streak)
        )
        await db.commit()

async def _add_tickets(uid: int, amount: int = 1):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO tickets(user_id, count) VALUES(?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET count = tickets.count + ?",
            (uid, amount, amount)
        )
        await db.commit()

async def _get_tickets(uid: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT count FROM tickets WHERE user_id = ?", (uid,))
        row = await cur.fetchone()
        await cur.close()
    return int(row[0]) if row else 0


# ===============================
# Sélection items & descriptions
# ===============================
def _pick_items(n: int) -> List[str]:
    """
    Tire n items depuis utils.get_random_items si dispo (les noms sont des emojis),
    en excluant tout ce qui ressemble à un ticket.
    """
    items: List[str] = []
    if _get_random_items:
        try:
            cand = _get_random_items(n)
            if isinstance(cand, list):
                items = [x for x in cand if isinstance(x, str) and x not in TICKET_NAMES]
        except Exception:
            items = []
    if not items:
        # Fallback si utils absent : petit pool d'emojis réels de ton catalogue
        fallback_pool = [k for k in ITEM_CATALOG.keys() if isinstance(k, str) and k not in TICKET_NAMES]
        if not fallback_pool:
            fallback_pool = ["🛡", "🩹", "💊", "💕", "🧪", "🧟", "🦠", "❄️", "🪓", "🔥", "⚡", "🔫", "🧨", "☠️", "📦", "🔍", "💉", "👟", "🪖", "⭐️"]
        random.shuffle(fallback_pool)
        items = fallback_pool[:n]
    # Ajuste la taille
    if len(items) > n:
        items = items[:n]
    elif len(items) < n:
        # Complète aléatoirement (sans tickets)
        pool = [k for k in ITEM_CATALOG.keys() if k not in items and k not in TICKET_NAMES]
        while len(items) < n and pool:
            items.append(pool.pop(random.randrange(len(pool))))
    return items

def _short_desc(emoji_key: str) -> str:
    """
    Produit une description courte à partir des métadonnées.
    """
    meta = ITEM_CATALOG.get(emoji_key, {}) if isinstance(ITEM_CATALOG, dict) else {}
    t = meta.get("type", "")

    if t == "attaque":
        dmg = meta.get("degats")
        return f"Dégâts {dmg}" if dmg is not None else "Attaque"
    if t == "attaque_chaine":
        dp = meta.get("degats_principal"); ds = meta.get("degats_secondaire")
        return f"Chaîne {dp}/{ds}" if dp is not None and ds is not None else "Attaque en chaîne"
    if t == "virus":
        dmg = meta.get("degats")
        return f"Virus {dmg} sur durée" if dmg is not None else "Virus"
    if t == "poison":
        dmg = meta.get("degats")
        return f"Poison {dmg}/tick" if dmg is not None else "Poison"
    if t == "infection":
        dmg = meta.get("degats")
        return f"Infection {dmg}/tick" if dmg is not None else "Infection"
    if t == "soin":
        heal = meta.get("soin")
        return f"Soigne {heal} PV" if heal is not None else "Soin"
    if t == "regen":
        val = meta.get("valeur")
        return f"Régén {val}/tick" if val is not None else "Régénération"
    if t == "mysterybox":
        return "Mystery Box"
    if t == "vol":
        return "Vol"
    if t == "vaccin":
        return "Immunise contre statut"
    if t == "bouclier":
        val = meta.get("valeur")
        return f"Bouclier {val}" if val is not None else "Bouclier"
    if t == "esquive+":
        val = meta.get("valeur")
        return f"Esquive +{int(val*100)}%" if isinstance(val, (int, float)) else "Esquive +"
    if t == "reduction":
        val = meta.get("valeur")
        return f"Réduction {int(val*100)}%" if isinstance(val, (int, float)) else "Réduction"
    if t == "immunite":
        return "Immunité"

    return emoji_key

def _format_items_lines(items: List[str]) -> List[str]:
    """Transforme ['🛡', '🩹'] -> ['1x 🛡 [Bouclier 20]', '1x 🩹 [Soigne 10 PV]']"""
    lines: List[str] = []
    for emoji in items:
        if not emoji or emoji in TICKET_NAMES:
            continue
        desc = _short_desc(emoji)
        lines.append(f"1x {emoji} [{desc}]")
    return lines

def _split_in_columns(lines: List[str], n_cols: int = 2) -> List[str]:
    if not lines:
        return ["—"]
    per_col = (len(lines) + n_cols - 1) // n_cols
    cols = []
    for i in range(n_cols):
        start = i * per_col
        block = "\n".join(lines[start:start + per_col]).strip()
        if block:
            cols.append(block)
    return cols or ["—"]


# ===============================
# Cog
# ===============================
class Daily(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="daily", description="Récupère ta récompense quotidienne.")
    async def daily(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False, thinking=False)
        await _ensure_tables()

        uid = interaction.user.id
        now = _now()

        # Cooldown / streak
        row = await _get_daily_row(uid)
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

        if last_ts is None:
            streak = 1
        else:
            since_last_h = (now - last_ts) / 3600
            streak = (max(1, prev_streak) + 1) if since_last_h <= STREAK_WINDOW_H else 1

        # Récompenses
        base_coins = 20
        streak_bonus = min(streak, 25)
        coins_gain = base_coins + streak_bonus

        # 1 ticket (séparé) + 2 items
        items = _pick_items(2)

        # Écritures
        await add_balance(uid, coins_gain, reason="daily")
        await _add_tickets(uid, 1)
        for it in items:
            await add_item(uid, it, 1)

        await _set_daily_row(uid, now, streak)

        coins_after = await get_balance(uid)
        tickets_after = await _get_tickets(uid)

        # --- Embed
        embed = discord.Embed(
            title="🎁 Récompense quotidienne",
            description=f"Streak : **{streak}** (bonus +{streak_bonus})",
            color=discord.Color.green()
        )

        # Ligne 1 : coins
        embed.add_field(name="GotCoins gagnés", value=f"+{coins_gain}", inline=False)

        # Ligne 2 : Tickets + Objets (colonnes)
        embed.add_field(name="🎟️ Tickets", value=f"+1 (total: {tickets_after})", inline=True)

        lines = _format_items_lines(items)  # ['1x 🛡 [Bouclier 20]', '1x 🩹 [Soigne 10 PV]']
        cols = _split_in_columns(lines, n_cols=2)

        if len(cols) == 1:
            embed.add_field(name="Objets", value=cols[0], inline=True)
        else:
            embed.add_field(name="Objets", value="\u200b", inline=True)  # en-tête
            # Pour garder l’alignement avec Tickets, on met la première colonne ici,
            # puis on ouvre une nouvelle "ligne" si besoin
            embed.add_field(name="\u200b", value=cols[0], inline=True)
            # si on veut forcer le retour ligne avant la 2e colonne d'objets, décommente la ligne vide :
            # embed.add_field(name="\u200b", value="\u200b", inline=False)
            if len(cols) >= 2:
                embed.add_field(name="\u200b", value=cols[1], inline=True)

        # Ligne suivante : solde actuel (pleine largeur)
        embed.add_field(name="Solde actuel", value=str(coins_after), inline=False)

        if last_ts:
            dt = datetime.fromtimestamp(last_ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            embed.set_footer(text=f"Dernier daily: {dt}")

        await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Daily(bot))

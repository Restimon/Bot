# cogs/daily_cog.py
import time
from datetime import datetime, timezone
from typing import List, Dict, Any

import discord
from discord import app_commands
from discord.ext import commands
import aiosqlite

# --- DB projets
from economy_db import add_balance, get_balance
from inventory_db import add_item

# --- Catalogue & tirage utils.py (items = emojis)
# On accepte get_random_items(n) OU get_random_item()
try:
    from utils import ITEMS as ITEM_CATALOG  # dict: { "🛡": {...}, ... }
except Exception:
    ITEM_CATALOG: Dict[str, Dict[str, Any]] = {}

try:
    from utils import get_random_items as _get_random_items  # type: ignore
except Exception:
    _get_random_items = None  # type: ignore

try:
    from utils import get_random_item as _get_random_item  # type: ignore
except Exception:
    _get_random_item = None  # type: ignore

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

# Valeurs à filtrer si jamais le tirage renvoie un "ticket"
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
# Tirage / formatage items
# ===============================
def _short_desc(emoji_key: str) -> str:
    meta: Dict[str, Any] = ITEM_CATALOG.get(emoji_key, {})
    t = meta.get("type", "")

    if t == "attaque":
        dmg = meta.get("degats");        return f"Dégâts {dmg}" if dmg is not None else "Attaque"
    if t == "attaque_chaine":
        dp = meta.get("degats_principal"); ds = meta.get("degats_secondaire")
        return f"Chaîne {dp}/{ds}" if dp is not None and ds is not None else "Attaque en chaîne"
    if t == "virus":
        dmg = meta.get("degats");        return f"Virus {dmg} sur durée" if dmg is not None else "Virus"
    if t == "poison":
        dmg = meta.get("degats");        return f"Poison {dmg}/tick" if dmg is not None else "Poison"
    if t == "infection":
        dmg = meta.get("degats");        return f"Infection {dmg}/tick" if dmg is not None else "Infection"
    if t == "soin":
        heal = meta.get("soin");         return f"Soigne {heal} PV" if heal is not None else "Soin"
    if t == "regen":
        val = meta.get("valeur");        return f"Régén {val}/tick" if val is not None else "Régénération"
    if t == "mysterybox":                return "Mystery Box"
    if t == "vol":                       return "Vol"
    if t == "vaccin":                    return "Immunise contre statut"
    if t == "bouclier":
        val = meta.get("valeur");        return f"Bouclier {val}" if val is not None else "Bouclier"
    if t == "esquive+":
        val = meta.get("valeur");        return f"Esquive +{int(val*100)}%" if isinstance(val, (int, float)) else "Esquive +"
    if t == "reduction":
        val = meta.get("valeur");        return f"Réduction {int(val*100)}%" if isinstance(val, (int, float)) else "Réduction"
    if t == "immunite":                  return "Immunité"
    return emoji_key

def _pick_items(n: int) -> List[str]:
    """Tire n items (émoticônes) en excluant tout ce qui ressemble à un ticket."""
    result: List[str] = []
    # get_random_items prioritaire
    if _get_random_items:
        try:
            cand = _get_random_items(n)
            if isinstance(cand, list):
                result = [e for e in cand if isinstance(e, str) and e not in TICKET_NAMES]
        except Exception:
            result = []
    # sinon on boucle sur get_random_item
    if not result and _get_random_item:
        try:
            for _ in range(n):
                e = _get_random_item()
                if isinstance(e, str) and e not in TICKET_NAMES:
                    result.append(e)
        except Exception:
            pass
    # Complète depuis le catalogue si besoin
    if len(result) < n:
        pool = [k for k in ITEM_CATALOG.keys() if k not in result and k not in TICKET_NAMES]
        result += pool[: max(0, n - len(result))]
    return result[:n]

def _compress_items(items: List[str]) -> List[tuple[str, int]]:
    """Garde l'ordre de tirage, mais regroupe les doublons → [('🔥', 2), ('🍀', 1)]"""
    counts: Dict[str, int] = {}
    order: List[str] = []
    for e in items:
        if not e or e in TICKET_NAMES:
            continue
        if e not in counts:
            order.append(e)
            counts[e] = 1
        else:
            counts[e] += 1
    return [(e, counts[e]) for e in order]

def _format_items_block(pairs: List[tuple[str, int]]) -> str:
    """[(emoji, qty)] → '2x 🔥 [Dégâts 5]\n1x 🍀 [Soigne 1 PV]'"""
    if not pairs:
        return "—"
    lines = [f"{qty}x {emoji} [{_short_desc(emoji)}]" for emoji, qty in pairs]
    return "\n".join(lines)

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

        # Items tirés (2) → compress pour éviter 🔥 🔥
        raw_items = _pick_items(2)
        pairs = _compress_items(raw_items)   # ex: [('🔥', 2)] ou [('🛡',1),('🩹',1)]

        # Écritures
        await add_balance(uid, coins_gain, reason="daily")
        await _add_tickets(uid, 1)
        for emoji, qty in pairs:
            await add_item(uid, emoji, qty)

        await _set_daily_row(uid, now, streak)

        coins_after = await get_balance(uid)
        tickets_after = await _get_tickets(uid)

        # --- Embed
        embed = discord.Embed(
            title="🎁 Récompense quotidienne",
            description=f"Streak : **{streak}** (bonus +{streak_bonus})",
            color=discord.Color.green()
        )

        # Ligne 1 : coins (pleine largeur)
        embed.add_field(name="GotCoins gagnés", value=f"+{coins_gain}", inline=False)

        # Ligne 2 : 2 colonnes bien alignées (Tickets | Objets)
        embed.add_field(name="🎟️ Tickets", value=f"+1 (total: {tickets_after})", inline=True)
        embed.add_field(name="Objets", value=_format_items_block(pairs), inline=True)

        # Ligne suivante : solde actuel (pleine largeur)
        embed.add_field(name="Solde actuel", value=str(coins_after), inline=False)

        if last_ts:
            dt = datetime.fromtimestamp(last_ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            embed.set_footer(text=f"Dernier daily: {dt}")

        await interaction.followup.send(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(Daily(bot))

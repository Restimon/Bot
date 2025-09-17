# cogs/inventory_cog.py
import discord
from discord import app_commands
from discord.ext import commands
import aiosqlite
from typing import List, Tuple

from economy_db import get_balance
from inventory_db import get_all_items

# ---- Emojis & descriptions depuis utils.py (fonctions si dispo, sinon fallback dict)
try:
    from utils import get_item_emoji as _utils_item_emoji  # type: ignore
except Exception:
    _utils_item_emoji = None

try:
    from utils import get_item_description as _utils_item_desc  # type: ignore
except Exception:
    _utils_item_desc = None

_UTILS_ITEMS = None
if _utils_item_emoji is None or _utils_item_desc is None:
    try:
        from utils import ITEMS as _UTILS_ITEMS  # type: ignore
    except Exception:
        _UTILS_ITEMS = None

def _item_emoji(name: str) -> str:
    if _utils_item_emoji:
        try:
            em = _utils_item_emoji(name)
            if isinstance(em, str) and em.strip():
                return em
        except Exception:
            pass
    if isinstance(_UTILS_ITEMS, dict):
        meta = _UTILS_ITEMS.get(name) or _UTILS_ITEMS.get((name or "").lower())
        if isinstance(meta, dict):
            em = meta.get("emoji") or meta.get("icon") or meta.get("emote")
            if isinstance(em, str) and em.strip():
                return em
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

def _item_desc(name: str) -> str:
    # 1) fonction dédiée
    if _utils_item_desc:
        try:
            d = _utils_item_desc(name)
            if isinstance(d, str) and d.strip():
                return d
        except Exception:
            pass
    # 2) dict catalogue
    if isinstance(_UTILS_ITEMS, dict):
        meta = _UTILS_ITEMS.get(name) or _UTILS_ITEMS.get((name or "").lower())
        if isinstance(meta, dict):
            for key in ("short", "short_desc", "shortDescription", "desc", "description"):
                d = meta.get(key)
                if isinstance(d, str) and d.strip():
                    return d
    # 3) fallback
    return name

# ---- DB path (la même DB que le reste)
try:
    from economy_db import DB_PATH as DB_PATH  # type: ignore
except Exception:
    DB_PATH = "gotvalis.sqlite3"

# ---- Tickets en table séparée (comme dans le daily modifié)
CREATE_TICKETS_SQL = """
CREATE TABLE IF NOT EXISTS tickets (
    user_id INTEGER PRIMARY KEY,
    count   INTEGER NOT NULL
);
"""

TICKET_NAMES = {"Ticket", "ticket", "🎟️ Ticket", "🎟️", "Daily Ticket", "daily ticket"}

async def _ensure_tickets_table():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(CREATE_TICKETS_SQL)
        await db.commit()

async def _get_tickets(uid: int) -> int:
    await _ensure_tickets_table()
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT count FROM tickets WHERE user_id = ?", (uid,))
        row = await cur.fetchone()
        await cur.close()
    return int(row[0]) if row else 0


class Inventory(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _format_items_lines(self, items: List[Tuple[str, int]]) -> List[str]:
        """Retourne une liste de lignes '1x 🛡️ [Description]' en excluant les tickets."""
        lines: List[str] = []
        for name, qty in items:
            if not name or name in TICKET_NAMES:
                continue
            emoji = _item_emoji(name)
            desc = _item_desc(name)
            if not isinstance(emoji, str) or not emoji.strip():
                emoji = name
            # ex: "1x 🛡️ [Réduction de dégâts]"
            lines.append(f"{qty}x {emoji} [{desc}]")
        return lines

    def _split_in_columns(self, lines: List[str], n_cols: int = 2) -> List[str]:
        """Découpe la liste en n colonnes équilibrées, renvoie la valeur texte de chaque colonne."""
        if not lines:
            return ["—"]
        # équilibre: moitié - moitié (ou réparti quasi égal)
        per_col = (len(lines) + n_cols - 1) // n_cols
        cols = []
        for i in range(n_cols):
            start = i * per_col
            chunk = lines[start:start + per_col]
            if chunk:
                cols.append("\n".join(chunk))
        # au moins une colonne
        return cols or ["—"]

    async def _send_inventory(self, interaction: discord.Interaction):
        """Logique partagée par /inventory et /inv."""
        await interaction.response.defer(ephemeral=False, thinking=False)

        uid = interaction.user.id
        username = interaction.user.display_name

        coins = await get_balance(uid)
        items = await get_all_items(uid)  # List[Tuple[name, qty]]
        tickets = await _get_tickets(uid)

        embed = discord.Embed(
            title=f"📦 Inventaire — {username}",
            color=discord.Color.green()
        )

        # OBJETS en colonnes
        lines = self._format_items_lines(items)
        cols = self._split_in_columns(lines, n_cols=2)

        if len(cols) == 1:
            # une seule colonne/peu d'items
            embed.add_field(name="Objets", value=cols[0], inline=False)
        else:
            # petit en-tête puis deux colonnes vides (noms invisibles) pour un rendu clean
            embed.add_field(name="Objets", value="\u200b", inline=False)
            embed.add_field(name="\u200b", value=cols[0], inline=True)
            embed.add_field(name="\u200b", value=cols[1], inline=True)

        # Tickets & GoldValis (ligne suivante)
        embed.add_field(name="🎟️ Tickets", value=str(tickets), inline=True)
        embed.add_field(name="💰 GoldValis", value=str(coins), inline=True)

        if interaction.user.display_avatar:
            embed.set_thumbnail(url=interaction.user.display_avatar.url)

        await interaction.followup.send(embed=embed)

    @app_commands.command(name="inventory", description="Affiche ton inventaire.")
    async def inventory(self, interaction: discord.Interaction):
        await self._send_inventory(interaction)

    @app_commands.command(name="inv", description="Alias de /inventory.")
    async def inv(self, interaction: discord.Interaction):
        await self._send_inventory(interaction)


async def setup(bot: commands.Bot):
    await bot.add_cog(Inventory(bot))

# cogs/inventory_cog.py
import discord
from discord import app_commands
from discord.ext import commands
import aiosqlite

from economy_db import get_balance
from inventory_db import get_all_items

# ---- Emojis depuis utils.py (fonction si dispo, sinon fallback dict)
try:
    from utils import get_item_emoji as _utils_item_emoji  # type: ignore
except Exception:
    _utils_item_emoji = None

_UTILS_ITEMS = None
if _utils_item_emoji is None:
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

    def _format_items_emoji_xqty(self, items: list[tuple[str, int]]) -> str:
        """Affiche uniquement les émojis avec ×qty, en excluant les tickets."""
        chunks = []
        for name, qty in items:
            if not name or name in TICKET_NAMES:
                continue  # ne pas montrer les tickets comme objets
            emoji = _item_emoji(name)
            # si la fonction renvoie le nom (pas d'emoji), on affiche quand même pour ne rien perdre
            if not isinstance(emoji, str) or not emoji.strip():
                emoji = name
            chunks.append(f"{emoji} × {qty}")
        return " · ".join(chunks) if chunks else "—"

    @app_commands.command(name="inventory", description="Affiche ton inventaire.")
    async def inventory(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False, thinking=False)

        uid = interaction.user.id
        username = interaction.user.display_name

        # Solde et items
        coins = await get_balance(uid)
        items = await get_all_items(uid)  # attendu: List[Tuple[name, qty]]

        # Tickets séparés
        tickets = await _get_tickets(uid)

        # Embed
        embed = discord.Embed(
            title=f"📦 Inventaire — {username}",
            color=discord.Color.green()
        )

        # Objets (ligne 1)
        embed.add_field(name="Objets", value=self._format_items_emoji_xqty(items), inline=False)

        # Tickets & GoldValis (ligne 2, deux colonnes)
        embed.add_field(name="🎟️ Tickets", value=str(tickets), inline=True)
        embed.add_field(name="💰 GoldValis", value=str(coins), inline=True)

        # (Option) Un rappel Daily si tu veux
        # embed.add_field(name="📅 Daily", value="Utilise `/daily` pour récupérer ton ticket journalier.", inline=False)

        # Avatar à droite si possible
        if interaction.user.display_avatar:
            embed.set_thumbnail(url=interaction.user.display_avatar.url)

        await interaction.followup.send(embed=embed)

    # Alias /inv si tu l'utilises déjà
    @app_commands.command(name="inv", description="Alias de /inventory.")
    async def inv(self, interaction: discord.Interaction):
        await self.inventory(interaction)


async def setup(bot: commands.Bot):
    await bot.add_cog(Inventory(bot))

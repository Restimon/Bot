# cogs/inventory_cog.py
import discord
from discord import app_commands
from discord.ext import commands
import aiosqlite
from typing import List, Tuple, Dict, Any

from economy_db import get_balance
from inventory_db import get_all_items

# -- On importe le catalogue depuis utils.py (clés = emojis)
try:
    from utils import ITEMS as ITEM_CATALOG  # type: ignore
except Exception:
    ITEM_CATALOG: Dict[str, Dict[str, Any]] = {}

# ---- DB path (même DB que le reste)
try:
    from economy_db import DB_PATH as DB_PATH  # type: ignore
except Exception:
    DB_PATH = "gotvalis.sqlite3"

# ---- Tickets en table séparée (le ticket ne doit PAS apparaître dans les objets)
CREATE_TICKETS_SQL = """
CREATE TABLE IF NOT EXISTS tickets (
    user_id INTEGER PRIMARY KEY,
    count   INTEGER NOT NULL
);
"""

# valeurs acceptées pour “ticket” si jamais il se glisse dans l’inventaire par erreur
TICKET_NAMES = {"🎟️", "🎟️ Ticket", "Ticket", "ticket", "Daily Ticket", "daily ticket"}

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


# ---------- Helpers d'affichage ----------
def _short_desc(emoji_key: str) -> str:
    """
    Fabrique une description courte à partir des métadonnées du catalogue.
    On couvre tous les 'type' que tu as listés : attaque, attaque_chaine, virus, poison, infection,
    soin, regen, mysterybox, vol, vaccin, bouclier, esquive+, reduction, immunite.
    """
    meta = ITEM_CATALOG.get(emoji_key, {}) if isinstance(ITEM_CATALOG, dict) else {}
    t = meta.get("type", "")

    # Attaques simples
    if t == "attaque":
        dmg = meta.get("degats")
        return f"Dégâts {dmg}" if dmg is not None else "Attaque"
    # Attaque en chaîne
    if t == "attaque_chaine":
        dp = meta.get("degats_principal")
        ds = meta.get("degats_secondaire")
        if dp is not None and ds is not None:
            return f"Chaîne {dp}/{ds}"
        return "Attaque en chaîne"
    # Virus / Poison / Infection (DoT)
    if t == "virus":
        dmg = meta.get("degats")
        dur = meta.get("duree")
        return f"Virus {dmg} sur durée" if dmg is not None else "Virus"
    if t == "poison":
        dmg = meta.get("degats")
        return f"Poison {dmg}/tick" if dmg is not None else "Poison"
    if t == "infection":
        dmg = meta.get("degats")
        return f"Infection {dmg}/tick" if dmg is not None else "Infection"
    # Soins
    if t == "soin":
        heal = meta.get("soin")
        return f"Soigne {heal} PV" if heal is not None else "Soin"
    # Régénération
    if t == "regen":
        val = meta.get("valeur")
        return f"Régén {val}/tick" if val is not None else "Régénération"
    # Mystery box
    if t == "mysterybox":
        return "Mystery Box"
    # Vol
    if t == "vol":
        return "Vol"
    # Vaccin
    if t == "vaccin":
        return "Immunise contre statut"
    # Bouclier
    if t == "bouclier":
        val = meta.get("valeur")
        return f"Bouclier {val}" if val is not None else "Bouclier"
    # Esquive +
    if t == "esquive+":
        val = meta.get("valeur")
        return f"Esquive +{int(val*100)}%" if isinstance(val, (int, float)) else "Esquive +"
    # Réduction (casque)
    if t == "reduction":
        val = meta.get("valeur")
        return f"Réduction {int(val*100)}%" if isinstance(val, (int, float)) else "Réduction"
    # Immunité
    if t == "immunite":
        return "Immunité"

    # Par défaut, si non trouvé, on renvoie l'emoji lui-même
    return emoji_key


def _format_items_lines(items: List[Tuple[str, int]]) -> List[str]:
    """
    Transforme [(emoji, qty), ...] en lignes '1x 🛡️ [Description]'.
    Filtre les tickets.
    """
    lines: List[str] = []
    for name, qty in items:
        if not name or name in TICKET_NAMES:
            continue
        emoji = name  # le nom EST déjà l'emoji
        desc = _short_desc(emoji)
        lines.append(f"{qty}x {emoji} [{desc}]")
    return lines


def _split_in_columns(lines: List[str], n_cols: int = 2) -> List[str]:
    """Découpe en n colonnes équilibrées et renvoie les blocs texte pour chaque colonne."""
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


# ---------- Cog ----------
class Inventory(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _send_inventory(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False, thinking=False)

        uid = interaction.user.id
        username = interaction.user.display_name

        coins = await get_balance(uid)
        items = await get_all_items(uid)  # List[Tuple[str(emoji), int]]
        tickets = await _get_tickets(uid)

        embed = discord.Embed(
            title=f"📦 Inventaire — {username}",
            color=discord.Color.green()
        )

        # OBJETS en colonnes (2)
        lines = _format_items_lines(items)
        cols = _split_in_columns(lines, n_cols=2)

        if len(cols) == 1:
            embed.add_field(name="Objets", value=cols[0], inline=False)
        else:
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

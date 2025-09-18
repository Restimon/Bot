# cogs/inventory_cog.py
import discord
from discord import app_commands
from discord.ext import commands
import aiosqlite
from typing import List, Tuple, Dict, Any

from economy_db import get_balance
from inventory_db import get_all_items

# --- Catalogue depuis utils.py (priorité à OBJETS, fallback ITEMS)
try:
    from utils import OBJETS as ITEM_CATALOG  # dict: { "🛡": {...}, ... }
except Exception:
    try:
        from utils import ITEMS as ITEM_CATALOG
    except Exception:
        ITEM_CATALOG: Dict[str, Dict[str, Any]] = {}

# ---- DB path
try:
    from economy_db import DB_PATH as DB_PATH  # type: ignore
except Exception:
    DB_PATH = "gotvalis.sqlite3"

# ---- Tickets dans une table dédiée (pas dans l'inventaire)
CREATE_TICKETS_SQL = """
CREATE TABLE IF NOT EXISTS tickets (
    user_id INTEGER PRIMARY KEY,
    count   INTEGER NOT NULL
);
"""

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
    """Construit une petite description à partir des métadonnées de utils."""
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

def _format_items_lines(items: List[Tuple[str, int]]) -> List[str]:
    """(emoji, qty) -> '1x 🛡 [Bouclier 20]' ; filtre tickets au cas où."""
    return [
        f"{qty}x {emoji} [{_short_desc(emoji)}]"
        for emoji, qty in items
        if emoji and emoji not in TICKET_NAMES
    ]

def _columns_rowwise(lines: List[str], n_cols: int = 2) -> List[str]:
    """
    Répartition LIGNE PAR LIGNE (row-major) :
    1er -> col1, 2e -> col2, 3e -> col1, 4e -> col2, ...
    """
    if not lines:
        return ["—"]
    cols: List[List[str]] = [[] for _ in range(n_cols)]
    for i, line in enumerate(lines):
        cols[i % n_cols].append(line)
    return ["\n".join(c) if c else "—" for c in cols]


# ---------- Cog ----------
class Inventory(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _send_inventory(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False, thinking=False)

        uid = interaction.user.id
        username = interaction.user.display_name

        # Données
        coins = await get_balance(uid)
        raw_items = await get_all_items(uid)  # List[Tuple[str(emoji), int]]
        tickets = await _get_tickets(uid)

        # Embed
        embed = discord.Embed(
            title=f"📦 Inventaire — {username}",
            color=discord.Color.green()
        )

        # --------- OBJETS ---------
        embed.add_field(name="Objets", value="\u200b", inline=False)

        lines = _format_items_lines(raw_items)

        if len(lines) >= 6:
            # 2 colonnes (remplies ligne par ligne)
            col_values = _columns_rowwise(lines, n_cols=2)
            embed.add_field(name="\u200b", value=col_values[0], inline=True)
            embed.add_field(name="\u200b", value=col_values[1] if len(col_values) > 1 else "—", inline=True)
        else:
            # 1 seule colonne
            block = "\n".join(lines) if lines else "—"
            embed.add_field(name="\u200b", value=block, inline=False)

        # Séparateur pour forcer un retour à la ligne
        embed.add_field(name="\u200b", value="\u200b", inline=False)

        # --------- RESSOURCES ---------
        # Même ligne : GoldValis | Tickets
        embed.add_field(name="💰 GoldValis", value=str(coins), inline=True)
        embed.add_field(name="🎟️ Tickets", value=str(tickets), inline=True)

        # Avatar
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

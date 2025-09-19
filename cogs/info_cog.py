# cogs/info_cog.py
import discord
from discord import app_commands
from discord.ext import commands
import aiosqlite
from typing import List, Tuple, Dict, Any, Optional
from datetime import timezone

# ---- Economy / Inventory
from economy_db import get_balance
from inventory_db import get_all_items

# ---- Total carrière (optionnel selon ton projet)
_get_total_career: Optional[callable] = None
try:
    # Essaie d'importer une fonction de total carrière si tu en as une
    from economy_db import get_total_earned as _get_total_career  # type: ignore
except Exception:
    try:
        from economy_db import get_lifetime_earned as _get_total_career  # type: ignore
    except Exception:
        _get_total_career = None

# ---- Effets (optionnels)
_get_effects: Optional[callable] = None
try:
    from effects_db import get_active_effects as _get_effects  # type: ignore
except Exception:
    _get_effects = None

# ---- Catalogue depuis utils.py (priorité à OBJETS, fallback ITEMS)
try:
    from utils import OBJETS as ITEM_CATALOG  # dict: { "🛡": {...}, ... }
except Exception:
    try:
        from utils import ITEMS as ITEM_CATALOG
    except Exception:
        ITEM_CATALOG: Dict[str, Dict[str, Any]] = {}

# ---- DB path (même DB que le reste)
try:
    from economy_db import DB_PATH as DB_PATH  # type: ignore
except Exception:
    DB_PATH = "gotvalis.sqlite3"

# ---- Tickets dans une table dédiée (comme /inv & /daily)
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
    Répartition LIGNE PAR LIGNE :
      1er -> col1, 2e -> col2, 3e -> col1, 4e -> col2, ...
    """
    if not lines:
        return ["—"]
    cols: List[List[str]] = [[] for _ in range(n_cols)]
    for i, line in enumerate(lines):
        cols[i % n_cols].append(line)
    return ["\n".join(c) if c else "—" for c in cols]


# ---------- Cog ----------
class Info(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _render_info_embed(self, member: discord.Member | discord.User) -> discord.Embed:
        uid = member.id
        username = member.display_name if isinstance(member, discord.Member) else member.name

        # Ressources
        coins_now = await get_balance(uid)
        tickets = await _get_tickets(uid)
        career_total = 0
        if _get_total_career:
            try:
                career_total = int(await _get_total_career(uid))  # type: ignore
            except Exception:
                career_total = 0

        # Inventaire
        inv_items = await get_all_items(uid)  # List[Tuple[str(emoji), int]]
        lines = _format_items_lines(inv_items)

        # Points de vie (si DB dispo, sinon défaut 100/100)
        hp, hp_max = 100, 100
        try:
            from stats_db import get_hp, get_max_hp  # type: ignore
            hp = int(await get_hp(uid))              # type: ignore
            hp_max = int(await get_max_hp(uid))      # type: ignore
        except Exception:
            pass

        # Effets actifs (optionnel)
        effects_text = "Aucun effet négatif détecté."
        if _get_effects:
            try:
                effs = await _get_effects(uid)  # type: ignore
                if effs:
                    # Effets attendus: liste de dicts ou tuples, adaptatif
                    pretty: List[str] = []
                    for e in effs:
                        name = str(getattr(e, "name", None) or e.get("name", "Effet"))
                        pretty.append(f"• {name}")
                    effects_text = "\n".join(pretty)
            except Exception:
                pass

        # ── Embed ──
        embed = discord.Embed(
            title=f"Profil GotValis de {username}",
            description="Analyse médicale et opérationnelle en cours...",
            color=discord.Color.blurple()
        )

        # PV
        embed.add_field(name="❤️ Points de vie", value=f"{hp} / {hp_max}", inline=False)

        # Ressources (ligne de 3)
        embed.add_field(name="🏆 GotCoins totaux (carrière)", value=str(career_total), inline=True)
        embed.add_field(name="💰 Solde actuel (dépensable)", value=str(coins_now), inline=True)
        embed.add_field(name="🎟️ Tickets", value=str(tickets), inline=True)

        # Date d'arrivée
        if isinstance(member, discord.Member) and member.joined_at:
            joined = member.joined_at.astimezone(timezone.utc).strftime("%d %B %Y à %Hh%M")
            embed.add_field(name="📅 Membre depuis", value=joined, inline=False)

        # Inventaire : 1 col < 6, sinon 2 colonnes remplies ligne par ligne
        if len(lines) >= 6:
            cols = _columns_rowwise(lines, n_cols=2)
            embed.add_field(name="📦 Inventaire", value=cols[0], inline=True)
            embed.add_field(name="\u200b", value=cols[1], inline=True)
            embed.add_field(name="\u200b", value="\u200b", inline=True)  # fin de rangée
        else:
            block = "\n".join(lines) if lines else "Aucun objet"
            embed.add_field(name="📦 Inventaire", value=block, inline=False)

        # Effets/pathologies
        embed.add_field(name="🩺 État pathologique", value=effects_text, inline=False)

        # Avatar
        if member.display_avatar:
            embed.set_thumbnail(url=member.display_avatar.url)

        return embed

    # ===== Slash =====
    @app_commands.command(name="info", description="Affiche ton profil GotValis.")
    async def info(self, interaction: discord.Interaction, membre: Optional[discord.Member] = None):
        await interaction.response.defer(ephemeral=False, thinking=False)
        target = membre or interaction.user
        embed = await self._render_info_embed(target)
        await interaction.followup.send(embed=embed)

    # ===== Préfixé (fallback) =====
    @commands.command(name="info")
    async def info_prefix(self, ctx: commands.Context, member: Optional[discord.Member] = None):
        target = member or ctx.author
        embed = await self._render_info_embed(target)
        await ctx.reply(embed=embed, mention_author=False)


async def setup(bot: commands.Bot):
    await bot.add_cog(Info(bot))

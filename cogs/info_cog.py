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

# ---- Total carrière (optionnel)
_get_total_career: Optional[callable] = None
try:
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

# ---- Personnage équipé (source prioritaire: gacha_db si dispo)
_gacha_get_equipped: Optional[callable] = None
try:
    from gacha_db import get_equipped_character as _gacha_get_equipped  # type: ignore
except Exception:
    _gacha_get_equipped = None

# ---- Catalogue personnages (pour joli rendu)
CHAR_CATALOG: Dict[str, Dict[str, Any]] = {}
for key in ("CHARACTERS", "PERSONNAGES"):
    if not CHAR_CATALOG:
        try:
            from utils import __dict__ as _u  # type: ignore
            maybe = _u.get(key)
            if isinstance(maybe, dict):
                CHAR_CATALOG = maybe  # type: ignore
        except Exception:
            pass

# ---- Catalogue objets (pour l'inventaire)
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

# ---- Tickets (même table que /inv & /daily)
CREATE_TICKETS_SQL = """
CREATE TABLE IF NOT EXISTS tickets (
    user_id INTEGER PRIMARY KEY,
    count   INTEGER NOT NULL
);
"""

# ---- Personnage équipé (fallback si gacha_db absent)
CREATE_EQUIPPED_SQL = """
CREATE TABLE IF NOT EXISTS equipped_character (
    user_id INTEGER PRIMARY KEY,
    char_id TEXT NOT NULL
);
"""

TICKET_NAMES = {"🎟️", "🎟️ Ticket", "Ticket", "ticket", "Daily Ticket", "daily ticket"}

async def _ensure_tables():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(CREATE_TICKETS_SQL)
        await db.execute(CREATE_EQUIPPED_SQL)
        await db.commit()

async def _get_tickets(uid: int) -> int:
    await _ensure_tables()
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT count FROM tickets WHERE user_id = ?", (uid,))
        row = await cur.fetchone()
        await cur.close()
    return int(row[0]) if row else 0

async def _get_equipped_char_id(uid: int) -> Optional[str]:
    """Essaie gacha_db, sinon notre table equipped_character."""
    # 1) gacha_db prioritaire
    if _gacha_get_equipped:
        try:
            r = await _gacha_get_equipped(uid)  # type: ignore
            # accepte différents formats: str | dict | tuple
            if isinstance(r, str):
                return r
            if isinstance(r, dict):
                return str(r.get("char_id") or r.get("id") or r.get("key") or "") or None
            if isinstance(r, (list, tuple)) and r:
                return str(r[0])
        except Exception:
            pass
    # 2) fallback table locale
    await _ensure_tables()
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT char_id FROM equipped_character WHERE user_id = ?", (uid,))
        row = await cur.fetchone()
        await cur.close()
    return str(row[0]) if row and row[0] else None

def _pretty_character(char_id: Optional[str]) -> str:
    if not char_id:
        return "Aucun"
    meta = None
    # accède par clé directe
    meta = CHAR_CATALOG.get(char_id)
    # sinon cherche par champ id
    if not meta:
        for k, v in CHAR_CATALOG.items():
            if isinstance(v, dict) and str(v.get("id")) == str(char_id):
                meta = v
                break
    if isinstance(meta, dict):
        emoji = meta.get("emoji") or meta.get("icon") or ""
        name = meta.get("name") or meta.get("nom") or str(char_id)
        if emoji:
            return f"{emoji} {name}"
        return name
    return str(char_id)

# ---------- Helpers d'affichage (inventaire) ----------
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
    return [
        f"{qty}x {emoji} [{_short_desc(emoji)}]"
        for emoji, qty in items
        if emoji and emoji not in TICKET_NAMES
    ]

def _columns_rowwise(lines: List[str], n_cols: int = 2) -> List[str]:
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

        # Personnage équipé
        char_id = await _get_equipped_char_id(uid)
        char_label = _pretty_character(char_id)

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
                    pretty: List[str] = []
                    for e in effs:
                        name = str(getattr(e, "name", None) or (isinstance(e, dict) and e.get("name")) or "Effet")
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

        # Personnage équipé
        embed.add_field(name="🧬 Personnage équipé", value=char_label, inline=False)

        # Inventaire : 1 col < 6, sinon 2 colonnes remplies ligne par ligne
        if len(lines) >= 6:
            cols = _columns_rowwise(lines, n_cols=2)
            embed.add_field(name="📦 Inventaire", value=cols[0], inline=True)
            embed.add_field(name="\u200b", value=cols[1], inline=True)
            embed.add_field(name="\u200b", value="\u200b", inline=True)  # fin de rangée
        else:
            block = "\n".join(lines) if lines else "Aucun objet"
            embed.add_field(name="📦 Inventaire", value=block, inline=False)

        # Avatar
        if member.display_avatar:
            embed.set_thumbnail(url=member.display_avatar.url)

        # Si le catalogue a une image dédiée pour ce personnage, on la met en bannière
        # (optionnel, n'affecte pas si None)
        try:
            meta = CHAR_CATALOG.get(char_id or "", {})
            banner = meta.get("image") or meta.get("banner") or meta.get("icon_url")
            if banner:
                embed.set_image(url=banner)
        except Exception:
            pass

        # Effets/pathologies
        embed.add_field(name="🩺 État pathologique", value=effects_text, inline=False)

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

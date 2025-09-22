# cogs/info_cog.py
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands
import aiosqlite
from typing import List, Tuple, Dict, Any, Optional
from datetime import timezone

# ==== Economy / Inventory ======================================================
from economy_db import get_balance
from inventory_db import get_all_items

# ---- Total carrière (optionnels) ---------------------------------------------
_get_total_career: Optional[callable] = None
try:
    from economy_db import get_total_earned as _get_total_career  # type: ignore
except Exception:
    try:
        from economy_db import get_lifetime_earned as _get_total_career  # type: ignore
    except Exception:
        _get_total_career = None

# ---- Effets (utilise la même source que le combat) ---------------------------
_list_effects: Optional[callable] = None
try:
    from effects_db import list_effects as _list_effects  # type: ignore
except Exception:
    _list_effects = None

# ---- Personnage équipé (source prioritaire: gacha_db si dispo) ---------------
_gacha_get_equipped: Optional[callable] = None
try:
    from gacha_db import get_equipped_character as _gacha_get_equipped  # type: ignore
except Exception:
    _gacha_get_equipped = None

# ---- Bouclier (si shields_db est présent) ------------------------------------
_get_shield: Optional[callable] = None
_get_max_shield: Optional[callable] = None
try:
    from shields_db import get_shield as _get_shield, get_max_shield as _get_max_shield  # type: ignore
except Exception:
    _get_shield = None
    _get_max_shield = None

# ---- Catalogue personnages (joli rendu facultatif) ---------------------------
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

# ---- Catalogue objets (pour l'inventaire) -----------------------------------
try:
    from utils import OBJETS as ITEM_CATALOG  # dict: { "🛡": {...}, ... }
except Exception:
    try:
        from utils import ITEMS as ITEM_CATALOG
    except Exception:
        ITEM_CATALOG: Dict[str, Dict[str, Any]] = {}

# ---- DB path (même DB que le reste) ------------------------------------------
try:
    from economy_db import DB_PATH as DB_PATH  # type: ignore
except Exception:
    DB_PATH = "gotvalis.sqlite3"

# ---- Tickets & personnage équipé fallback (tables locales) -------------------
CREATE_TICKETS_SQL = """
CREATE TABLE IF NOT EXISTS tickets (
    user_id INTEGER PRIMARY KEY,
    count   INTEGER NOT NULL
);
"""
CREATE_EQUIPPED_SQL = """
CREATE TABLE IF NOT EXISTS equipped_character (
    user_id INTEGER PRIMARY KEY,
    char_id TEXT NOT NULL
);
"""
TICKET_NAMES = {"🎟️", "🎟️ Ticket", "Ticket", "ticket", "Daily Ticket", "daily ticket"}

# ==== Classement "points" via storage JSON (comme leaderboard_cog) =============
_storage = None
try:
    from data import storage as _storage  # type: ignore
except Exception:
    _storage = None

def _lb_get_leaderboard(gid: int) -> Dict[str, Dict[str, int]]:
    """Retourne dict user_id -> {points, kills, deaths} pour CE serveur."""
    if _storage is not None:
        if not hasattr(_storage, "leaderboard") or not isinstance(getattr(_storage, "leaderboard"), dict):
            setattr(_storage, "leaderboard", {})
        lb = getattr(_storage, "leaderboard")
        lb.setdefault(str(gid), {})
        return lb[str(gid)]
    # Fallback RAM si storage indisponible
    if not hasattr(_lb_get_leaderboard, "_mem"):
        _lb_get_leaderboard._mem: Dict[str, Dict[str, Dict[str, int]]] = {}
    mem = _lb_get_leaderboard._mem  # type: ignore
    mem.setdefault(str(gid), {})
    return mem[str(gid)]

def _lb_rank_sorted(gid: int) -> List[Tuple[int, Dict[str, int]]]:
    lb = _lb_get_leaderboard(gid)
    items: List[Tuple[int, Dict[str, int]]] = []
    for uid_str, stats in lb.items():
        try:
            uid = int(uid_str)
        except Exception:
            continue
        if not isinstance(stats, dict):
            continue
        pts = int(stats.get("points", 0) or 0)
        k = int(stats.get("kills", 0) or 0)
        d = int(stats.get("deaths", 0) or 0)
        items.append((uid, {"points": pts, "kills": k, "deaths": d}))
    items.sort(key=lambda x: (-x[1]["points"], -x[1]["kills"], x[1]["deaths"], x[0]))
    return items

def _lb_find_rank(sorted_list: List[Tuple[int, Dict[str, int]]], uid: int) -> Optional[int]:
    for i, (u, _) in enumerate(sorted_list, start=1):
        if u == uid:
            return i
    return None

# ==== Helpers tickets / inventaire / format ===================================
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
    # 1) gacha_db prioritaire
    if _gacha_get_equipped:
        try:
            r = await _gacha_get_equipped(uid)  # type: ignore
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
    meta = CHAR_CATALOG.get(char_id)
    if not meta:
        for _, v in CHAR_CATALOG.items():
            if isinstance(v, dict) and str(v.get("id")) == str(char_id):
                meta = v
                break
    if isinstance(meta, dict):
        emoji = meta.get("emoji") or meta.get("icon") or ""
        name = meta.get("name") or meta.get("nom") or str(char_id)
        return f"{emoji} {name}".strip()
    return str(char_id)

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
    """Répartition ligne par ligne (row-major) pour des colonnes compactes."""
    if not lines:
        return ["—"]
    cols: List[List[str]] = [[] for _ in range(n_cols)]
    for i, line in enumerate(lines):
        cols[i % n_cols].append(line)
    return ["\n".join(c) if c else "—" for c in cols]

def _fmt_dt_utc(dt) -> str:
    try:
        return dt.astimezone(timezone.utc).strftime("%d %B %Y à %Hh%M UTC")
    except Exception:
        return str(dt)

# ==== Calcul du total carrière (fallback robuste) ==============================
USER_COLS = ("user_id", "uid", "member_id", "author_id", "player_id")
AMOUNT_COLS = ("amount", "delta", "change", "value", "coins", "gotcoins", "gc", "balance_change")

async def _career_total_from_db(uid: int) -> Optional[int]:
    """Scanne la DB pour inférer un total gagné si aucune fonction dédiée n'existe."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [r[0] for r in await cur.fetchall()]
            await cur.close()

            for t in tables:
                cur = await db.execute(f"PRAGMA table_info({t})")
                cols = [r[1].lower() for r in await cur.fetchall()]
                await cur.close()

                user_candidates = [c for c in cols if c in USER_COLS]
                amount_candidates = [c for c in cols if c in AMOUNT_COLS]
                if not user_candidates or not amount_candidates:
                    continue

                ucol = user_candidates[0]
                acol = amount_candidates[0]

                q = f"SELECT COALESCE(SUM(CASE WHEN {acol} > 0 THEN {acol} ELSE 0 END), 0) FROM {t} WHERE {ucol}=?"
                cur = await db.execute(q, (uid,))
                v = await cur.fetchone()
                await cur.close()
                if v and v[0] is not None:
                    total = int(v[0])
                    if total > 0:
                        return total
    except Exception:
        pass
    return None

async def _get_career_total(uid: int, min_floor: int) -> int:
    # 1) fonction dédiée si dispo
    if _get_total_career:
        try:
            v = int(await _get_total_career(uid))  # type: ignore
            if v > 0:
                return v
        except Exception:
            pass
    # 2) heuristique DB
    dbv = await _career_total_from_db(uid)
    if dbv is not None and dbv >= 0:
        return max(dbv, min_floor)
    # 3) fallback minimal
    return max(min_floor, 0)

# ==== Rang par Coins (serveur) avec fallback si ligne manquante ================
async def _get_coin_rank(uid: int, guild: Optional[discord.Guild] = None) -> Optional[Tuple[int, int, int]]:
    """
    Rang par COINS (DESC) avec fallback si la ligne 'balances' manque.
    - Si 'guild' est fourni, ne classe que les membres de CE serveur.
    - Retourne (rang, total_pris_en_compte, solde_utilisateur).
    """
    # Solde actuel (même source que /daily et /inv)
    try:
        coins_now = int(await get_balance(uid))
    except Exception:
        coins_now = 0

    # Récupère toutes les balances > 0 depuis la DB (si la table existe)
    rows: List[Tuple[int, int]] = []
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute("SELECT user_id, balance FROM balances WHERE balance > 0")
            rows = [(int(u), int(b)) for (u, b) in await cur.fetchall()]
            await cur.close()
    except Exception:
        # Pas de table 'balances' → on se base au moins sur notre solde si > 0
        if coins_now > 0:
            rows = [(uid, coins_now)]
        else:
            return None

    # Ajoute l'utilisateur virtuellement s'il n'est pas présent mais a des coins
    if coins_now > 0 and not any(u == uid for (u, _) in rows):
        rows.append((uid, coins_now))

    # Classement PAR SERVEUR si 'guild' est fourni
    if guild is not None:
        try:
            member_ids = {m.id for m in guild.members}
            rows = [(u, b) for (u, b) in rows if u in member_ids]
        except Exception:
            pass

    if not rows:
        return None

    # Trie: balance DESC, puis user_id ASC pour stabilité
    rows.sort(key=lambda t: (-t[1], t[0]))

    # Trouve le rang de l'utilisateur
    try:
        rank = next(i for i, (u, _) in enumerate(rows, start=1) if u == uid)
    except StopIteration:
        return None  # pas pris en compte (zéro coin et/ou pas membre du serveur)

    total = len(rows)
    return rank, total, coins_now

# ==== Cog ======================================================================
class Info(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _render_info_embed(self, member: discord.Member | discord.User, guild: Optional[discord.Guild] = None) -> discord.Embed:
        uid = member.id
        username = member.display_name if isinstance(member, discord.Member) else member.name

        # Ressources
        coins_now = await get_balance(uid)
        tickets = await _get_tickets(uid)
        career_total = await _get_career_total(uid, min_floor=coins_now)

        # Personnage équipé
        char_id = await _get_equipped_char_id(uid)
        char_label = _pretty_character(char_id)

        # Inventaire
        inv_items = await get_all_items(uid)  # List[Tuple[str(emoji), int]]
        lines = _format_items_lines(inv_items)

        # PV & bouclier — mêmes sources que le COG de combat
        hp, hp_max = 100, 100
        try:
            from stats_db import get_hp  # type: ignore
            hp, hp_max = await get_hp(uid)  # ← get_hp renvoie (hp, max_hp)
        except Exception:
            pass

        shield_now = 0
        shield_max = 0
        # 1) Base dédiée PB si dispo
        if _get_shield:
            try:
                shield_now = int(await _get_shield(uid))  # type: ignore
            except Exception:
                pass
        if _get_max_shield:
            try:
                shield_max = int(await _get_max_shield(uid))  # type: ignore
            except Exception:
                pass
        # 2) Fallback: somme de l'effet "pb" (cohérent avec /fight fallback)
        if (shield_now == 0) and _list_effects:
            try:
                rows = await _list_effects(uid)  # type: ignore
                shield_from_effects = sum(int(v or 0) for (eff_type, v, *_rest) in rows if eff_type == "pb")
                if shield_from_effects > shield_now:
                    shield_now = shield_from_effects
            except Exception:
                pass

        # ── Embed ──
        embed = discord.Embed(
            title=f"Profil GotValis de {username}",
            description="Analyse médicale et opérationnelle en cours...",
            color=discord.Color.blurple()
        )

        # PV & bouclier
        embed.add_field(name="❤️ Points de vie", value=f"{hp} / {hp_max}", inline=False)
        embed.add_field(name="🛡 Bouclier", value=f"{shield_now} / {shield_max}", inline=False)

        # Ressources (3 colonnes)
        embed.add_field(name="🏆 GotCoins totaux (carrière)", value=str(career_total), inline=True)
        embed.add_field(name="💰 Solde actuel (dépensable)", value=str(coins_now), inline=True)
        embed.add_field(name="🎟️ Tickets", value=str(tickets), inline=True)

        # Date serveur (on n'affiche PAS "Sur Discord depuis")
        if isinstance(member, discord.Member) and member.joined_at:
            embed.add_field(name="📅 Membre du serveur depuis", value=_fmt_dt_utc(member.joined_at), inline=False)

        # Personnage équipé
        embed.add_field(name="🧬 Personnage équipé", value=char_label, inline=False)

        # ===== Classement (Coins & Points) =====
        classements: List[str] = []

        # Coins (par serveur)
        coin_rank = await _get_coin_rank(uid, guild)
        if coin_rank:
            r, tot, bal = coin_rank
            classements.append(f"💰 Coins : **#{r}** sur **{tot}** — {bal}")

        # Points (storage leaderboard)
        if guild is not None:
            rows = _lb_rank_sorted(guild.id)
            pos = _lb_find_rank(rows, uid)
            if pos:
                stats = next((s for (u, s) in rows if u == uid), {"points": 0, "kills": 0, "deaths": 0})
                classements.append(
                    f"🎯 Points : **#{pos}** — {stats.get('points',0)} pts • 🗡 {stats.get('kills',0)} / 💀 {stats.get('deaths',0)}"
                )

        if not classements:
            classements.append("Non classé")

        embed.add_field(name="🏅 Classement (serveur)", value="\n".join(classements), inline=False)

        # Inventaire : 1 col <6, sinon 2 colonnes remplies ligne par ligne
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

        # Effets / pathologies (si disponibles, via list_effects)
        effects_text = "Aucun effet détecté."
        if _list_effects:
            try:
                rows = await _list_effects(uid)  # type: ignore
                if rows:
                    labels = {
                        "regen": "🌿 Régén",
                        "poison": "🧪 Poison",
                        "infection": "🧟 Infection",
                        "virus": "🦠 Virus",
                        "brulure": "🔥 Brûlure",
                        "esquive+": "👟 Esquive+",
                        "reduction": "🪖 Réduction",
                        "immunite": "⭐️ Immunité",
                        "pb": "🛡 PB",
                    }
                    pretty: List[str] = []
                    for eff_type, value, interval, next_ts, end_ts, source_id, meta_json in rows:
                        label = labels.get(eff_type, eff_type)
                        if interval and int(interval) > 0:
                            pretty.append(f"• {label}: {value} / {max(1,int(interval)//60)} min")
                        else:
                            pretty.append(f"• {label}: {value}")
                    if pretty:
                        effects_text = "\n".join(pretty[:15])
            except Exception:
                pass
        embed.add_field(name="🩺 État (effets)", value=effects_text, inline=False)

        return embed

    # ===== Slash =====
    @app_commands.command(name="info", description="Affiche ton profil GotValis.")
    async def info(self, interaction: discord.Interaction, membre: Optional[discord.Member] = None):
        await interaction.response.defer(ephemeral=False, thinking=False)
        target = membre or interaction.user
        embed = await self._render_info_embed(target, guild=interaction.guild)
        await interaction.followup.send(embed=embed)

    # ===== Préfixé (fallback) =====
    @commands.command(name="info")
    async def info_prefix(self, ctx: commands.Context, member: Optional[discord.Member] = None):
        target = member or ctx.author
        embed = await self._render_info_embed(target, guild=ctx.guild)
        await ctx.reply(embed=embed, mention_author=False)


async def setup(bot: commands.Bot):
    await bot.add_cog(Info(bot))

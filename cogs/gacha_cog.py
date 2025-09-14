# cogs/gacha_cog.py
from __future__ import annotations

import random
from typing import Dict, Any, List, Tuple

import discord
from discord import app_commands
from discord.ext import commands

# ─────────────────────────────────────────────────────────────
# Storage persistant (data/storage.py)
# ─────────────────────────────────────────────────────────────
try:
    from data import storage
except Exception as e:
    storage = None
    print("[gacha_cog] WARNING: storage module not available:", e)

# ─────────────────────────────────────────────────────────────
# Roster des personnages (personnage.py)
# On attend une structure PERSONNAGES (dict ou list) avec un champ "rarete".
# Optionnel: RARETE_WEIGHTS (dict) pour surcharger les poids par rareté.
# ─────────────────────────────────────────────────────────────
try:
    from personnage import PERSONNAGES  # noqa
except Exception as e:
    PERSONNAGES = []
    print("[gacha_cog] WARNING: personnage.PERSONNAGES missing:", e)

try:
    from personnage import RARETE_WEIGHTS as RARETE_WEIGHTS_OVERRIDE  # noqa
except Exception:
    RARETE_WEIGHTS_OVERRIDE = None


# ─────────────────────────────────────────────────────────────
# Helpers pour lire/normaliser le roster
# ─────────────────────────────────────────────────────────────
def _as_list_of_chars(raw) -> List[Dict[str, Any]]:
    """Accepte PERSONNAGES en list[dict] ou dict[key->dict]. Retourne list[dict]."""
    if isinstance(raw, dict):
        out = []
        for key, val in raw.items():
            if isinstance(val, dict):
                v = dict(val)
                v.setdefault("key", key)
                out.append(v)
        return out
    elif isinstance(raw, list):
        return [dict(x) for x in raw if isinstance(x, dict)]
    return []

def _get_char_key(c: Dict[str, Any]) -> str:
    """Clé unique du perso pour la collection (fallback sur name)."""
    return str(c.get("key") or c.get("id") or c.get("name") or c.get("nom") or c.get("slug") or c.get("emoji") or c.get("code") or "unknown")

def _get_char_display(c: Dict[str, Any]) -> str:
    """Texte affiché dans l'embed: priorise emoji + nom."""
    emoji = str(c.get("emoji") or c.get("icon") or "")
    name = str(c.get("name") or c.get("nom") or _get_char_key(c))
    if emoji:
        return f"{emoji} **{name}**"
    return f"**{name}**"

def _get_char_rarete(c: Dict[str, Any]) -> str:
    return str(c.get("rarete") or c.get("rarity") or "").lower().strip() or "commun"

def _collect_raretes(chars: List[Dict[str, Any]]) -> List[str]:
    seen = []
    for c in chars:
        r = _get_char_rarete(c)
        if r not in seen:
            seen.append(r)
    return seen


# ─────────────────────────────────────────────────────────────
# Poids par rareté
# ─────────────────────────────────────────────────────────────
DEFAULT_RARETE_WEIGHTS = {
    # ajuste à ta guise ; c'est un fallback si personnage.RARETE_WEIGHTS n’existe pas
    "commun": 100,
    "rare": 35,
    "epique": 10,
    "légendaire": 2,
    "legendaire": 2,
    "mythique": 1,
}

def _resolve_weights(chars: List[Dict[str, Any]]) -> Dict[str, int]:
    """Renvoie les poids par rareté. Priorise override depuis personnage.py si présent."""
    base = dict(DEFAULT_RARETE_WEIGHTS)
    if isinstance(RARETE_WEIGHTS_OVERRIDE, dict) and RARETE_WEIGHTS_OVERRIDE:
        # normalise les clés en minuscule
        for k, v in RARETE_WEIGHTS_OVERRIDE.items():
            base[str(k).lower()] = int(v)
    # ne garder que les raretés réellement présentes
    present = _collect_raretes(chars)
    return {r: base.get(r, 1) for r in present}


# ─────────────────────────────────────────────────────────────
# Tirage pondéré (par personnage)
# ─────────────────────────────────────────────────────────────
def _build_weighted_pool(chars: List[Dict[str, Any]]) -> List[Tuple[int, int]]:
    """
    Construit une liste [(index_char, weight), ...] où weight = poids(rarete).
    On tire ensuite un index via ces poids.
    """
    weights_by_r = _resolve_weights(chars)
    pool: List[Tuple[int, int]] = []
    for idx, c in enumerate(chars):
        r = _get_char_rarete(c)
        w = int(weights_by_r.get(r, 1))
        if w > 0:
            pool.append((idx, w))
    return pool

def _weighted_choice(pool: List[Tuple[int, int]]) -> int:
    """Retourne l’index choisi en fonction des poids."""
    total = sum(w for _, w in pool)
    if total <= 0:
        return random.choice(pool)[0]
    pick = random.randint(1, total)
    acc = 0
    for idx, w in pool:
        acc += w
        if pick <= acc:
            return idx
    return pool[-1][0]


# ─────────────────────────────────────────────────────────────
# Accès/MAJ storage (tickets, collection)
# ─────────────────────────────────────────────────────────────
def _ensure_user_slot(gid: str, uid: str) -> Dict[str, Any]:
    if storage is None:
        raise RuntimeError("storage module manquant")
    root = storage.data
    g = root.setdefault("guilds", {}).setdefault(gid, {})
    u = g.setdefault("users", {}).setdefault(uid, {})
    # inventaire existant si tu l’utilises déjà
    u.setdefault("inventory", [])
    # tickets
    u.setdefault("tickets", 0)
    # collection de persos {key: count}
    u.setdefault("characters", {})
    return u

def _get_tickets(gid: str, uid: str) -> int:
    u = _ensure_user_slot(gid, uid)
    try:
        return int(u.get("tickets", 0))
    except Exception:
        return 0

def _add_tickets(gid: str, uid: str, n: int) -> int:
    u = _ensure_user_slot(gid, uid)
    u["tickets"] = int(u.get("tickets", 0)) + int(n)
    storage.save_data()
    return u["tickets"]

def _consume_tickets(gid: str, uid: str, n: int) -> bool:
    u = _ensure_user_slot(gid, uid)
    have = int(u.get("tickets", 0))
    if have < n:
        return False
    u["tickets"] = have - n
    storage.save_data()
    return True

def _grant_character(gid: str, uid: str, char_key: str) -> int:
    """Incrémente la possession d’un perso et renvoie le total pour ce perso."""
    u = _ensure_user_slot(gid, uid)
    chars = u.setdefault("characters", {})
    chars[char_key] = int(chars.get(char_key, 0)) + 1
    storage.save_data()
    return chars[char_key]


# ─────────────────────────────────────────────────────────────
# Le Cog
# ─────────────────────────────────────────────────────────────
class Gacha(commands.Cog):
    """
    /gacha count: 1..10  → consomme 'count' tickets
    /gacha_inventaire    → liste tes personnages obtenus
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._chars: List[Dict[str, Any]] = _as_list_of_chars(PERSONNAGES)
        if not self._chars:
            print("[gacha_cog] WARNING: roster vide. Ajoute PERSONNAGES dans personnage.py")

        self._pool = _build_weighted_pool(self._chars) if self._chars else []

    # --------------- Slash: /gacha ---------------
    @app_commands.command(name="gacha", description="Invoque des personnages (1 ticket par invocation).")
    @app_commands.describe(count="Nombre d’invocations (1 à 10)")
    async def gacha_slash(self, interaction: discord.Interaction, count: app_commands.Range[int, 1, 10] = 1):
        if storage is None:
            return await interaction.response.send_message("⚠️ Système de stockage indisponible.", ephemeral=True)
        if not self._pool:
            return await interaction.response.send_message("⚠️ Aucun personnage disponible pour le gacha.", ephemeral=True)

        gid = str(interaction.guild_id) if interaction.guild_id else "dm"
        uid = str(interaction.user.id)

        # Vérif tickets
        have = _get_tickets(gid, uid)
        if have < count:
            return await interaction.response.send_message(
                f"🎟️ Il te faut **{count}** ticket(s), tu n’en as que **{have}**.\n"
                f"Passe à la boutique ou gagne des tickets via `/daily` ou évènements.",
                ephemeral=True
            )

        await interaction.response.defer(thinking=True, ephemeral=False)

        # Consommer tickets
        if not _consume_tickets(gid, uid, count):
            return await interaction.followup.send("⚠️ Impossible de débiter tes tickets (conflit). Réessaie.", ephemeral=True)

        # Tirages
        pulls: List[Dict[str, Any]] = []
        rarity_counts: Dict[str, int] = {}

        for _ in range(count):
            idx = _weighted_choice(self._pool)
            char = dict(self._chars[idx])
            key = _get_char_key(char)
            rarete = _get_char_rarete(char)
            owned_after = _grant_character(gid, uid, key)

            pulls.append({
                "key": key,
                "rarete": rarete,
                "display": _get_char_display(char),
                "dup": owned_after > 1,
                "owned_after": owned_after,
            })
            rarity_counts[rarete] = rarity_counts.get(rarete, 0) + 1

        # Embed résultat
        title = f"🎲 Invocation x{count} | {interaction.user.display_name}"
        desc_lines = []
        for p in pulls:
            dup_txt = " *(doublon)*" if p["dup"] else ""
            desc_lines.append(f"• {p['display']} — `{p['rarete']}`{dup_txt}")

        # Résumé raretés
        sum_txt = " | ".join(f"{r}: {n}" for r, n in rarity_counts.items())

        embed = discord.Embed(title=title, color=discord.Color.gold())
        embed.add_field(name="Résultats", value="\n".join(desc_lines) or "—", inline=False)
        embed.set_footer(text=f"Raretés: {sum_txt} • Tickets restants: { _get_tickets(gid, uid) }")

        await interaction.followup.send(embed=embed)

    # --------------- Slash: /gacha_inventaire ---------------
    @app_commands.command(name="gacha_inventaire", description="Affiche ta collection de personnages.")
    async def gacha_inventory(self, interaction: discord.Interaction):
        if storage is None:
            return await interaction.response.send_message("⚠️ Système de stockage indisponible.", ephemeral=True)
        gid = str(interaction.guild_id) if interaction.guild else "dm"
        uid = str(interaction.user.id)
        u = _ensure_user_slot(gid, uid)
        chars: Dict[str, int] = dict(u.get("characters", {}))

        if not chars:
            return await interaction.response.send_message("Ta collection est vide. Utilise `/gacha` pour invoquer !", ephemeral=True)

        # On tente de mapper key -> display si possible
        by_key: Dict[str, str] = {}
        for c in self._chars:
            by_key[_get_char_key(c)] = _get_char_display(c)

        lines = []
        total = 0
        for key, qty in sorted(chars.items(), key=lambda kv: (-kv[1], kv[0])):
            disp = by_key.get(key, f"**{key}**")
            lines.append(f"• {disp} ×{qty}")
            total += qty

        embed = discord.Embed(
            title=f"📚 Collection de {interaction.user.display_name}",
            description="\n".join(lines)[:4000],
            color=discord.Color.blurple()
        )
        embed.set_footer(text=f"Total: {total} • Tickets: { _get_tickets(gid, uid) }")
        await interaction.response.send_message(embed=embed, ephemeral=True)


# ─────────────────────────────────────────────────────────────
# Setup extension
# ─────────────────────────────────────────────────────────────
async def setup(bot: commands.Bot):
    await bot.add_cog(Gacha(bot))

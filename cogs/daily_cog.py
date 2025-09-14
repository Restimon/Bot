# cogs/daily_cog.py
from __future__ import annotations

import time
import random
from typing import Dict, Tuple, Optional, List

import discord
from discord import app_commands
from discord.ext import commands

# -----------------------
# Constantes du DAILY
# -----------------------
DAILY_COOLDOWN = 24 * 3600           # 24h
STREAK_GRACE = 48 * 3600             # 48h pour conserver le streak
BASE_COINS_MIN = 20
BASE_COINS_MAX = 40
STREAK_BONUS_CAP = 25                # +max 25 coins

TICKET_EMOJI = "🎟️"

# -----------------------
# Dépendances souples
# -----------------------
# On essaye d'importer des fonctions précises depuis data.storage
_storage_get_user_data = None
_storage_set_user_coins = None
_storage_save_data = None
_storage_daily_container = None  # on stockera la réf vers le module pour y mettre .daily

try:
    from data import storage as _storage_daily_container  # type: ignore
    _storage_daily_container = _storage_daily_container
except Exception:
    _storage_daily_container = None

try:
    from data.storage import get_user_data as _storage_get_user_data  # type: ignore
except Exception:
    _storage_get_user_data = None

try:
    from data.storage import set_user_coins as _storage_set_user_coins  # type: ignore
except Exception:
    _storage_set_user_coins = None

try:
    from data.storage import save_data as _storage_save_data  # type: ignore
except Exception:
    _storage_save_data = None

# utilitaires de loot pondérés par rareté
try:
    from utils import get_random_item
except Exception:
    def get_random_item(debug: bool = False):
        return random.choice(["🍀", "❄️", "🧪", "🩹", "💊"])

# économie (optionnelle)
_add_coins_fn = None
try:
    # si tu as un module d’économie avec add_coins(gid, uid, delta)
    from economy_db import add_coins as _add_coins_fn  # type: ignore
except Exception:
    pass


def _get_daily_state() -> Dict:
    """
    Accède au conteneur daily persistant si possible, sinon garde en RAM.
    Structure attendue: daily[guild_id][user_id] = {"last": int, "streak": int}
    """
    # Persistance via data.storage si dispo
    if _storage_daily_container is not None:
        if not hasattr(_storage_daily_container, "daily") or not isinstance(getattr(_storage_daily_container, "daily"), dict):
            setattr(_storage_daily_container, "daily", {})
        return getattr(_storage_daily_container, "daily")

    # Fallback RAM non persistant
    if not hasattr(_get_daily_state, "_mem"):
        _get_daily_state._mem: Dict[str, Dict[str, Dict[str, int]]] = {}
    return _get_daily_state._mem  # type: ignore


def _get_user_data(gid: int, uid: int) -> Tuple[List[str], int, Optional[dict]]:
    """Toujours renvoyer (inventaire, coins, personnage)."""
    if callable(_storage_get_user_data):
        try:
            inv, coins, perso = _storage_get_user_data(str(gid), str(uid))  # type: ignore
            return inv, int(coins or 0), perso
        except Exception:
            pass
    # Fallback mémoire
    # On émule une structure minimale par serveur
    state = _get_daily_state()
    gkey, ukey = str(gid), str(uid)
    inv_key = f"_inv_{ukey}"
    coins_key = f"_coins_{ukey}"
    perso_key = f"_perso_{ukey}"
    state.setdefault(gkey, {})
    gspace = state[gkey]
    inv = gspace.get(inv_key, [])
    coins = int(gspace.get(coins_key, 0) or 0)
    perso = gspace.get(perso_key, None)
    return inv, coins, perso


def _persist_user_data(gid: int, uid: int, inv: Optional[List[str]] = None, coins: Optional[int] = None):
    """Écrit dans storage si possible, sinon dans le fallback RAM."""
    if coins is not None and callable(_storage_set_user_coins):
        try:
            _storage_set_user_coins(str(gid), str(uid), int(coins))  # type: ignore
        except Exception:
            # si set_user_coins échoue, on passera par RAM ci-dessous
            pass

    # Si on est en mode RAM (ou si on veut aussi y refléter)
    if _storage_daily_container is None or not callable(_storage_set_user_coins):
        state = _get_daily_state()
        gkey, ukey = str(gid), str(uid)
        inv_key = f"_inv_{ukey}"
        coins_key = f"_coins_{ukey}"
        state.setdefault(gkey, {})
        gspace = state[gkey]
        if inv is not None:
            gspace[inv_key] = inv
        if coins is not None:
            gspace[coins_key] = int(coins)

    _save()


def _save():
    """Sauvegarde si possible via data.storage.save_data()."""
    if callable(_storage_save_data):
        try:
            _storage_save_data()  # type: ignore
        except Exception:
            pass


def _add_coins(gid: int, uid: int, amount: int) -> int:
    """
    Ajoute des coins de façon robuste.
    - economy_db.add_coins si dispo
    - sinon via storage.set_user_coins si dispo
    - sinon fallback RAM
    Retourne le solde final estimé.
    """
    inv, coins_before, _ = _get_user_data(gid, uid)
    if amount == 0:
        return coins_before

    # chemin économie dédié si dispo
    if callable(_add_coins_fn):
        try:
            _add_coins_fn(str(gid), str(uid), int(amount))  # type: ignore
            _, coins_after, _ = _get_user_data(gid, uid)
            _save()
            return coins_after
        except Exception:
            pass

    coins_after = max(0, int(coins_before) + int(amount))
    _persist_user_data(gid, uid, inv=None, coins=coins_after)
    return coins_after


def _format_inventory_line(inv: List[str], limit: int = 20) -> str:
    """Petit format sympa pour un aperçu d’inventaire (utilisé dans l’embed)."""
    if not inv:
        return "_Inventaire vide_"
    counts: Dict[str, int] = {}
    for e in inv:
        if not isinstance(e, str):
            continue
        counts[e] = counts.get(e, 0) + 1
    parts = [f"{k} ×{v}" if v > 1 else f"{k}" for k, v in counts.items()]
    if len(parts) > limit:
        shown = ", ".join(parts[:limit])
        return shown + f" … (+{len(parts) - limit})"
    return ", ".join(parts)


class DailyCog(commands.Cog):
    """Récompense quotidienne avec streak."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ─────────────────────────────────────────────────────────
    # /daily
    # ─────────────────────────────────────────────────────────
    @app_commands.command(name="daily", description="Récupère ta récompense quotidienne.")
    async def daily(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)

        if not interaction.user or not interaction.guild:
            return await interaction.followup.send(
                "Commande indisponible en DM.", ephemeral=True
            )

        gid = interaction.guild.id
        uid = interaction.user.id
        now = int(time.time())

        daily_state = _get_daily_state()
        gkey, ukey = str(gid), str(uid)
        daily_state.setdefault(gkey, {})
        user_daily = daily_state[gkey].get(ukey, {"last": 0, "streak": 0})

        last = int(user_daily.get("last", 0) or 0)
        streak = int(user_daily.get("streak", 0) or 0)

        # Cooldown strict 24h
        if last and (now - last) < DAILY_COOLDOWN:
            reste = DAILY_COOLDOWN - (now - last)
            hh = reste // 3600
            mm = (reste % 3600) // 60
            ss = reste % 60
            return await interaction.followup.send(
                f"⏳ Tu as déjà pris ton daily. Reviens dans **{hh:02d}h {mm:02d}m {ss:02d}s**.",
                ephemeral=True,
            )

        # Gestion du streak : si on revient dans les 48h, on continue, sinon on repart à 1
        if last and (now - last) <= STREAK_GRACE:
            streak += 1
        else:
            streak = 1

        # Tirage récompenses
        base_coins = random.randint(BASE_COINS_MIN, BASE_COINS_MAX)
        bonus_coins = min(streak, STREAK_BONUS_CAP)  # +1 par jour de streak, cap 25
        total_coins = base_coins + bonus_coins

        # 2 objets selon rareté
        item1 = get_random_item()
        item2 = get_random_item()
        inv, coins_before, _ = _get_user_data(gid, uid)

        # ajout items & ticket
        inv.append(item1)
        inv.append(item2)
        inv.append(TICKET_EMOJI)

        # ajout coins
        coins_after = _add_coins(gid, uid, total_coins)

        # persiste last / streak
        daily_state[gkey][ukey] = {"last": now, "streak": streak}

        # persiste inventaire si on est en fallback RAM
        _persist_user_data(gid, uid, inv=inv, coins=None)
        _save()

        # Embed résultat
        e = discord.Embed(
            title="✅ Récompense quotidienne",
            color=discord.Color.green(),
        )
        e.set_author(name=f"{interaction.user.display_name}", icon_url=interaction.user.display_avatar.url)

        e.add_field(
            name="GotCoins",
            value=f"**+{total_coins}** (base {base_coins}  •  bonus streak {bonus_coins})\n"
                  f"Solde actuel : **{coins_after}**",
            inline=False,
        )
        e.add_field(
            name="Tickets",
            value=f"{TICKET_EMOJI} ×1",
            inline=True,
        )
        e.add_field(
            name="Objets",
            value=f"{item1}  {item2}",
            inline=True,
        )
        e.add_field(
            name="Streak",
            value=f"🔥 **{streak}** jour(s) consécutif(s)  •  bonus max = {STREAK_BONUS_CAP}",
            inline=False,
        )

        # petit aperçu inventaire (optionnel)
        preview = _format_inventory_line(inv, limit=12)
        e.add_field(
            name="Inventaire (aperçu)",
            value=preview,
            inline=False,
        )

        await interaction.followup.send(embed=e, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(DailyCog(bot))

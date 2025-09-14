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
# storage: inventaire + persistance JSON (déjà utilisé partout dans ton projet)
try:
    from data import storage
except Exception:
    storage = None

# utilitaires de loot pondérés par rareté
try:
    from utils import get_random_item
except Exception:
    def get_random_item(debug: bool = False):
        return random.choice(["🍀", "❄️", "🧪", "🩹", "💊"])

# économie (facultatif) – on essaie d’appeler une API dédiée si elle existe
_add_coins_fn = None
try:
    # si tu as un module d’économie avec une fonction "add_coins(gid, uid, delta)"
    from economy_db import add_coins as _add_coins_fn  # type: ignore
except Exception:
    pass


def _get_daily_state():
    """
    Accès sûr au conteneur de daily dans storage.
    On garde tout sur storage.daily[guild_id][user_id] = {"last": int, "streak": int}
    """
    if storage is None:
        # fallback minimaliste en mémoire (non persistant)
        if not hasattr(_get_daily_state, "_mem"):
            _get_daily_state._mem = {}
        return _get_daily_state._mem  # type: ignore
    if not hasattr(storage, "daily") or not isinstance(getattr(storage, "daily"), dict):
        storage.daily = {}
    return storage.daily


def _get_user_data(gid: int, uid: int) -> Tuple[List[str], int, Optional[dict]]:
    """Toujours renvoyer (inventaire, coins, personnage)."""
    if storage is None:
        return [], 0, None
    inv, coins, perso = storage.get_user_data(str(gid), str(uid))
    return inv, coins, perso


def _save():
    """Sauvegarde si possible."""
    if storage is not None and hasattr(storage, "save_data"):
        try:
            storage.save_data()
        except Exception:
            pass


def _add_coins(gid: int, uid: int, amount: int) -> int:
    """
    Ajoute des coins de façon robuste.
    - Si economy_db.add_coins existe → on l'utilise
    - Sinon on écrit directement dans storage.get_user_data(...)
    Retourne le solde final estimé.
    """
    if amount == 0:
        inv, coins, _ = _get_user_data(gid, uid)
        return coins

    # chemin économie dédié si dispo
    if callable(_add_coins_fn):
        try:
            _add_coins_fn(str(gid), str(uid), int(amount))
            inv, coins, _ = _get_user_data(gid, uid)
            _save()
            return coins
        except Exception:
            pass

    # fallback: modifier directement le solde dans storage
    inv, coins, perso = _get_user_data(gid, uid)
    coins = int(coins) + int(amount)
    coins = max(0, coins)
    # on pousse la valeur dans le storage si possible
    if storage is not None and hasattr(storage, "set_user_coins"):
        try:
            storage.set_user_coins(str(gid), str(uid), coins)  # type: ignore
        except Exception:
            # dernier fallback: si set_user_coins n’existe pas, on essaie d'écrire directement
            try:
                # beaucoup de projets stockent ça sous storage.wallet[gid][uid]
                if hasattr(storage, "wallet"):
                    storage.wallet.setdefault(str(gid), {})[str(uid)] = coins  # type: ignore
            except Exception:
                pass
    else:
        try:
            if hasattr(storage, "wallet"):
                storage.wallet.setdefault(str(gid), {})[str(uid)] = coins  # type: ignore
        except Exception:
            pass

    _save()
    return coins


def _format_inventory_line(inv: List[str], limit: int = 20) -> str:
    """
    Petit format sympa pour un aperçu d’inventaire (utilisé dans l’embed).
    """
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

# cogs/daily_cog.py
from __future__ import annotations

import time
import random
from typing import Dict, Tuple, List, Any

import discord
from discord import app_commands
from discord.ext import commands

# ----- Import du bon storage (racine d'abord, puis data.storage) -----
try:
    import storage  # <- privilégier la même cible que utils.py, ravitaillement, etc.
except Exception:
    try:
        from data import storage  # fallback si ton projet l’expose comme package
    except Exception:
        storage = None  # dernier filet (mémoire volatile)

try:
    from utils import get_random_item
except Exception:
    def get_random_item(debug: bool = False):
        return random.choice(["🍀", "❄️", "🧪", "🩹", "💊"])

TICKET_EMOJI = "🎟️"
DAILY_COOLDOWN = 24 * 3600          # 24h
STREAK_WINDOW = 48 * 3600           # streak conservé si on reclique < 48h
STREAK_BONUS_CAP = 25               # +1/jour jusqu'à 25 max

# ---------------------------------------------------------------------------
# Helpers de compat avec ton storage
# ---------------------------------------------------------------------------

def _now() -> float:
    return time.time()

def _ensure_daily_slot() -> Dict[str, Dict[str, Dict[str, Any]]]:
    """
    Crée/retourne storage.daily (persistant) ou une mémoire locale si storage indispo.
    Structure: storage.daily[guild_id][user_id] = {"last": ts, "streak": int}
    """
    if storage is None:
        if not hasattr(_ensure_daily_slot, "_mem"):
            _ensure_daily_slot._mem = {}
        return _ensure_daily_slot._mem  # type: ignore[attr-defined]

    if not hasattr(storage, "daily") or not isinstance(getattr(storage, "daily"), dict):
        storage.daily = {}
    return storage.daily

def _get_user_data(gid: int | str, uid: int | str) -> Tuple[List[Any], int, Any]:
    gid = str(gid); uid = str(uid)
    if storage is None:
        d = getattr(_get_user_data, "_mem", {})
        if not d:
            _get_user_data._mem = d = {}
        d.setdefault(gid, {}).setdefault(uid, {"inv": [], "coins": 0, "perso": None})
        rec = d[gid][uid]
        return rec["inv"], rec["coins"], rec["perso"]

    # API standard de ton projet
    if hasattr(storage, "get_user_data"):
        inv, coins, perso = storage.get_user_data(gid, uid)
        return inv, int(coins or 0), perso

    # API alternative possible
    if hasattr(storage, "get_or_create_user"):
        u = storage.get_or_create_user(gid, uid)
        u.setdefault("inventory", [])
        u.setdefault("coins", 0)
        return u["inventory"], int(u["coins"]), u.get("personnage")

    raise RuntimeError("Impossible de lire les données utilisateur depuis storage.")

def _add_user_coins(gid: int | str, uid: int | str, delta: int) -> int:
    """Ajoute 'delta' au solde et renvoie le nouveau solde."""
    gid = str(gid); uid = str(uid)
    inv, coins, perso = _get_user_data(gid, uid)
    new_amount = int(coins) + int(delta)

    if storage is None:
        d = getattr(_get_user_data, "_mem", {})
        d[gid][uid]["coins"] = new_amount
        return new_amount

    # Priorité à des API dédiées si elles existent
    if hasattr(storage, "add_coins"):
        storage.add_coins(gid, uid, int(delta))
        return new_amount

    if hasattr(storage, "set_user_coins"):
        storage.set_user_coins(gid, uid, int(new_amount))
        return new_amount

    if hasattr(storage, "set_user_data"):
        storage.set_user_data(gid, uid, inv, int(new_amount), perso)
        return new_amount

    # Dernier recours: écrire dans storage.data si présent
    if hasattr(storage, "data") and isinstance(storage.data, dict):
        storage.data.setdefault(gid, {}).setdefault(uid, {})
        storage.data[gid][uid]["coins"] = int(new_amount)

    return new_amount

def _save():
    if storage is not None and hasattr(storage, "save_data"):
        try:
            storage.save_data()
        except Exception:
            pass

# ---------------------------------------------------------------------------
# Le COG
# ---------------------------------------------------------------------------

class DailyCog(commands.Cog):
    """Récompense quotidienne : 24h de CD, streak, 1 ticket + 2 objets + coins."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _fmt_delta(self, seconds: float) -> str:
        seconds = max(0, int(seconds))
        h = seconds // 3600
        m = (seconds % 3600) // 60
        s = seconds % 60
        parts = []
        if h: parts.append(f"{h}h")
        if m: parts.append(f"{m}m")
        if s or not parts: parts.append(f"{s}s")
        return " ".join(parts)

    @app_commands.command(name="daily", description="Récupère ta récompense quotidienne.")
    async def daily(self, interaction: discord.Interaction):
        gid = interaction.guild_id
        if not gid:
            await interaction.response.send_message(
                "Cette commande doit être utilisée dans un serveur.",
                ephemeral=True
            )
            return
        uid = interaction.user.id

        inv, coins_before, _ = _get_user_data(gid, uid)

        # Streak & cooldown
        daily_map = _ensure_daily_slot()
        gmap = daily_map.setdefault(str(gid), {})
        urec = gmap.setdefault(str(uid), {"last": 0.0, "streak": 0})
        now = _now()
        last = float(urec.get("last", 0.0))
        streak = int(urec.get("streak", 0))

        remaining = (last + DAILY_COOLDOWN) - now
        if remaining > 0:
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="⏳ Daily déjà récupéré",
                    description=f"Reviens dans **{self._fmt_delta(remaining)}**.",
                    color=discord.Color.orange(),
                ),
                ephemeral=True
            )
            return

        if last > 0 and (now - last) <= STREAK_WINDOW:
            streak += 1
        else:
            streak = 1

        # Gains
        base = random.randint(25, 35)
        bonus = min(streak, STREAK_BONUS_CAP)
        coins_gain = base + bonus

        # Tickets & objets (persistants car 'inv' vient du storage)
        inv.append(TICKET_EMOJI)
        item1 = get_random_item()
        item2 = get_random_item()
        inv.append(item1)
        inv.append(item2)

        # Mise à jour des coins via un setter compatible
        coins_after = _add_user_coins(gid, uid, coins_gain)

        # Sauvegarde du daily + data
        urec["last"] = now
        urec["streak"] = streak
        _save()

        # Embed public
        embed = discord.Embed(
            title="✅ Récompense quotidienne",
            color=discord.Color.green(),
        )
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        embed.add_field(name="GotCoins", value=f"{coins_gain} *(base {base} · bonus streak {bonus})*", inline=False)
        embed.add_field(name="Tickets", value=f"{TICKET_EMOJI} ×1", inline=True)
        embed.add_field(name="Objets", value=f"{item1} {item2}", inline=True)
        embed.add_field(name="Solde", value=f"{coins_after}", inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=False)


async def setup(bot: commands.Bot):
    await bot.add_cog(DailyCog(bot))

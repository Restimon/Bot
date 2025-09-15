# cogs/daily_cog.py
from __future__ import annotations

import time
import random
import math
from typing import Dict, Tuple, List, Any, Optional

import discord
from discord import app_commands
from discord.ext import commands

# ----- Imports tolérants -----
try:
    from data import storage  # ton module de persistance
except Exception:  # fallback léger
    storage = None

try:
    from utils import get_random_item
except Exception:
    def get_random_item(debug: bool = False):
        return random.choice(["🍀", "❄️", "🧪", "🩹", "💊"])

TICKET_EMOJI = "🎟️"
DAILY_COOLDOWN = 24 * 3600          # 24h
STREAK_WINDOW = 48 * 3600           # on garde le streak si on reclame < 48h
STREAK_BONUS_CAP = 25               # bonus max appliqué

# ---------------------------------------------------------------------------
# Helpers de compatibilité avec ton storage
# ---------------------------------------------------------------------------

def _now() -> float:
    return time.time()

def _ensure_daily_slot() -> Dict[str, Dict[str, Dict[str, Any]]]:
    """
    Crée un magasin daily si absent.
    Structure: storage.daily[guild_id][user_id] = {"last": ts, "streak": int}
    """
    if storage is None:
        # fallback mémoire très minimal si storage pas dispo
        if not hasattr(_ensure_daily_slot, "_mem"):
            _ensure_daily_slot._mem = {}
        return _ensure_daily_slot._mem  # type: ignore[attr-defined]

    if not hasattr(storage, "daily") or not isinstance(getattr(storage, "daily"), dict):
        storage.daily = {}
    return storage.daily

def _get_user_data(gid: int | str, uid: int | str) -> Tuple[List[Any], int, Any]:
    """
    Essaie d'utiliser storage.get_user_data(gid, uid) -> (inv, coins, personnage)
    Fallback si tu as une autre forme de stockage.
    """
    gid = str(gid); uid = str(uid)
    if storage is None:
        # fallback mémoire
        d = getattr(_get_user_data, "_mem", {})
        if not d:
            _get_user_data._mem = d = {}
        d.setdefault(gid, {}).setdefault(uid, {"inv": [], "coins": 0, "perso": None})
        rec = d[gid][uid]
        return rec["inv"], rec["coins"], rec["perso"]

    # cas standard (ton utils.py s’attend à cette signature)
    if hasattr(storage, "get_user_data"):
        inv, coins, perso = storage.get_user_data(gid, uid)
        return inv, int(coins or 0), perso

    # autre API éventuelle : get_or_create_user -> dict
    if hasattr(storage, "get_or_create_user"):
        u = storage.get_or_create_user(gid, uid)
        u.setdefault("inventory", [])
        u.setdefault("coins", 0)
        return u["inventory"], int(u["coins"]), u.get("personnage")

    # dernier filet
    raise RuntimeError("Aucune API compatible trouvée dans data.storage pour lire l'utilisateur.")

def _set_user_coins(gid: int | str, uid: int | str, new_amount: int) -> None:
    gid = str(gid); uid = str(uid)
    if storage is None:
        d = getattr(_get_user_data, "_mem", {})
        d.setdefault(gid, {}).setdefault(uid, {"inv": [], "coins": 0, "perso": None})
        d[gid][uid]["coins"] = int(new_amount)
        return

    if hasattr(storage, "set_user_coins"):
        storage.set_user_coins(gid, uid, int(new_amount))
        return

    # si get_user_data renvoie une structure modifiable, on l'écrase puis save
    if hasattr(storage, "get_user_data"):
        inv, _, perso = storage.get_user_data(gid, uid)
        # petite astuce: certaines implémentations mettent coins par référence
        # si non, on essaye une API générique
        if hasattr(storage, "set_user_data"):
            storage.set_user_data(gid, uid, inv, int(new_amount), perso)
        else:
            # tente d'accéder à un dict sous-jacent
            if hasattr(storage, "data") and isinstance(storage.data, dict):
                storage.data.setdefault(gid, {}).setdefault(uid, {})
                storage.data[gid][uid]["coins"] = int(new_amount)

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

    # Petit utilitaire pour le texte temps restant
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

        # Lecture user + compteur daily
        inv, coins_before, _ = _get_user_data(gid, uid)
        daily_map = _ensure_daily_slot()
        gmap = daily_map.setdefault(str(gid), {})
        urec = gmap.setdefault(str(uid), {"last": 0.0, "streak": 0})

        now = _now()
        last = float(urec.get("last", 0.0))
        streak = int(urec.get("streak", 0))

        # Cooldown strict 24h
        remaining = (last + DAILY_COOLDOWN) - now
        if remaining > 0:
            # on répond en éphémère ici (évite le spam public)
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="⏳ Daily déjà récupéré",
                    description=f"Reviens dans **{self._fmt_delta(remaining)}**.",
                    color=discord.Color.orange(),
                ),
                ephemeral=True
            )
            return

        # Gestion du streak : si on revient < 48h après le dernier claim, +1, sinon reset
        if last > 0 and (now - last) <= STREAK_WINDOW:
            streak += 1
        else:
            streak = 1  # on recommence

        # Gains
        base = random.randint(25, 35)
        bonus = min(streak, STREAK_BONUS_CAP)
        coins_gain = base + bonus

        # Tickets & objets
        inv.append(TICKET_EMOJI)
        item1 = get_random_item()
        item2 = get_random_item()
        inv.append(item1)
        inv.append(item2)

        # Mise à jour solde
        coins_after = coins_before + coins_gain
        _set_user_coins(gid, uid, coins_after)

        # Mémorise daily
        urec["last"] = now
        urec["streak"] = streak
        _save()

        # Embed public (succès)
        embed = discord.Embed(
            title="✅ Récompense quotidienne",
            color=discord.Color.green(),
        )
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)

        # GotCoins : afficher le gain du jour (sans +) + détail base/bonus
        embed.add_field(
            name="GotCoins",
            value=f"{coins_gain} *(base {base} · bonus streak {bonus})*",
            inline=False,
        )

        # Tickets
        embed.add_field(
            name="Tickets",
            value=f"{TICKET_EMOJI} ×1",
            inline=True
        )

        # Objets
        embed.add_field(
            name="Objets",
            value=f"{item1} {item2}",
            inline=True
        )

        # Solde (à la fin, montant actuel seulement)
        embed.add_field(
            name="Solde",
            value=f"{coins_after}",
            inline=False
        )

        await interaction.response.send_message(embed=embed, ephemeral=False)


async def setup(bot: commands.Bot):
    await bot.add_cog(DailyCog(bot))

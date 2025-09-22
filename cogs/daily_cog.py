# cogs/daily_cog.py
from __future__ import annotations

import random
import time
from typing import Dict, List, Optional, Tuple

import discord
from discord.ext import commands
from discord import app_commands

# ── Économie & Inventaire (SQLite)
from economy_db import add_balance, get_balance
from inventory_db import add_item

# ── Passifs
from passifs import trigger

# ── Objets (emoji) + tirage tolérant
try:
    from utils import OBJETS, get_random_item  # type: ignore
except Exception:
    OBJETS = {}
    def get_random_item(debug: bool = False):
        return random.choice(["🍀", "❄️", "🧪", "🩹", "💊"])

# ── Storage JSON optionnel (tickets + cooldowns + streak)
try:
    from data import storage  # type: ignore
except Exception:
    storage = None  # type: ignore


# ======================================================================
# Helpers storage : tickets, cooldowns, streaks
# ======================================================================

def _now() -> int:
    return int(time.time())

def _ensure_map(obj, name: str):
    if not hasattr(obj, name) or not isinstance(getattr(obj, name), dict):
        setattr(obj, name, {})

def _get_guild_map(root: Dict, gid: int) -> Dict:
    root.setdefault(str(gid), {})
    return root[str(gid)]

def _get_user_int(map_: Dict, uid: int, default: int = 0) -> int:
    try:
        return int(map_.get(str(uid), default))
    except Exception:
        return default

def _set_user_int(map_: Dict, uid: int, value: int):
    map_[str(uid)] = int(value)

def _save_storage():
    try:
        if storage and hasattr(storage, "save_data"):
            storage.save_data()
    except Exception:
        pass

# Tickets
def get_tickets(gid: int, uid: int) -> int:
    if not storage:
        return 0
    _ensure_map(storage, "tickets")                # storage.tickets = {}
    gmap = _get_guild_map(storage.tickets, gid)    # storage.tickets[gid] = {}
    return _get_user_int(gmap, uid, 0)

def add_tickets(gid: int, uid: int, delta: int) -> int:
    if not storage:
        return 0
    _ensure_map(storage, "tickets")
    gmap = _get_guild_map(storage.tickets, gid)
    cur = _get_user_int(gmap, uid, 0)
    cur += int(delta or 0)
    _set_user_int(gmap, uid, cur)
    _save_storage()
    return cur

# Cooldown daily
def get_last_daily_ts(gid: int, uid: int) -> int:
    if not storage:
        return 0
    _ensure_map(storage, "cooldowns")                          # storage.cooldowns = {}
    cdm = storage.cooldowns
    cdm.setdefault("daily", {})
    d_gmap = _get_guild_map(cdm["daily"], gid)                 # storage.cooldowns["daily"][gid] = {}
    return _get_user_int(d_gmap, uid, 0)

def set_last_daily_ts(gid: int, uid: int, ts: int):
    if not storage:
        return
    _ensure_map(storage, "cooldowns")
    cdm = storage.cooldowns
    cdm.setdefault("daily", {})
    d_gmap = _get_guild_map(cdm["daily"], gid)
    _set_user_int(d_gmap, uid, ts)
    _save_storage()

# Streak
STREAK_MAX_GAP = 48 * 3600  # max 48h d’écart pour garder la série

def get_streak_count(gid: int, uid: int) -> int:
    if not storage:
        return 0
    _ensure_map(storage, "streaks")               # storage.streaks = {}
    gmap = _get_guild_map(storage.streaks, gid)   # storage.streaks[gid] = {}
    try:
        data = gmap.get(str(uid)) or {}
        return int(data.get("count", 0))
    except Exception:
        return 0

def _set_streak(gid: int, uid: int, count: int):
    if not storage:
        return
    _ensure_map(storage, "streaks")
    gmap = _get_guild_map(storage.streaks, gid)
    cur = gmap.get(str(uid)) or {}
    cur["count"] = int(count)
    gmap[str(uid)] = cur
    _save_storage()

def update_streak_after_claim(gid: int, uid: int, last_ts: int, now_ts: int) -> int:
    """Retourne le nouveau count, en conservant la série si le dernier claim < 48h."""
    prev = get_streak_count(gid, uid)
    if last_ts <= 0:
        new = 1
    else:
        delta = now_ts - last_ts
        new = (prev + 1) if delta <= STREAK_MAX_GAP else 1
    _set_streak(gid, uid, new)
    return new

def fmt_duration(seconds: int) -> str:
    if seconds <= 0:
        return "0s"
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h}h {m}m {s}s"
    if m > 0:
        return f"{m}m {s}s"
    return f"{s}s"


# ======================================================================
# DAILY
# ======================================================================

DAILY_BASE_SECONDS = 24 * 3600  # CD de base (Nyra Kell le divise par 2)
COINS_MIN, COINS_MAX = 8, 25
TICKETS_MIN, TICKETS_MAX = 0, 1
ITEMS_MIN, ITEMS_MAX = 0, 3
STREAK_BONUS_CAP = 10  # bonus coins = min(streak, cap)

class DailyCog(commands.Cog):
    """Récompense quotidienne : GotCoins, Tickets, Objets (emoji) + streak."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ---------------------------------------------------------
    # /daily
    # ---------------------------------------------------------
    @app_commands.command(name="daily", description="Récupère ta récompense quotidienne.")
    async def daily(self, interaction: discord.Interaction):
        if not interaction.guild:
            return await interaction.response.send_message("Commande serveur uniquement.", ephemeral=True)

        gid = interaction.guild.id
        uid = interaction.user.id
        now = _now()

        # Cooldown (avec passifs)
        last_ts = get_last_daily_ts(gid, uid)
        base_cd = DAILY_BASE_SECONDS
        cooldown = {"mult": 1.0}

        # Tirage préliminaire
        coins = random.randint(COINS_MIN, COINS_MAX)
        tickets = random.randint(TICKETS_MIN, TICKETS_MAX)
        nb_items = random.randint(ITEMS_MIN, ITEMS_MAX)
        items: List[str] = [get_random_item(debug=False) for _ in range(nb_items)]

        # Passifs (peuvent modifier rewards ET cooldown)
        rewards = {"coins": coins, "tickets": tickets, "items": list(items)}
        try:
            res = await trigger("on_daily", user_id=uid, rewards=rewards, cooldown=cooldown) or {}
        except Exception:
            res = {}
        coins = int(rewards.get("coins", coins))
        tickets = int(rewards.get("tickets", tickets))
        items = list(rewards.get("items", items))

        # CD effectif
        effective_cd = int(base_cd * float(cooldown.get("mult", 1.0)))
        remain = (last_ts + effective_cd) - now
        if remain > 0:
            return await interaction.response.send_message(
                f"⏱️ Tu pourras reprendre un daily dans **{fmt_duration(remain)}**.",
                ephemeral=True
            )

        await interaction.response.defer(thinking=True)

        # Streak (si storage dispo)
        streak = 0
        streak_bonus = 0
        if storage:
            streak = update_streak_after_claim(gid, uid, last_ts, now)
            streak_bonus = min(streak, STREAK_BONUS_CAP)
            coins += streak_bonus

        # Appliquer les gains
        await add_balance(uid, coins)           # GotCoins
        tickets_total = None
        if tickets > 0:
            tickets_total = add_tickets(gid, uid, tickets)  # Tickets (JSON)

        # Objets → inventaire DB (agrégé)
        bag: Dict[str, int] = {}
        for it in items:
            bag[it] = bag.get(it, 0) + 1
        for emo, qty in bag.items():
            await add_item(uid, emo, qty)

        # Sauvegarde du CD
        set_last_daily_ts(gid, uid, now)

        # Leaderboard live (si dispo)
        try:
            from cogs.leaderboard_live import schedule_lb_update
            schedule_lb_update(self.bot, gid, "daily")
        except Exception:
            pass

        # Construction de l'embed (style “ancien”)
        emb = discord.Embed(
            title="🎁 Récompense quotidienne",
            color=discord.Color.gold()
        )

        # Ligne Streak
        if streak > 0:
            emb.description = f"Streak : **{streak}** (bonus **+{streak_bonus}**)"
        else:
            emb.description = None

        # GotCoins gagnés
        emb.add_field(name="GotCoins gagnés", value=f"+{coins}", inline=False)

        # Tickets séparés (avec total)
        if tickets > 0:
            if tickets_total is None:
                tickets_total = get_tickets(gid, uid)
            emb.add_field(name="🎟 Tickets", value=f"+{tickets} (total: {tickets_total})", inline=False)

        # Objets (avec petits détails)
        def _item_line(emoji: str, qty: int) -> str:
            info = OBJETS.get(emoji) or {}
            typ = info.get("type")
            detail = ""
            try:
                if typ == "attaque":
                    d = int(info.get("degats", 0) or 0)
                    if d: detail = f" [Dégâts {d}]"
                elif typ == "attaque_chaine":
                    d1 = int(info.get("degats_principal", 0) or 0)
                    d2 = int(info.get("degats_secondaire", 0) or 0)
                    if d1 or d2: detail = f" [Dégâts {d1}+{d2}]"
                elif typ == "soin":
                    s = int(info.get("soin", 0) or 0)
                    if s: detail = f" [Soin {s}]"
                elif typ in ("poison", "infection", "brulure", "virus"):
                    d = int(info.get("degats", 0) or 0)
                    itv = int(info.get("intervalle", 60) or 60)
                    if d: detail = f" [DoT {d}/{max(1,itv)//60}m]"
                elif typ == "regen":
                    v = int(info.get("valeur", 0) or 0)
                    itv = int(info.get("intervalle", 60) or 60)
                    if v: detail = f" [Regen +{v}/{max(1,itv)//60}m]"
            except Exception:
                pass
            if qty > 1:
                return f"1x {emoji}{detail}  +  … ×{qty-1}"
            return f"1x {emoji}{detail}"

        if bag:
            lines = [_item_line(emo, qty) for emo, qty in bag.items()]
            emb.add_field(name="Objets", value="\n".join(lines), inline=False)
        else:
            emb.add_field(name="Objets", value="—", inline=False)

        # Solde actuel
        try:
            bal = await get_balance(uid)
            emb.add_field(name="Solde actuel", value=str(bal), inline=False)
        except Exception:
            pass

        emb.set_footer(text=f"Prochain daily dans ~{fmt_duration(effective_cd)}.")

        await interaction.followup.send(embed=emb)


async def setup(bot: commands.Bot):
    await bot.add_cog(DailyCog(bot))

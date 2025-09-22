# cogs/daily_cog.py
from __future__ import annotations

import random
import time
from typing import Dict, List, Optional

import discord
from discord.ext import commands
from discord import app_commands

from economy_db import add_balance, get_balance
from inventory_db import add_item
from passifs import trigger

try:
    from utils import OBJETS, get_random_item  # type: ignore
except Exception:
    OBJETS = {}
    def get_random_item(debug: bool = False):
        return random.choice(["🍀", "❄️", "🧪", "🩹", "💊"])

# Storage JSON (tickets, cooldowns, streak)
try:
    from data import storage  # type: ignore
except Exception:
    storage = None  # type: ignore


# =============== Helpers storage (tickets / cooldown / streak) ===============

def _now() -> int:
    return int(time.time())

def _ensure_map(obj, name: str):
    if not hasattr(obj, name) or not isinstance(getattr(obj, name), dict):
        setattr(obj, name, {})

def _guild_map(root: Dict, gid: int) -> Dict:
    root.setdefault(str(gid), {})
    return root[str(gid)]

def _get_user_int(m: Dict, uid: int, default: int = 0) -> int:
    try:
        return int(m.get(str(uid), default))
    except Exception:
        return default

def _set_user_int(m: Dict, uid: int, value: int):
    m[str(uid)] = int(value)

def _save_storage():
    try:
        if storage and hasattr(storage, "save_data"):
            storage.save_data()
    except Exception:
        pass

# Tickets
def get_tickets(gid: int, uid: int) -> int:
    if not storage: return 0
    _ensure_map(storage, "tickets")
    gmap = _guild_map(storage.tickets, gid)
    return _get_user_int(gmap, uid, 0)

def add_tickets(gid: int, uid: int, delta: int) -> int:
    if not storage: return 0
    _ensure_map(storage, "tickets")
    gmap = _guild_map(storage.tickets, gid)
    cur = _get_user_int(gmap, uid, 0) + int(delta or 0)
    _set_user_int(gmap, uid, cur)
    _save_storage()
    return cur

# Cooldown
def get_last_daily_ts(gid: int, uid: int) -> int:
    if not storage: return 0
    _ensure_map(storage, "cooldowns")
    storage.cooldowns.setdefault("daily", {})
    gmap = _guild_map(storage.cooldowns["daily"], gid)
    return _get_user_int(gmap, uid, 0)

def set_last_daily_ts(gid: int, uid: int, ts: int):
    if not storage: return
    _ensure_map(storage, "cooldowns")
    storage.cooldowns.setdefault("daily", {})
    gmap = _guild_map(storage.cooldowns["daily"], gid)
    _set_user_int(gmap, uid, ts)
    _save_storage()

# Streak (conservé si on ne dépasse pas 48h entre deux claims)
STREAK_MAX_GAP = 48 * 3600

def get_streak(gid: int, uid: int) -> int:
    if not storage: return 0
    _ensure_map(storage, "streaks")
    gmap = _guild_map(storage.streaks, gid)
    try:
        return int((gmap.get(str(uid)) or {}).get("count", 0))
    except Exception:
        return 0

def set_streak(gid: int, uid: int, count: int):
    if not storage: return
    _ensure_map(storage, "streaks")
    gmap = _guild_map(storage.streaks, gid)
    row = gmap.get(str(uid)) or {}
    row["count"] = int(count)
    gmap[str(uid)] = row
    _save_storage()

def update_streak_after_claim(gid: int, uid: int, last_ts: int, now_ts: int) -> int:
    prev = get_streak(gid, uid)
    if last_ts <= 0:
        cur = 1
    else:
        cur = prev + 1 if (now_ts - last_ts) <= STREAK_MAX_GAP else 1
    set_streak(gid, uid, cur)
    return cur

def fmt_duration(seconds: int) -> str:
    seconds = max(0, int(seconds))
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h: return f"{h}h {m}m {s}s"
    if m: return f"{m}m {s}s"
    return f"{s}s"


# ================================== DAILY ===================================

DAILY_BASE_SECONDS = 24 * 3600
COINS_MIN, COINS_MAX = 8, 25
STREAK_BONUS_CAP = 10

class DailyCog(commands.Cog):
    """Récompense quotidienne (coins + streak, 1 ticket garanti, 2 objets aléatoires)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="daily", description="Récupère ta récompense quotidienne.")
    async def daily(self, interaction: discord.Interaction):
        if not interaction.guild:
            return await interaction.response.send_message("Commande serveur uniquement.", ephemeral=True)

        gid = interaction.guild.id
        uid = interaction.user.id
        now = _now()

        # Cooldown de base (modifiable par passifs via on_daily -> cooldown['mult'])
        last_ts = get_last_daily_ts(gid, uid)
        base_cd = DAILY_BASE_SECONDS
        cooldown = {"mult": 1.0}

        # Récompenses de base style "ancien daily"
        coins = random.randint(COINS_MIN, COINS_MAX)
        tickets = 1                              # ← 1 ticket garanti
        items: List[str] = [get_random_item(False), get_random_item(False)]  # ← 2 objets garantis

        rewards = {"coins": coins, "tickets": tickets, "items": list(items)}

        # Passifs (Lior, Nyra, etc.) — peuvent modifier rewards et/ou cooldown
        try:
            _ = await trigger("on_daily", user_id=uid, rewards=rewards, cooldown=cooldown) or {}
        except Exception:
            pass
        coins = int(rewards.get("coins", coins))
        tickets = int(rewards.get("tickets", tickets))
        items = list(rewards.get("items", items))

        effective_cd = int(base_cd * float(cooldown.get("mult", 1.0)))
        remain = (last_ts + effective_cd) - now
        if remain > 0:
            return await interaction.response.send_message(
                f"⏱️ Tu pourras reprendre un daily dans **{fmt_duration(remain)}**.",
                ephemeral=True
            )

        await interaction.response.defer(thinking=True)

        # Streak + bonus
        streak = 0
        bonus = 0
        if storage:
            streak = update_streak_after_claim(gid, uid, last_ts, now)
            bonus = min(streak, STREAK_BONUS_CAP)
            coins += bonus

        # Appliquer les gains
        await add_balance(uid, coins)

        tickets_total = None
        if tickets > 0:
            tickets_total = add_tickets(gid, uid, tickets)

        # Ajouter les objets (un par un) et préparer l’affichage
        lines: List[str] = []
        for emo in items:
            await add_item(uid, emo, 1)
            info = OBJETS.get(emo) or {}
            detail = ""
            try:
                typ = info.get("type")
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
            lines.append(f"1x {emo}{detail}")

        # Sauver le CD
        set_last_daily_ts(gid, uid, now)

        # LB live
        try:
            from cogs.leaderboard_live import schedule_lb_update
            schedule_lb_update(self.bot, gid, "daily")
        except Exception:
            pass

        # ── Embed “ancien style”
        emb = discord.Embed(title="🎁 Récompense quotidienne", color=discord.Color.gold())
        if streak > 0:
            emb.description = f"Streak : **{streak}** (bonus **+{bonus}**)"
        emb.add_field(name="GotCoins gagnés", value=f"+{coins}", inline=False)

        # Tickets / Objets côte-à-côte
        if tickets > 0:
            if tickets_total is None:
                tickets_total = get_tickets(gid, uid)
            emb.add_field(name="🎟 Tickets", value=f"+{tickets} (total: {tickets_total})", inline=True)
        else:
            emb.add_field(name="🎟 Tickets", value="—", inline=True)

        emb.add_field(name="Objets", value="\n".join(lines) if lines else "—", inline=True)

        # Solde actuel
        try:
            bal = await get_balance(uid)
            emb.add_field(name="Solde actuel", value=str(bal), inline=False)
        except Exception:
            pass

        # (pas de footer “prochain daily” pour coller à l’ancien visuel)
        await interaction.followup.send(embed=emb)


async def setup(bot: commands.Bot):
    await bot.add_cog(DailyCog(bot))

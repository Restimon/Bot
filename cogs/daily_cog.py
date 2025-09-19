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

# ── Storage JSON optionnel (tickets + cooldowns)
try:
    from data import storage  # type: ignore
except Exception:
    storage = None  # type: ignore


# ======================================================================
# Helpers storage : tickets & cooldowns
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

class DailyCog(commands.Cog):
    """Récompense quotidienne : GotCoins, Tickets, Objets (emoji)."""

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
        await trigger("on_daily", user_id=uid, rewards=rewards, cooldown=cooldown)
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

        # Appliquer les gains
        await add_balance(uid, coins)           # GotCoins
        if tickets > 0:
            add_tickets(gid, uid, tickets)      # Tickets (JSON)
        # Objets → inventaire DB
        # Agrège et ajoute
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

        # Construction de l'embed
        emb = discord.Embed(
            title="🎁 Récompense quotidienne",
            color=discord.Color.gold()
        )
        # Ligne Coins + Tickets (sur la même ligne)
        coins_txt = f"💰 **{coins}**"
        tickets_txt = f" • 🎟️ **{tickets}**" if tickets > 0 else ""
        emb.add_field(name="Ressources", value=f"{coins_txt}{tickets_txt}", inline=False)

        # Objets : affichage en colonnes à partir de 6 lignes, sinon 1/ligne
        if bag:
            lines = [f"{emo} ×{qty}" if qty > 1 else f"{emo} ×1" for emo, qty in bag.items()]
            if len(lines) >= 6:
                # 2 colonnes, remplissage colonne par colonne
                half = (len(lines) + 1) // 2
                col1 = "\n".join(lines[:half])
                col2 = "\n".join(lines[half:])
                emb.add_field(name="Objets", value=col1, inline=True)
                emb.add_field(name="\u200b", value=col2 or "\u200b", inline=True)
            else:
                emb.add_field(name="Objets", value="\n".join(lines), inline=False)
        else:
            emb.add_field(name="Objets", value="—", inline=False)

        emb.set_footer(text=f"Prochain daily dans ~{fmt_duration(effective_cd)}.")

        await interaction.followup.send(embed=emb)


async def setup(bot: commands.Bot):
    await bot.add_cog(DailyCog(bot))

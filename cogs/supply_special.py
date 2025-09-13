# cogs/supply_special.py
from __future__ import annotations

import asyncio
import datetime as dt
import random
from typing import Dict, Optional, Tuple, Set

import discord
from discord.ext import commands, tasks

from data import storage
from economy_db import add_balance
from stats_db import heal_user, deal_damage
from inventory_db import add_item

# Items droppables (mêmes emojis que le shop). On peut étendre si besoin.
DROPPABLE_ITEMS = ["❄️", "🪓", "🔥", "⚡", "🔫", "🧨", "☠️", "🦠", "🧪", "🧟", "🍀",
                   "🩸", "🩹", "💊", "💕", "📦", "🔍", "💉", "🛡", "👟", "🪖", "⭐️"]
TICKET_EMOJI = "🎟️"
CLAIM_EMOJI = "📦"

# Fenêtres horaires locales (24h)
WINDOWS = [
    (8, 12),   # 08:00 → 12:00
    (13, 16),  # 13:00 → 16:00
    (18, 22),  # 18:00 → 22:00
]

REQUIRED_MESSAGES = 20     # quota de msgs (hors bots) pour autoriser la tranche
MAX_CLAIMERS = 5
MESSAGE_TIMEOUT_SEC = 5 * 60  # le message de drop expire au bout de 5 minutes

def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).astimezone()  # heure locale du serveur

def _current_window(now: dt.datetime) -> Optional[int]:
    hour = now.hour
    for idx, (start, end) in enumerate(WINDOWS):
        if start <= hour < end:
            return idx
    return None

def _window_end_dt(now: dt.datetime, window_idx: int) -> dt.datetime:
    _, end_h = WINDOWS[window_idx]
    end = now.replace(hour=end_h, minute=0, second=0, microsecond=0)
    if end <= now:
        # sécurité
        end += dt.timedelta(days=1)
    return end

class SupplySpecialCog(commands.Cog):
    """
    Ravitaillement SPÉCIAL:
      • Dans les salons textuels avec activité (hors bots), on mémorise le dernier salon actif.
      • À chaque tranche horaire (08-12 / 13-16 / 18-22), si ≥ REQUIRED_MESSAGES depuis le dernier drop:
          - on tente un drop aléatoire DURANT la tranche (proba croissante),
          - sinon on force un drop au cutoff (12h/16h/22h) si aucune tentative n’a abouti.
      • Le message de drop accepte les réactions (📦) pendant 5 min; les 5 premiers obtiennent une récompense:
          - 3–5× même objet ALÉA OU
          - 50–150 GoldValis OU
          - soin +5 à +20 PV OU
          - dégâts +5 à +20 PV OU
          - 1–3 🎟️ tickets
      • Pas de double drop dans la même tranche.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # mémoire runtime
        self._last_active_channel: Dict[int, int] = {}   # guild_id -> channel_id
        self._msg_count_in_window: Dict[int, int] = {}   # guild_id -> compteur msgs (hors bots)
        self._window_drop_done: Dict[int, Tuple[int, int]] = {}  # guild_id -> (year*1000+day_of_year, window_idx)
        self._active_drops: Dict[int, Set[int]] = {}     # message_id -> set(user_ids) déjà récompensés

        self._load_persisted()
        self._ticker.start()

    # ─────────────────────────────────────────────────────────
    # Persistence minimale (dernier drop / par fenêtre)
    # ─────────────────────────────────────────────────────────
    def _load_persisted(self):
        data = storage.load_data()
        by_guild = data.get("by_guild", {})
        for gid, bucket in by_guild.items():
            sd = bucket.get("supply_special", {})
            win_info = sd.get("last_drop_key")  # tuple [key, idx]
            if isinstance(win_info, list) and len(win_info) == 2:
                self._window_drop_done[int(gid)] = (int(win_info[0]), int(win_info[1]))

    def _save_persisted(self, guild_id: int, key_tuple: Tuple[int, int]):
        data = storage.load_data()
        bucket = data.setdefault("by_guild", {}).setdefault(str(guild_id), {})
        st = bucket.setdefault("supply_special", {})
        st["last_drop_key"] = [int(key_tuple[0]), int(key_tuple[1])]
        storage.save_data(data)

    # ─────────────────────────────────────────────────────────
    # Listener activité (messages non-bot)
    # ─────────────────────────────────────────────────────────
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return
        # mémorise dernier salon actif
        self._last_active_channel[message.guild.id] = message.channel.id
        # incrémente compteur messages pour la fenêtre courante
        now = _now()
        w = _current_window(now)
        if w is None:
            # hors fenêtre: reset le compteur pour éviter pollution
            self._msg_count_in_window[message.guild.id] = 0
            return
        self._msg_count_in_window[message.guild.id] = self._msg_count_in_window.get(message.guild.id, 0) + 1

    # ─────────────────────────────────────────────────────────
    # Tâche périodique: tentative de drop
    # ─────────────────────────────────────────────────────────
    @tasks.loop(seconds=60)
    async def _ticker(self):
        now = _now()
        w = _current_window(now)
        for guild in self.bot.guilds:
            gid = guild.id
            # Surveille l’état
            last_key = self._window_drop_done.get(gid)  # (daykey, widx)
            daykey = now.timetuple().tm_yday + now.year * 1000

            # reset compteur si on a changé de fenêtre
            # (clé simple: (daykey, idx))
            have = (daykey, w) if w is not None else None
            if last_key and have and last_key[0] == daykey and last_key[1] == w:
                # déjà droppé dans cette fenêtre → rien
                continue

            # quota de messages atteint ?
            msgs = self._msg_count_in_window.get(gid, 0)
            if msgs < REQUIRED_MESSAGES:
                continue

            # Doit-on forcer au cutoff si pas encore fait ?
            if w is not None:
                cutoff = _window_end_dt(now, w)
                # chance pendant la fenêtre (progressive)
                # plus on approche du cutoff, plus la proba augmente
                secs_total = (cutoff - cutoff.replace(hour=WINDOWS[w][0], minute=0, second=0, microsecond=0)).total_seconds()
                secs_elapsed = (now - cutoff.replace(hour=WINDOWS[w][0], minute=0, second=0, microsecond=0)).total_seconds()
                p = min(0.1 + 0.9 * max(0.0, secs_elapsed / max(1.0, secs_total)), 0.95)  # 10% → 95%
                roll = random.random()
                should_drop = roll < p
                # si on a dépassé la fenêtre (garde-fou), on force
                if now >= cutoff:
                    should_drop = True

                if should_drop:
                    # poste dans le dernier salon actif si dispo
                    channel_id = self._last_active_channel.get(gid)
                    if channel_id:
                        channel = guild.get_channel(channel_id)
                    else:
                        # fallback: premier salon textuel
                        channel = discord.utils.get(guild.text_channels)
                    if channel:
                        await self._post_supply(channel)
                        # marque le drop pour cette fenêtre
                        self._window_drop_done[gid] = (daykey, w)
                        self._save_persisted(gid, (daykey, w))
                        # reset compteur pour éviter redrop
                        self._msg_count_in_window[gid] = 0

    @_ticker.before_loop
    async def _before_ticker(self):
        await self.bot.wait_until_ready()

    # ─────────────────────────────────────────────────────────
    # Affichage + récompenses
    # ─────────────────────────────────────────────────────────
    async def _post_supply(self, channel: discord.abc.Messageable):
        """Poste le message spécial et gère les réactions pendant 5 min."""
        embed = discord.Embed(
            title="📦 GotValis — Ravitaillement Spécial détecté",
            description=f"Les **{MAX_CLAIMERS} premiers** à réagir avec {CLAIM_EMOJI} reçoivent une récompense aléatoire.\n"
                        f"⏳ Disponible pendant **5 minutes**.",
            color=discord.Color.gold()
        )
        msg = await channel.send(embed=embed)
        try:
            await msg.add_reaction(CLAIM_EMOJI)
        except Exception:
            pass

        self._active_drops[msg.id] = set()
        # attends les réactions
        def check(payload: discord.RawReactionActionEvent):
            return (
                payload.message_id == msg.id
                and str(payload.emoji) == CLAIM_EMOJI
                and payload.user_id != self.bot.user.id
            )

        end_ts = dt.datetime.now(dt.timezone.utc).timestamp() + MESSAGE_TIMEOUT_SEC
        try:
            while len(self._active_drops[msg.id]) < MAX_CLAIMERS:
                timeout = max(0.0, end_ts - dt.datetime.now(dt.timezone.utc).timestamp())
                if timeout == 0.0:
                    break
                payload = await self.bot.wait_for("raw_reaction_add", check=check, timeout=timeout)
                # ignore les bots
                guild = self.bot.get_guild(payload.guild_id)
                if not guild:
                    continue
                user = guild.get_member(payload.user_id)
                if not user or user.bot:
                    continue
                if user.id in self._active_drops[msg.id]:
                    continue  # déjà récompensé

                # récompense
                await self._grant_reward(guild.id, user.id)
                self._active_drops[msg.id].add(user.id)

        except asyncio.TimeoutError:
            pass
        finally:
            # petit résumé
            winners = self._active_drops.pop(msg.id, set())
            if winners:
                mentions = ", ".join(f"<@{uid}>" for uid in winners)
                await channel.send(f"✅ Ravitaillement terminé. Récompenses attribuées à: {mentions}")
            else:
                await channel.send("⏳ Ravitaillement expiré sans réclamation.")

    async def _grant_reward(self, guild_id: int, user_id: int):
        """
        5 tables de loot (du + commun au + rare) :
          1) objet x3–5 (même item)
          2) +50..150 GoldValis
          3) soin +5..20
          4) dégâts +5..20
          5) 🎟️ x1..3
        """
        roll = random.random()
        if roll < 0.30:  # 30% objets
            emoji = random.choice(DROPPABLE_ITEMS)
            qty = random.randint(3, 5)
            await add_item(user_id, emoji, qty)
            desc = f"{emoji} × **{qty}**"
        elif roll < 0.60:  # 30% coins
            coins = random.randint(50, 150)
            await add_balance(user_id, coins, reason="supply_special")
            desc = f"💰 **{coins}** GoldValis"
        elif roll < 0.78:  # 18% soin
            heal = random.randint(5, 20)
            healed = await heal_user(user_id, user_id, heal)
            desc = f"💕 **+{healed} PV**"
        elif roll < 0.96:  # 18% dégâts
            dmg = random.randint(5, 20)
            await deal_damage(0, user_id, dmg)  # système = 0
            desc = f"💥 **-{dmg} PV**"
        else:  # 4% tickets
            qty = random.randint(1, 3)
            await add_item(user_id, TICKET_EMOJI, qty)
            desc = f"{TICKET_EMOJI} × **{qty}**"

        # ping discret en MP si possible (silencieux si ça échoue)
        user = self.bot.get_user(user_id)
        if user:
            try:
                await user.send(f"🎁 Ravitaillement spécial → tu reçois: {desc}")
            except Exception:
                pass

async def setup(bot: commands.Bot):
    await bot.add_cog(SupplySpecialCog(bot))

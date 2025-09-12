# cogs/supply_special.py
from __future__ import annotations
import asyncio, random, time, datetime as dt
from typing import Dict, List, Optional

import discord
from discord import app_commands, Interaction, Embed, Colour
from discord.ext import commands

from data.items import OBJETS
from inventory import add_item
from economy_db import add_balance
from gacha_db import add_tickets
from stats_db import init_stats_db, heal_hp, damage_hp, get_hp

# ─────────────────────────────────────────────────────────────────────
# Réglages
# ─────────────────────────────────────────────────────────────────────
DROP_DURATION = 5 * 60           # 5 minutes
MAX_WINNERS = 5
REACTION_EMOJI = "📦"

# du moins rare au plus rare
REWARD_WEIGHTS = {
    "items":   45,   # 3–5 items identiques
    "coins":   30,   # 50–150 GV
    "heal":    12,   # +5–20 PV (si PV manquants, sinon compensation)
    "damage":   8,   # -5–20 PV
    "tickets":  5,   # +1–3 tickets
}

# tranches horaires locales (24h)
WINDOWS = [(8, 12), (13, 16), (18, 22)]

# quota pour armer une tranche
MIN_MSGS_BETWEEN_DROPS = 20

# ─────────────────────────────────────────────────────────────────────
# Utils temps
# ─────────────────────────────────────────────────────────────────────
def _bounds_today(h1: int, h2: int) -> tuple[int, int]:
    now = dt.datetime.now()
    a = now.replace(hour=h1, minute=0, second=0, microsecond=0)
    b = now.replace(hour=h2, minute=0, second=0, microsecond=0)
    return int(a.timestamp()), int(b.timestamp())

def _rand_between(a: int, b: int) -> int:
    # on évite de planifier dans les 5 dernières minutes pour préserver la durée
    safe_b = max(a + 60, b - DROP_DURATION)
    if safe_b <= a:
        safe_b = b
    return random.randint(a, safe_b)

def _rand_between_now_end(now_ts: int, end_ts: int) -> int:
    safe_end = max(now_ts + 60, end_ts - DROP_DURATION)
    if safe_end <= now_ts:
        safe_end = end_ts
    return random.randint(now_ts, safe_end)

def _pick_item(exclude: set[str] | None = None) -> str:
    exclude = exclude or set()
    emojis, weights = [], []
    for e, d in OBJETS.items():
        if e in exclude:
            continue
        r = max(1, int(d.get("rarete", 1)))
        emojis.append(e)
        weights.append(1.0 / r)  # inverse de la "rarete"
    return random.choices(emojis, weights=weights, k=1)[0]

# ─────────────────────────────────────────────────────────────────────
# Cog
# ─────────────────────────────────────────────────────────────────────
class SupplySpecial(commands.Cog):
    """
    Supply spécial par tranches (08–12, 13–16, 18–22) :
    - 1 drop max par tranche.
    - tranche "armée" uniquement si ≥ MIN_MSGS_BETWEEN_DROPS messages non-bot depuis le dernier drop.
    - si quota atteint pendant la tranche → planifie un drop aléatoire entre "maintenant" et la fin.
    - pas de fallback automatique à 12/16/22 si quota non atteint.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._last_active: Dict[int, int] = {}          # guild_id -> last text channel id
        self._state: Dict[int, dict] = {}               # guild_id -> {day, windows:[{start,end,armed,scheduled,sent}]}
        self._active_drop: Dict[int, bool] = {}         # guild_id -> bool
        self._msgs_since_drop: Dict[int, int] = {}      # guild_id -> compteur non-bot depuis dernier drop
        self._loop_task: asyncio.Task | None = None

    async def cog_load(self):
        await init_stats_db()
        self._loop_task = asyncio.create_task(self._scheduler_loop())

    async def cog_unload(self):
        if self._loop_task:
            self._loop_task.cancel()

    # track dernier salon ACTIF + compteur messages (ignore bots)
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return
        if isinstance(message.channel, discord.TextChannel):
            self._last_active[message.guild.id] = message.channel.id
        self._msgs_since_drop[message.guild.id] = self._msgs_since_drop.get(message.guild.id, 0) + 1

    # boucle planif
    async def _scheduler_loop(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            try:
                await self._tick()
            except Exception:
                pass
            await asyncio.sleep(15)

    async def _ensure_day_state(self, guild_id: int):
        today = dt.datetime.now().strftime("%Y-%m-%d")
        gstate = self._state.get(guild_id)
        if not gstate or gstate.get("day") != today:
            windows = []
            for (h1, h2) in WINDOWS:
                a, b = _bounds_today(h1, h2)
                windows.append({
                    "start": a, "end": b,
                    "armed": False,     # tranche autorisée ?
                    "scheduled": None,  # timestamp prévu si armée
                    "sent": False,      # a déjà envoyé un drop ?
                })
            self._state[guild_id] = {"day": today, "windows": windows}
            self._active_drop[guild_id] = False
            # on NE reset PAS _msgs_since_drop ici : c'est depuis le dernier drop, pas par jour

    async def _tick(self):
        now = int(time.time())
        for guild in self.bot.guilds:
            await self._ensure_day_state(guild.id)
            gstate = self._state[guild.id]
            win_list = gstate["windows"]

            for w in win_list:
                if w["sent"]:
                    continue  # déjà un drop cette tranche

                start, end = w["start"], w["end"]
                # 1) avant la tranche → on arme si quota déjà atteint
                if now < start:
                    if not w["armed"] and self._msgs_since_drop.get(guild.id, 0) >= MIN_MSGS_BETWEEN_DROPS:
                        w["armed"] = True
                        w["scheduled"] = _rand_between(start, end)
                    continue

                # 2) pendant la tranche
                if start <= now < end:
                    # a) si pas armée au début → peut s'armer à chaud si quota atteint pendant la tranche
                    if not w["armed"] and self._msgs_since_drop.get(guild.id, 0) >= MIN_MSGS_BETWEEN_DROPS:
                        w["armed"] = True
                        w["scheduled"] = _rand_between_now_end(now, end)

                    # b) si armée et horaire atteint → tente de drop
                    if w["armed"] and w["scheduled"] is not None and now >= w["scheduled"]:
                        launched = await self._try_spawn_in_last_active(guild)
                        if launched:
                            w["sent"] = True
                            # reset du quota puisqu’on vient de faire un drop
                            self._msgs_since_drop[guild.id] = 0
                        else:
                            # si on n'a pas pu lancer (ex: pas de salon/perm), on peut retenter plus tard
                            # on reprogramme un nouvel horaire dans le reste de la tranche
                            w["scheduled"] = _rand_between_now_end(now, end)
                    continue

                # 3) après la tranche → si rien n'a été envoyé, on ne fait rien (pas de fallback)
                if now >= end:
                    # tranche manquée, on la marque comme "sent" pour ne pas la retravailler
                    w["sent"] = True
                    continue

    async def _choose_channel(self, guild: discord.Guild) -> Optional[discord.TextChannel]:
        ch_id = self._last_active.get(guild.id)
        ch = guild.get_channel(ch_id) if ch_id else None
        if not isinstance(ch, discord.TextChannel):
            return None
        me = guild.me
        if not me:
            return None
        perms = ch.permissions_for(me)
        if not (perms.view_channel and perms.read_message_history and perms.send_messages and perms.add_reactions):
            return None
        return ch

    async def _try_spawn_in_last_active(self, guild: discord.Guild) -> bool:
        # pas 2 drops en même temps
        if self._active_drop.get(guild.id):
            return False
        ch = await self._choose_channel(guild)
        if not ch:
            return False

        self._active_drop[guild.id] = True
        try:
            await self._spawn_supply(ch)
            return True
        finally:
            self._active_drop[guild.id] = False

    # déroulé d’un drop
    async def _spawn_supply(self, channel: discord.TextChannel):
        header = Embed(
            title="📦 Ravitaillement spécial GotValis",
            description=(
                f"Réagissez avec {REACTION_EMOJI} pour récupérer une récompense surprise !\n"
                f"⏳ Disponible pendant **5 minutes**, maximum **{MAX_WINNERS}** personnes."
            ),
            colour=Colour.orange()
        )
        msg = await channel.send(embed=header)
        try:
            await msg.add_reaction(REACTION_EMOJI)
        except Exception:
            pass

        winners: List[int] = []
        end_ts = time.time() + DROP_DURATION

        def valid(evt: discord.RawReactionActionEvent) -> bool:
            if evt.message_id != msg.id:
                return False
            if str(evt.emoji) != REACTION_EMOJI:
                return False
            if evt.user_id == self.bot.user.id:
                return False
            if evt.user_id in winners:
                return False
            return True

        while time.time() < end_ts and len(winners) < MAX_WINNERS:
            try:
                evt: discord.RawReactionActionEvent = await self.bot.wait_for(
                    "raw_reaction_add", timeout=max(0.1, end_ts - time.time())
                )
            except asyncio.TimeoutError:
                break
            if valid(evt):
                winners.append(evt.user_id)

        rec_lines: List[str] = []
        for uid in winners:
            rec_lines.append(await self._grant_reward_line(uid))

        recap = Embed(
            title="📦 Récapitulatif du ravitaillement",
            description=("\n".join(rec_lines) if rec_lines else "*Aucun gagnant.*"),
            colour=Colour.green() if rec_lines else Colour.red()
        )
        await channel.send(embed=recap)

    async def _grant_reward_line(self, user_id: int) -> str:
        cats = list(REWARD_WEIGHTS.keys())
        weights = list(REWARD_WEIGHTS.values())
        cat = random.choices(cats, weights=weights, k=1)[0]

        if cat == "items":
            qty = random.randint(3, 5)
            e = _pick_item()
            await add_item(user_id, e, qty)
            return f"🎁 <@{user_id}> a obtenu {e} × **{qty}**."

        if cat == "coins":
            gv = random.randint(50, 150)
            await add_balance(user_id, gv, "supply_special")
            return f"💰 <@{user_id}> reçoit **{gv}** GoldValis."

        if cat == "heal":
            amount = random.randint(5, 20)
            gained = await heal_hp(user_id, amount)
            if gained <= 0:
                gv = random.randint(50, 150)
                await add_balance(user_id, gv, "supply_special_heal_fallback")
                return f"❤️ <@{user_id}> avait déjà tous ses PV → **+{gv}** GoldValis."
            hp, mx = await get_hp(user_id)
            return f"❤️ <@{user_id}> soigne **{gained} PV** (→ {hp}/{mx})."

        if cat == "damage":
            amount = random.randint(5, 20)
            lost = await damage_hp(user_id, amount)
            hp, mx = await get_hp(user_id)
            return f"💥 <@{user_id}> subit **{lost} PV** (→ {hp}/{mx})."

        t = random.randint(1, 3)
        await add_tickets(user_id, t)
        return f"🎟️ <@{user_id}> gagne **{t}** ticket(s)."

    # staff (respecte toujours la non-concurrence, mais ignore le quota volontairement)
    @app_commands.command(name="force_special_supply", description="Lance un ravitaillement spécial maintenant (dernier salon actif).")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def force_special_supply(self, itx: Interaction):
        await itx.response.defer(ephemeral=True)
        if self._active_drop.get(itx.guild.id):
            return await itx.followup.send("⚠️ Un supply spécial est déjà en cours.", ephemeral=True)
        ch_id = self._last_active.get(itx.guild.id) if itx.guild else None
        ch = itx.guild.get_channel(ch_id) if ch_id else None
        if not isinstance(ch, discord.TextChannel):
            return await itx.followup.send("❌ Aucun salon texte actif trouvé.", ephemeral=True)

        self._active_drop[itx.guild.id] = True
        try:
            await self._spawn_supply(ch)
            # on considère que c'est un vrai drop → reset du quota
            self._msgs_since_drop[itx.guild.id] = 0
        finally:
            self._active_drop[itx.guild.id] = False
        await itx.followup.send(f"✅ Supply spécial lancé dans {ch.mention}.", ephemeral=True)

    @force_special_supply.error
    async def _perm_err(self, itx: Interaction, error: Exception):
        if isinstance(error, app_commands.errors.MissingPermissions):
            return await itx.response.send_message("❌ Permission manquante: Gérer le serveur.", ephemeral=True)
        try:
            await itx.response.send_message("❌ Erreur lors du lancement.", ephemeral=True)
        except discord.InteractionResponded:
            await itx.followup.send("❌ Erreur lors du lancement.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(SupplySpecial(bot))

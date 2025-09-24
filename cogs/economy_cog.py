# cogs/economie.py
from __future__ import annotations
import asyncio
import random
import time
from typing import Dict, Optional, List, Tuple

import aiosqlite
import discord
from discord import app_commands, Interaction, Embed, Colour
from discord.ext import commands

from economy_db import init_economy_db, get_balance, add_balance
from passifs import trigger  # ← bonus passifs "on_gain_coins"

DB_PATH = "gotvalis.sqlite3"

# ─────────────────────────────────────────────────────────────
# Réglages généraux
# ─────────────────────────────────────────────────────────────
ECON_MULTIPLIER = 0.5  # ÷2 pour messages et vocal

# Messages
MSG_MIN_LEN = 6            # longueur minimale pour compter
MSG_COOLDOWN = 5           # secondes anti-spam par utilisateur
MSG_REWARD_MIN = 1         # base 1..10, puis × ECON_MULTIPLIER
MSG_REWARD_MAX = 10
MSG_STREAK_MIN = 2         # toutes les 2..5 contributions valides
MSG_STREAK_MAX = 5

# Vocal
VC_TICK_SECONDS = 60       # boucle interne (1 min)
VC_AWARD_INTERVAL = 30*60  # 30 minutes
VC_REWARD_MIN = 2          # base 2..20, puis × ECON_MULTIPLIER
VC_REWARD_MAX = 20
VC_MIN_ACTIVE = 2          # ⬅️ nb min de membres ACTIFS requis dans le salon

# Leaderboard
TOP_LIMIT = 10


class Economie(commands.Cog):
    """Économie : gains par messages & vocal, /wallet, /give, /top, /earnings."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Messages : suivi par user (global)
        self._last_msg_ts: Dict[int, float] = {}           # user_id -> last ts
        self._msg_counts: Dict[int, int] = {}              # user_id -> compteur valid msgs
        self._msg_threshold: Dict[int, int] = {}           # user_id -> palier 2..5

        # Vocal : suivi temps cumulé depuis dernier award
        self._vc_accum: Dict[int, int] = {}                # user_id -> secondes accumulées
        self._vc_task: Optional[asyncio.Task] = None

    # ─────────────────────────────────────────────────────────
    # Lifecycle
    # ─────────────────────────────────────────────────────────
    async def cog_load(self):
        await init_economy_db()
        self._vc_task = asyncio.create_task(self._voice_loop())

    async def cog_unload(self):
        if self._vc_task:
            self._vc_task.cancel()

    # ─────────────────────────────────────────────────────────
    # Helpers internes
    # ─────────────────────────────────────────────────────────
    async def _apply_passif_gain(self, user_id: int, amount: int) -> int:
        """Applique les bonus de passif pour un gain positif (on_gain_coins)."""
        if amount <= 0:
            return amount
        try:
            res = await trigger("on_gain_coins", user_id=user_id, delta=amount)
            extra = int((res or {}).get("extra", 0))
            return amount + extra
        except Exception:
            return amount

    async def _maybe_update_lb(self, guild_id: Optional[int], reason: str):
        if not guild_id:
            return
        try:
            from cogs.leaderboard_live import schedule_lb_update
            schedule_lb_update(self.bot, int(guild_id), reason)
        except Exception:
            pass

    # ─────────────────────────────────────────────────────────
    # Messages → gains
    # ─────────────────────────────────────────────────────────
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # ignore DM, bots, systèmes
        if not message.guild or message.author.bot:
            return
        if not isinstance(message.channel, discord.TextChannel):
            return

        user_id = message.author.id
        gid = message.guild.id

        # anti-spam : cooldown et longueur minimale
        now = time.time()
        last = self._last_msg_ts.get(user_id, 0.0)
        if now - last < MSG_COOLDOWN:
            return
        if len((message.content or "").strip()) < MSG_MIN_LEN:
            return

        # ok, contribution valide
        self._last_msg_ts[user_id] = now

        # incrémente le compteur du user
        n = self._msg_counts.get(user_id, 0) + 1
        self._msg_counts[user_id] = n
        thr = self._msg_threshold.get(user_id)
        if thr is None:
            thr = random.randint(MSG_STREAK_MIN, MSG_STREAK_MAX)
            self._msg_threshold[user_id] = thr

        # si atteint le palier → récompense
        if n >= thr:
            base = random.randint(MSG_REWARD_MIN, MSG_REWARD_MAX)
            reward = max(1, int(base * ECON_MULTIPLIER))
            reward = await self._apply_passif_gain(user_id, reward)  # passifs (Silien/Alphonse…)
            await add_balance(user_id, reward, "msg_reward")
            await self._maybe_update_lb(gid, "msg_reward")
            # reset le compteur et nouveau palier
            self._msg_counts[user_id] = 0
            self._msg_threshold[user_id] = random.randint(MSG_STREAK_MIN, MSG_STREAK_MAX)

    # ─────────────────────────────────────────────────────────
    # Vocal → gains (toutes les 30min d'activité)
    # ─────────────────────────────────────────────────────────
    async def _voice_loop(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            try:
                await self._voice_tick()
            except Exception:
                pass
            await asyncio.sleep(VC_TICK_SECONDS)

    async def _voice_tick(self):
        # Parcourt tous les salons vocaux de toutes les guilds
        for guild in self.bot.guilds:
            if not guild.members:
                continue

            afk_channel_id = guild.afk_channel.id if guild.afk_channel else None

            # 1) Regrouper les membres par canal vocal
            channels: Dict[int, List[discord.Member]] = {}
            for m in guild.members:
                vs = m.voice
                if not vs or not vs.channel:
                    continue
                channels.setdefault(vs.channel.id, []).append(m)

            # 2) Pour chaque canal, filtrer les "actifs"
            for cid, members in channels.items():
                active: List[discord.Member] = []
                for member in members:
                    vs = member.voice
                    if not vs or not vs.channel:
                        continue
                    # AFK → inactif
                    if afk_channel_id and vs.channel.id == afk_channel_id:
                        continue
                    # Bots → ignorés
                    if member.bot:
                        continue
                    # Stage audience (auditeur) → inactif
                    if isinstance(vs.channel, discord.StageChannel) and vs.suppress:
                        continue
                    # Sourd (self ou serveur) → inactif
                    if vs.self_deaf or vs.deaf:
                        continue
                    # Muet utilisateur → inactif
                    if vs.self_mute:
                        continue
                    # Actif
                    active.append(member)

                # 3) Salon "inactif" si moins de VC_MIN_ACTIVE actifs
                if len(active) < VC_MIN_ACTIVE:
                    # (Optionnel) purger l'accumulation pour éviter d'empiler dans un salon inactif
                    # for m in active:
                    #     self._vc_accum[m.id] = 0
                    continue

                # 4) Créditer uniquement les membres ACTIFS dans un salon ACTIF
                for member in active:
                    uid = member.id
                    self._vc_accum[uid] = self._vc_accum.get(uid, 0) + VC_TICK_SECONDS

                    while self._vc_accum[uid] >= VC_AWARD_INTERVAL:
                        self._vc_accum[uid] -= VC_AWARD_INTERVAL
                        base = random.randint(VC_REWARD_MIN, VC_REWARD_MAX)
                        reward = max(1, int(base * ECON_MULTIPLIER))
                        reward = await self._apply_passif_gain(uid, reward)
                        await add_balance(uid, reward, "voice_reward")
                        await self._maybe_update_lb(guild.id, "voice_reward")

    # ─────────────────────────────────────────────────────────
    # Slash commands
    # ─────────────────────────────────────────────────────────
    @app_commands.command(name="wallet", description="Affiche ton solde de GoldValis.")
    async def wallet(self, itx: Interaction, user: Optional[discord.User] = None):
        target = user or itx.user
        bal = await get_balance(target.id)
        emb = Embed(
            title="💰 Portefeuille",
            description=f"{target.mention} possède **{bal}** GoldValis.",
            colour=Colour.gold()
        )
        await itx.response.send_message(embed=emb, ephemeral=(target.id == itx.user.id))

    @app_commands.command(name="give", description="Donne des GoldValis à quelqu'un.")
    @app_commands.describe(user="Destinataire", amount="Montant à transférer (≥1)")
    async def give(self, itx: Interaction, user: discord.User, amount: int):
        if amount <= 0:
            return await itx.response.send_message("❌ Le montant doit être ≥ 1.", ephemeral=True)
        if user.id == itx.user.id:
            return await itx.response.send_message("❌ Tu ne peux pas te donner à toi-même.", ephemeral=True)

        sender_bal = await get_balance(itx.user.id)
        if sender_bal < amount:
            return await itx.response.send_message(
                f"❌ Solde insuffisant. Tu as **{sender_bal}** GV.", ephemeral=True
            )

        # Transfert : on n'applique PAS les passifs sur /give (évite l'abus).
        await add_balance(itx.user.id, -amount, "give_transfer_out")
        await add_balance(user.id, amount, "give_transfer_in")

        # Rafraîchir le LB pour la guilde courante
        gid = itx.guild.id if itx.guild else None
        await self._maybe_update_lb(gid, "give")

        emb = Embed(
            title="🤝 Transfert réussi",
            description=f"{itx.user.mention} a donné **{amount}** GoldValis à {user.mention}.",
            colour=Colour.green()
        )
        await itx.response.send_message(embed=emb)

    @app_commands.command(name="top", description="Classement des plus riches (serveur entier).")
    async def top(self, itx: Interaction, limit: Optional[int] = TOP_LIMIT):
        limit = max(1, min(25, limit or TOP_LIMIT))
        rows = await self._fetch_top(limit)
        if not rows:
            return await itx.response.send_message("Aucun portefeuille trouvé.", ephemeral=True)

        lines = []
        for i, (uid, bal) in enumerate(rows, start=1):
            member = itx.guild.get_member(int(uid)) if itx.guild else None
            name = member.mention if member else f"<@{uid}>"
            lines.append(f"**{i}.** {name} — **{bal}** GV")

        emb = Embed(title=f"🏆 Top {len(rows)} — GoldValis", colour=Colour.blurple(), description="\n".join(lines))
        await itx.response.send_message(embed=emb)

    @app_commands.command(name="earnings", description="Affiche tes 10 dernières entrées de journal économique.")
    async def earnings(self, itx: Interaction, user: Optional[discord.User] = None):
        target = user or itx.user
        logs = await self._fetch_logs(target.id, limit=10)
        if not logs:
            return await itx.response.send_message("Aucune entrée de journal.", ephemeral=True)

        lines = []
        for ts, delta, reason in logs:
            sign = "＋" if delta >= 0 else "－"
            lines.append(f"`{time.strftime('%Y-%m-%d %H:%M', time.localtime(ts))}` {sign}{abs(delta)} — {reason}")

        emb = Embed(
            title=f"📒 Journal — {target.display_name}",
            description="\n".join(lines),
            colour=Colour.dark_teal()
        )
        await itx.response.send_message(embed=emb, ephemeral=(target.id == itx.user.id))

    # ─────────────────────────────────────────────────────────
    # Helpers DB (lecture leaderboard & logs)
    # ─────────────────────────────────────────────────────────
    async def _fetch_top(self, limit: int) -> List[Tuple[str, int]]:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT user_id, balance FROM wallets ORDER BY balance DESC LIMIT ?",
                (limit,)
            ) as cur:
                rows = await cur.fetchall()
        return [(r[0], r[1]) for r in rows]

    async def _fetch_logs(self, user_id: int, limit: int = 10) -> List[Tuple[int, int, str]]:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT ts, delta, reason FROM wallet_logs WHERE user_id = ? ORDER BY ts DESC LIMIT ?",
                (str(user_id), limit)
            ) as cur:
                rows = await cur.fetchall()
        return [(r[0], r[1], r[2]) for r in rows]


async def setup(bot: commands.Bot):
    await bot.add_cog(Economie(bot))

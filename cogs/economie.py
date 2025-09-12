# cogs/economie.py
import asyncio, random, time, math
from typing import Dict
import discord
from discord import app_commands, Interaction, Embed, Colour
from discord.ext import commands

from economy_db import (
    init_economy_db, get_balance, add_balance, transfer,
    get_recent_earnings, get_top_balances,
    get_next_voice_payout, set_next_voice_payout,
    get_last_msg_count_ts, set_last_msg_count_ts,
    VOICE_INTERVAL
)

# -------- Réglages gains (divisés par 2) --------
ECON_MULTIPLIER = 0.5  # applique /2 aux gains passifs

VOICE_MIN = 2
VOICE_MAX = 20

MSG_TARGET_MIN = 2
MSG_TARGET_MAX = 5
MSG_MIN_LEN = 8
MSG_COOLDOWN = 5  # s

def compute_msg_reward(length: int) -> int:
    if length < 25:
        base = random.randint(1, 3)
    elif length < 80:
        base = random.randint(4, 7)
    else:
        base = random.randint(8, 10)
    return max(1, math.ceil(base * ECON_MULTIPLIER))

class _MsgState:
    __slots__ = ("count", "target", "last_contrib_ts")
    def __init__(self):
        self.count = 0
        self.target = random.randint(MSG_TARGET_MIN, MSG_TARGET_MAX)
        self.last_contrib_ts = 0.0

class Economie(commands.Cog):
    """Économie: gains messages & vocal, wallet/top/logs/give (sans shop)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.msg_states: Dict[tuple[int,int], _MsgState] = {}
        self._voice_task: asyncio.Task | None = None

    async def cog_load(self):
        await init_economy_db()
        self._voice_task = asyncio.create_task(self._voice_loop())

    async def cog_unload(self):
        if self._voice_task:
            self._voice_task.cancel()

    # -------- boucle vocal (scan / min) --------
    async def _voice_loop(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            now = int(time.time())
            try:
                for guild in self.bot.guilds:
                    for vc in guild.voice_channels:
                        for member in vc.members:
                            if member.bot:
                                continue
                            next_ts = await get_next_voice_payout(member.id)
                            if not next_ts or now >= next_ts:
                                raw = random.randint(VOICE_MIN, VOICE_MAX)
                                amount = max(1, math.floor(raw * ECON_MULTIPLIER))
                                await add_balance(member.id, amount, "voice_interval")
                                await set_next_voice_payout(member.id, now + VOICE_INTERVAL)
            except Exception:
                pass
            await asyncio.sleep(60)

    # -------- listener messages --------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return
        if not isinstance(message.channel, discord.abc.Messageable):
            return

        content = (message.content or "").strip()
        if content.startswith("/"):
            return
        if len(content) < MSG_MIN_LEN and not message.attachments:
            return

        now = int(time.time())
        last_global = await get_last_msg_count_ts(message.author.id)
        if last_global and (now - last_global) < MSG_COOLDOWN:
            return
        await set_last_msg_count_ts(message.author.id, now)

        key = (message.channel.id, message.author.id)
        st = self.msg_states.get(key) or _MsgState()
        self.msg_states[key] = st

        if time.time() - st.last_contrib_ts < MSG_COOLDOWN:
            return
        st.last_contrib_ts = time.time()

        st.count += 1
        if st.count >= st.target:
            amount = compute_msg_reward(len(content))
            await add_balance(message.author.id, amount, "message_chunk")
            st.count = 0
            st.target = random.randint(MSG_TARGET_MIN, MSG_TARGET_MAX)

    # -------- commandes wallet --------
    @app_commands.command(name="wallet", description="Affiche ton solde.")
    async def wallet(self, itx: Interaction, user: discord.User | None = None):
        target = user or itx.user
        bal = await get_balance(target.id)
        await itx.response.send_message(
            f"💳 Solde de {target.mention} : **{bal}** GoldValis.",
            ephemeral=(target.id == itx.user.id)
        )

    @app_commands.command(name="give", description="Envoyer des GoldValis à quelqu'un.")
    async def give(self, itx: Interaction, member: discord.User, amount: app_commands.Range[int,1]):
        if member.id == itx.user.id:
            return await itx.response.send_message("🙃 Tu ne peux pas t'envoyer des GoldValis à toi-même.", ephemeral=True)
        ok, err = await transfer(itx.user.id, member.id, amount)
        if not ok:
            return await itx.response.send_message(f"❌ {err}", ephemeral=True)
        await itx.response.send_message(f"🤝 {itx.user.mention} → {member.mention} : **{amount}** GoldValis envoyés !")

    @app_commands.command(name="top", description="Top des plus riches.")
    async def top(self, itx: Interaction):
        rows = await get_top_balances(10)
        if not rows:
            return await itx.response.send_message("Personne n’a encore de GoldValis.", ephemeral=True)
        desc = [f"**#{i}** <@{uid}> — **{bal}**" for i,(uid,bal) in enumerate(rows,1)]
        emb = Embed(title="🏆 Top Richesse — GoldValis", description="\n".join(desc), colour=Colour.gold())
        await itx.response.send_message(embed=emb)

    @app_commands.command(name="earnings", description="Tes derniers gains/pertes (journal).")
    async def earnings(self, itx: Interaction):
        rows = await get_recent_earnings(itx.user.id, 12)
        if not rows:
            return await itx.response.send_message("Aucun log pour le moment.", ephemeral=True)
        lines = []
        for ts, reason, amount in rows:
            sign = "🟢" if amount >= 0 else "🔴"
            lines.append(f"{sign} {amount:+} — `{reason}` <t:{ts}:R>")
        await itx.response.send_message("\n".join(lines), ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Economie(bot))

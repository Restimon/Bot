# cogs/leaderboard_live.py
from __future__ import annotations

import asyncio
from typing import Dict, List, Tuple, Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks
import aiosqlite

# ─────────────────────────────────────────────────────────
# DB partagée (même fichier SQLite que le reste)
# ─────────────────────────────────────────────────────────
try:
    from economy_db import DB_PATH, get_balance
except Exception:
    DB_PATH = "gotvalis.sqlite3"
    async def get_balance(user_id: int) -> int:  # fallback
        return 0

# PV / PB (stats_db)
try:
    from stats_db import get_hp as stats_get_hp, get_shield as stats_get_shield
except Exception:
    async def stats_get_hp(user_id: int) -> Tuple[int, int]:  # (hp, max_hp)
        return 100, 100
    async def stats_get_shield(user_id: int) -> int:
        return 0

# Salon mémorisé côté storage JSON (lecture seule ici)
try:
    from data.storage import get_leaderboard_channel
except Exception:
    def get_leaderboard_channel(guild_id: int) -> Optional[int]:
        return None

# ─────────────────────────────────────────────────────────
# Persistance du message unique (canal + message id)
# ─────────────────────────────────────────────────────────
CREATE_SQL = """
CREATE TABLE IF NOT EXISTS leaderboard_pins (
    guild_id   TEXT PRIMARY KEY,
    channel_id INTEGER NOT NULL,
    message_id INTEGER NOT NULL
);
"""

async def _init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(CREATE_SQL)
        await db.commit()

async def _get_pin(guild_id: int) -> Optional[Tuple[int, int]]:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT channel_id, message_id FROM leaderboard_pins WHERE guild_id=?",
            (str(guild_id),),
        )
        row = await cur.fetchone()
        await cur.close()
    return (int(row[0]), int(row[1])) if row else None

async def _set_pin(guild_id: int, channel_id: int, message_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO leaderboard_pins(guild_id, channel_id, message_id) VALUES(?,?,?) "
            "ON CONFLICT(guild_id) DO UPDATE SET channel_id=excluded.channel_id, message_id=excluded.message_id",
            (str(guild_id), int(channel_id), int(message_id)),
        )
        await db.commit()

# ─────────────────────────────────────────────────────────
# Scheduler debouncé pour MAJ
# ─────────────────────────────────────────────────────────
_pending_updates: Dict[int, str] = {}   # guild_id -> reason
_update_lock = asyncio.Lock()

def schedule_lb_update(bot: commands.Bot, guild_id: int, reason: str = "auto") -> None:
    """À appeler dès qu'une action peut changer Coins/PV/PB."""
    _pending_updates[guild_id] = reason  # dernière raison gagne

async def trigger_lb_update_now(bot: commands.Bot, guild_id: int, reason: str = "manual") -> None:
    """MAJ immédiate (awaitable), utilisée par l'admin (/lb_set, /lb_refresh) situé dans admin_cog.py."""
    cog: Optional[LiveLeaderboard] = bot.get_cog("LiveLeaderboard")  # type: ignore
    if cog:
        await cog._render_guild(guild_id, reason)

# ─────────────────────────────────────────────────────────
# Rendu (Coins + PV + PB)
# ─────────────────────────────────────────────────────────
def _rank_emoji(n: int) -> str:
    if n == 1:
        return "🥇"
    if n == 2:
        return "🥈"
    if n == 3:
        return "🥉"
    # Échapper le point pour éviter que Discord transforme "4. " en liste numérotée
    return f"{n}\\."

def _format_line(idx: int, name: str, coins: int, hp: int, pb: int) -> str:
    medal = _rank_emoji(idx)
    pb_part = f" | 🛡 **{pb}** PB" if pb > 0 else ""
    return f"**{medal} {name}** → 💰 **{coins}** GotCoins | ❤️ **{hp}** PV{pb_part}"

async def _collect_rows(guild: discord.Guild) -> List[Tuple[int, str, int, int, int]]:
    """
    Construit la liste des joueurs actifs et la trie :
      rows = [(user_id, display_name, coins, hp, pb)]
    Tri: coins DESC, pb DESC, hp DESC, name ASC
    Règle "actif" : montrer le joueur s'il a coins>0 OU a perdu des PV (hp<max) OU a du PB>0.
    """
    members = [m for m in guild.members if not m.bot]

    # appels parallèles
    coins_list = await asyncio.gather(*(get_balance(m.id) for m in members))
    hp_list = await asyncio.gather(*(stats_get_hp(m.id) for m in members))          # (hp, max_hp)
    pb_list = await asyncio.gather(*(stats_get_shield(m.id) for m in members))

    rows: List[Tuple[int, str, int, int, int]] = []
    for m, coins, (hp, mx), pb in zip(members, coins_list, hp_list, pb_list):
        coins = int(coins); hp = int(hp); mx = int(mx); pb = int(pb)
        # garder seulement les "actifs"
        if not (coins > 0 or hp < mx or pb > 0):
            continue
        rows.append((m.id, m.display_name, coins, hp, pb))

    rows.sort(key=lambda t: (-t[2], -t[4], -t[3], t[1].lower()))
    return rows[:10]

def _build_embed(guild: discord.Guild, rows: List[Tuple[int, str, int, int, int]], reason: str) -> discord.Embed:
    e = discord.Embed(
        title="🏆 CLASSEMENT GOTVALIS — ÉDITION SPÉCIALE 🏆",
        color=discord.Color.gold(),
    )
    if rows:
        e.description = "\n".join(
            _format_line(i, name, coins, hp, pb)
            for i, (_uid, name, coins, hp, pb) in enumerate(rows, start=1)
        )
    else:
        e.description = "_Aucun joueur classé pour le moment._"
    e.set_footer(text="💡 Les GotCoins représentent votre richesse accumulée.")
    # (pas de e.set_author — on ne veut pas “maj: …” en tête)
    return e

# ─────────────────────────────────────────────────────────
# Le Cog (sans commandes slash ; elles sont dans admin_cog)
# ─────────────────────────────────────────────────────────
class LiveLeaderboard(commands.Cog):
    """Classement persistant (Top 10 Coins + PV/PB), message unique édité, auto-MAJ et persistant après reboot."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._runner.start()
        self._last_signature: Dict[int, List[Tuple[int, int, int]]] = {}  # gid -> [(uid, coins, pb)]

    # Listeners : “à chaque action” on programme une MAJ (debouncée)
    @commands.Cog.listener()
    async def on_app_command_completion(self, interaction: discord.Interaction, command: app_commands.Command):
        if interaction.guild:
            schedule_lb_update(self.bot, interaction.guild.id, f"/{command.name}")

    @commands.Cog.listener()
    async def on_command_completion(self, ctx: commands.Context):
        if ctx.guild:
            try:
                name = ctx.command.qualified_name if ctx.command else ""
            except Exception:
                name = ""
            schedule_lb_update(self.bot, ctx.guild.id, f"!{name}")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.guild and not message.author.bot:
            schedule_lb_update(self.bot, message.guild.id, "message")

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if member.guild:
            schedule_lb_update(self.bot, member.guild.id, "voice")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        schedule_lb_update(self.bot, member.guild.id, "member_join")

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        schedule_lb_update(self.bot, member.guild.id, "member_remove")

    # Boucle périodique : applique les MAJ en attente (et rattrape si un event a été manqué)
    @tasks.loop(seconds=5.0)
    async def _runner(self):
        if not _pending_updates:
            return
        async with _update_lock:
            items = list(_pending_updates.items())
            _pending_updates.clear()
        for gid, reason in items:
            try:
                await self._render_guild(gid, reason)
            except Exception:
                pass

    @_runner.before_loop
    async def _before_runner(self):
        await self.bot.wait_until_ready()
        await _init_db()
        # Au démarrage : si un salon est mémorisé, planifie un rendu pour chaque guilde
        for g in self.bot.guilds:
            if get_leaderboard_channel(g.id):
                schedule_lb_update(self.bot, g.id, "startup")

    # ─────────────────────────────────────────────────────
    # Rendu + création/édition persistante (message unique)
    # ─────────────────────────────────────────────────────
    async def _render_guild(self, guild_id: int, reason: str) -> None:
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return

        chan_id = get_leaderboard_channel(guild_id)
        if not chan_id:
            return

        channel = guild.get_channel(chan_id)
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            return

        rows = await _collect_rows(guild)

        # signature: (uid, coins, pb) du top10 → pour éviter d'éditer inutilement
        sig = [(uid, coins, pb) for uid, _name, coins, _hp, pb in rows]
        last = self._last_signature.get(guild_id)
        if sig == last and reason != "set_channel":
            return
        self._last_signature[guild_id] = sig

        embed = _build_embed(guild, rows, reason)

        pin = await _get_pin(guild_id)
        msg: Optional[discord.Message] = None
        if pin:
            saved_chan_id, msg_id = pin
            try:
                msg_channel = guild.get_channel(saved_chan_id)
                if isinstance(msg_channel, (discord.TextChannel, discord.Thread)):
                    msg = await msg_channel.fetch_message(msg_id)
                    if saved_chan_id != chan_id:
                        msg = None  # on va republier dans le nouveau salon
            except Exception:
                msg = None

        if msg is None:
            # create + pin
            new_msg = await channel.send(embed=embed)
            try:
                await new_msg.pin()
            except Exception:
                pass
            await _set_pin(guild_id, chan_id, new_msg.id)
        else:
            await msg.edit(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(LiveLeaderboard(bot))

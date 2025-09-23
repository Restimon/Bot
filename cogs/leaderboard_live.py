# cogs/leaderboard_live.py
from __future__ import annotations

import asyncio
from typing import Dict, List, Optional, Tuple

import discord
from discord import app_commands
from discord.ext import commands, tasks

# ─────────────────────────────────────────────────────────
# Storage JSON (optionnel) pour persister canal/message/flags
# ─────────────────────────────────────────────────────────
_storage = None
_save_data = None
_get_user_data = None

try:
    from data import storage as _storage  # type: ignore
except Exception:
    _storage = None

try:
    from data.storage import save_data as _save_data  # type: ignore
except Exception:
    _save_data = None

try:
    # get_user_data(gid, uid) -> (inventory: list[str], coins: int, perso: dict|None)
    from data.storage import get_user_data as _get_user_data  # type: ignore
except Exception:
    _get_user_data = None


# ─────────────────────────────────────────────────────────
# Petits helpers pour lire Coins / PV / PB de manière souple
# ─────────────────────────────────────────────────────────
def _read_coins(gid: int, uid: int) -> int:
    if callable(_get_user_data):
        try:
            _, coins, _ = _get_user_data(str(gid), str(uid))  # type: ignore
            return int(coins or 0)
        except Exception:
            pass
    return 0

def _read_hp_pb(gid: int, uid: int) -> Tuple[int, int]:
    """
    Essaie de lire PV/PB si tu as une DB d'effets; sinon fallback 100/0.
    Tu peux brancher effects_db ici si tu as la fonction.
    """
    # Exemple d’intégration (à activer si dispo) :
    # try:
    #     from effects_db import get_current_hp_pb  # type: ignore
    #     hp, pb = get_current_hp_pb(gid, uid)
    #     return int(hp or 0), int(pb or 0)
    # except Exception:
    #     pass
    return 100, 0


# ─────────────────────────────────────────────────────────
# Persistance (canal & message & options)
# ─────────────────────────────────────────────────────────
def _get_cfg_for_guild(gid: int) -> Dict[str, int]:
    """
    Retourne {channel_id, message_id, auto_all} pour CE serveur.
    Persisté dans storage.leaderboard_live si dispo; sinon RAM.
    """
    key = "leaderboard_live"
    if _storage is not None:
        if not hasattr(_storage, key) or not isinstance(getattr(_storage, key), dict):
            setattr(_storage, key, {})
        all_cfg = getattr(_storage, key)
        all_cfg.setdefault(str(gid), {})
        gcfg = all_cfg[str(gid)]
        gcfg.setdefault("channel_id", 0)
        gcfg.setdefault("message_id", 0)
        gcfg.setdefault("auto_all", 1)  # 1 = ON par défaut
        return gcfg

    # fallback RAM
    if not hasattr(_get_cfg_for_guild, "_mem"):
        _get_cfg_for_guild._mem: Dict[str, Dict[str, int]] = {}
    mem = _get_cfg_for_guild._mem  # type: ignore
    mem.setdefault(str(gid), {"channel_id": 0, "message_id": 0, "auto_all": 1})
    return mem[str(gid)]

def _save_cfg():
    if callable(_save_data):
        try:
            _save_data()  # type: ignore
        except Exception:
            pass

def _auto_all_enabled(gid: int) -> bool:
    cfg = _get_cfg_for_guild(gid)
    try:
        return bool(int(cfg.get("auto_all", 1)))
    except Exception:
        return True


# ─────────────────────────────────────────────────────────
# Rendu du classement
# ─────────────────────────────────────────────────────────
def _rank_rows(guild: discord.Guild) -> List[Tuple[int, str, int, int, int]]:
    """
    Retourne une liste triée de tuples:
    (user_id, display_name, coins, hp, pb)
    Tri: coins DESC, pb DESC, hp DESC, name ASC
    """
    rows: List[Tuple[int, str, int, int, int]] = []
    for m in guild.members:
        if m.bot:
            continue
        coins = _read_coins(guild.id, m.id)
        hp, pb = _read_hp_pb(guild.id, m.id)
        if coins <= 0 and hp <= 0 and pb <= 0:
            continue
        rows.append((m.id, m.display_name, coins, hp, pb))

    rows.sort(key=lambda t: (-t[2], -t[4], -t[3], t[1].lower()))
    return rows

def _rank_emoji(n: int) -> str:
    return "🥇" if n == 1 else "🥈" if n == 2 else "🥉" if n == 3 else f"{n}."

def _format_line(idx: int, name: str, coins: int, hp: int, pb: int) -> str:
    medal = _rank_emoji(idx)
    pb_part = f" | 🛡 {pb} PB" if pb > 0 else ""
    return f"**{medal} {name}** → 💰 **{coins}** GotCoins | ❤️ **{hp}** PV{pb_part}"

def _build_embed(guild: discord.Guild, rows: List[Tuple[int, str, int, int, int]]) -> discord.Embed:
    e = discord.Embed(
        title="🏆 CLASSEMENT GOTVALIS — ÉDITION SPÉCIALE 🏆",
        color=discord.Color.gold(),
    )
    lines: List[str] = []
    for i, (_, name, coins, hp, pb) in enumerate(rows[:10], start=1):
        lines.append(_format_line(i, name, coins, hp, pb))

    e.description = "\n".join(lines) if lines else "_Aucun joueur classé pour le moment._"
    e.set_footer(text="💡 Les GotCoins représentent votre richesse accumulée.")
    return e


# ─────────────────────────────────────────────────────────
# Debounce & mise à jour “auto”
# ─────────────────────────────────────────────────────────
_update_tasks: Dict[int, asyncio.Task] = {}      # guild_id -> task en cours
_last_snapshots: Dict[int, List[Tuple[int, int, int]]] = {}  # guild_id -> [(uid, coins, pb)]

async def _do_update(bot: commands.Bot, gid: int):
    guild = bot.get_guild(gid)
    if not guild:
        return

    cfg = _get_cfg_for_guild(gid)
    channel_id = int(cfg.get("channel_id") or 0)
    message_id = int(cfg.get("message_id") or 0)

    # Si pas configuré, on ne fait rien
    if channel_id == 0:
        return

    channel = guild.get_channel(channel_id)
    if not isinstance(channel, (discord.TextChannel, discord.Thread)):
        return

    rows = _rank_rows(guild)

    # Snapshot minimal pour détection de changement du top10
    new_sig = [(uid, coins, pb) for uid, _, coins, _, pb in rows[:10]]
    old_sig = _last_snapshots.get(gid)
    if new_sig == old_sig:
        return  # rien n'a changé
    _last_snapshots[gid] = new_sig

    embed = _build_embed(guild, rows)

    # éditer le message existant ou en créer un
    msg: Optional[discord.Message] = None
    if message_id:
        try:
            msg = await channel.fetch_message(message_id)
        except Exception:
            msg = None

    if msg is None:
        try:
            msg = await channel.send(embed=embed)
            try:
                await msg.pin()
            except Exception:
                pass
            cfg["message_id"] = msg.id
            _save_cfg()
        except Exception:
            return
    else:
        try:
            await msg.edit(embed=embed)
        except Exception:
            try:
                msg = await channel.send(embed=embed)
                try:
                    await msg.pin()
                except Exception:
                    pass
                cfg["message_id"] = msg.id
                _save_cfg()
            except Exception:
                return

def _cancel_task(gid: int):
    t = _update_tasks.pop(gid, None)
    if t and not t.done():
        t.cancel()

def _schedule(bot: commands.Bot, gid: int, delay: float = 2.0):
    _cancel_task(gid)

    async def _worker():
        try:
            await asyncio.sleep(delay)
            await _do_update(bot, gid)
        except asyncio.CancelledError:
            pass

    _update_tasks[gid] = bot.loop.create_task(_worker())


# ─────────────────────────────────────────────────────────
# Helper PUBLIC à utiliser depuis d'autres cogs
# ─────────────────────────────────────────────────────────
def schedule_lb_update(bot: commands.Bot, guild_id: int, reason: str = ""):
    """
    Appelle ceci quand la richesse / PV / PB d'un joueur a changé.
    Exemples :
      - après /daily : schedule_lb_update(self.bot, guild_id, "daily")
      - après achat/vente : schedule_lb_update(self.bot, guild_id, "shop")
      - après combat (dégâts, soins, pb) : schedule_lb_update(self.bot, guild_id, "combat")
    """
    _schedule(bot, guild_id, delay=2.0)


# ─────────────────────────────────────────────────────────
# Utilitaires pour boucle périodique
# ─────────────────────────────────────────────────────────
def _iter_configured_guild_ids() -> List[int]:
    gids: List[int] = []
    key = "leaderboard_live"
    if _storage is not None and isinstance(getattr(_storage, key, None), dict):
        for gid_str, cfg in getattr(_storage, key).items():
            try:
                gid = int(gid_str)
            except Exception:
                continue
            if int(cfg.get("channel_id", 0) or 0):
                gids.append(gid)
    else:
        mem = getattr(_get_cfg_for_guild, "_mem", {})
        if isinstance(mem, dict):
            for gid_str, cfg in mem.items():
                try:
                    gid = int(gid_str)
                except Exception:
                    continue
                if int(cfg.get("channel_id", 0) or 0):
                    gids.append(gid)
    return gids


# ─────────────────────────────────────────────────────────
# Le Cog
# ─────────────────────────────────────────────────────────
class LiveLeaderboard(commands.Cog):
    """Classement persistant (top 10) basé sur la richesse (GotCoins) + PV/PB."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.auto_refresh.start()     # boucle périodique (filet de sécurité)

    # — Admin: définir le salon & créer/épingle le message persistant
    @app_commands.default_permissions(administrator=True)
    @app_commands.command(name="lb_set", description="(Admin) Définit le salon du classement persistant et le crée/replace.")
    @app_commands.describe(channel="Salon où poster le classement")
    async def lb_set(self, inter: discord.Interaction, channel: discord.TextChannel):
        if not inter.guild:
            return await inter.response.send_message("Commande serveur uniquement.", ephemeral=True)

        cfg = _get_cfg_for_guild(inter.guild.id)
        cfg["channel_id"] = channel.id
        cfg["message_id"] = 0  # on recréera proprement
        _save_cfg()

        await inter.response.defer(ephemeral=True, thinking=True)
        await _do_update(self.bot, inter.guild.id)
        await inter.followup.send(f"✅ Classement persistant configuré dans {channel.mention}.", ephemeral=True)

    # — Admin: refresh manuel
    @app_commands.default_permissions(administrator=True)
    @app_commands.command(name="lb_refresh", description="(Admin) Recalcule et met à jour le classement persistant.")
    async def lb_refresh(self, inter: discord.Interaction):
        if not inter.guild:
            return await inter.response.send_message("Commande serveur uniquement.", ephemeral=True)
        await inter.response.defer(ephemeral=True, thinking=True)
        await _do_update(self.bot, inter.guild.id)
        await inter.followup.send("🔁 Classement mis à jour.", ephemeral=True)

    # — Admin: activer/désactiver le “rafraîchissement à chaque action”
    @app_commands.default_permissions(administrator=True)
    @app_commands.command(
        name="lb_auto",
        description="(Admin) Active/désactive le rafraîchissement à chaque action (global)."
    )
    @app_commands.describe(enabled="True = ON, False = OFF")
    async def lb_auto(self, inter: discord.Interaction, enabled: bool):
        if not inter.guild:
            return await inter.response.send_message("Commande serveur uniquement.", ephemeral=True)
        cfg = _get_cfg_for_guild(inter.guild.id)
        cfg["auto_all"] = 1 if enabled else 0
        _save_cfg()
        await inter.response.send_message(
            f"✅ Auto-refresh **{'activé' if enabled else 'désactivé'}** pour ce serveur.",
            ephemeral=True
        )

    # — Listeners pour déclenchement “à chaque action”
    @commands.Cog.listener()
    async def on_app_command_completion(self, interaction: discord.Interaction, command: app_commands.Command):
        if interaction.guild and _auto_all_enabled(interaction.guild.id):
            schedule_lb_update(self.bot, interaction.guild.id, f"/{command.name}")

    @commands.Cog.listener()
    async def on_command_completion(self, ctx: commands.Context):
        if ctx.guild and _auto_all_enabled(ctx.guild.id):
            name = ""
            try:
                if ctx.command:
                    name = ctx.command.qualified_name
            except Exception:
                pass
            schedule_lb_update(self.bot, ctx.guild.id, f"!{name}")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.guild and not message.author.bot and _auto_all_enabled(message.guild.id):
            schedule_lb_update(self.bot, message.guild.id, "message")

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if member.guild and _auto_all_enabled(member.guild.id):
            schedule_lb_update(self.bot, member.guild.id, "voice")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        schedule_lb_update(self.bot, member.guild.id, "member_join")

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        schedule_lb_update(self.bot, member.guild.id, "member_remove")

    # — Boucle périodique (2 min) : rattrapage si un event est manqué
    @tasks.loop(minutes=2)
    async def auto_refresh(self):
        for gid in _iter_configured_guild_ids():
            await _do_update(self.bot, gid)

    @auto_refresh.before_loop
    async def _wait_ready(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(LiveLeaderboard(bot))

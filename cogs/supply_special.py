# cogs/supply_special.py (extrait: imports)
from __future__ import annotations
import asyncio
import random
from dataclasses import dataclass, field
from typing import Dict, Optional, Set, Tuple

import discord
from discord.ext import commands, tasks
from discord import app_commands

# Imports robustes
try:
    from utils import get_random_item as _get_random_item, OBJETS
except ImportError:
    from ..utils import get_random_item as _get_random_item, OBJETS

try:
    from inventory_db import add_item
except ImportError:
    from ..inventory_db import add_item

try:
    from economy_db import add_balance
except ImportError:
    from ..economy_db import add_balance

try:
    from stats_db import get_hp, heal_user, deal_damage
except ImportError:
    from ..stats_db import get_hp, heal_user, deal_damage


# ─────────────────────────────────────────────────────────────
# Réglages
# ─────────────────────────────────────────────────────────────

CLAIM_EMOJI = "🎁"                # Emoji unique pour réclamer ce "supply spécial"
TICKET_EMOJI = "🎫"               # Emoji des tickets (doit exister dans ton écosystème)
MSG_QUOTA_DEFAULT = 20            # Quota de messages non-bots requis pour autoriser un drop
WINNERS_DEFAULT = 5               # Nombre de gagnants (premiers à réagir)
DROP_CHANCE_TICK = 0.30           # Chance par tick (toutes les 60s) de spawn si quota OK durant la tranche
CHECK_INTERVAL = 60               # Vérification toutes les 60s

# Répartition de rareté des types de récompenses (somme libre)
WEIGHTS = {
    "items": 40,   # 3 à 5 objets identiques tirés via utils.OBJETS (📦 et 💰 exclus)
    "coins": 25,   # 50 à 150 GoldValis
    "heal": 15,    # 5 à 20 si le joueur a perdu des PV
    "damage": 12,  # 5 à 20 dégâts (source=0)
    "tickets": 8,  # 1 à 3 🎫
}

# Exclure certains emojis de la catégorie "items"
EXCLUS_ITEMS = {"📦", "💰"}  # on laisse 🎫 pour la catégorie "tickets" uniquement

# ─────────────────────────────────────────────────────────────
# Fenêtres horaires (UTC locale du process)
# ─────────────────────────────────────────────────────────────
# Chaque tranche: (start_hour, end_hour, force_hour)
WINDOWS: Tuple[Tuple[int, int, int], ...] = (
    (8, 12, 12),   # 08:00–12:00 → force à 12:00 si pas déjà drop
    (13, 16, 16),  # 13:00–16:00 → force à 16:00
    (18, 22, 22),  # 18:00–22:00 → force à 22:00
)

# ─────────────────────────────────────────────────────────────
# État par serveur
# ─────────────────────────────────────────────────────────────

@dataclass
class ActiveSpecial:
    message_id: int
    channel_id: int
    guild_id: int
    winners_max: int
    started_ts: float
    winners: Set[int] = field(default_factory=set)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

@dataclass
class GuildState:
    enabled: bool = True
    msg_quota: int = MSG_QUOTA_DEFAULT
    winners: int = WINNERS_DEFAULT
    # dernier salon texte actif (non-bots)
    last_active_channel_id: Optional[int] = None
    # messages depuis le dernier drop
    msgs_since_last_drop: int = 0
    # timestamp du dernier drop (info)
    last_drop_ts: float = 0.0
    # suivi "un drop max par tranche" (clé = index de tranche → bool)
    window_dropped: Dict[int, str] = field(default_factory=dict)  # "yes" pour aujourd'hui
    # drop actif
    active: Optional[ActiveSpecial] = None

# ─────────────────────────────────────────────────────────────

class SupplySpecialCog(commands.Cog):
    """
    Supply spécial automatique par tranches horaires avec quota de messages.
    - Réagit à l'activité (dernière chaîne texto non-bot)
    - 5 premiers à cliquer sur 🎁 gagnent
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._g: Dict[int, GuildState] = {}  # guild_id -> state
        self._loop_task = self._loop_check.start()

    def cog_unload(self):
        try:
            self._loop_task.cancel()
        except Exception:
            pass

    # ─────────────────────────────────────────────────────────
    # Listeners pour suivre l’activité & éviter bots
    # ─────────────────────────────────────────────────────────
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return
        if not isinstance(message.channel, discord.TextChannel):
            return
        st = self._g.setdefault(message.guild.id, GuildState())
        st.last_active_channel_id = message.channel.id
        st.msgs_since_last_drop += 1

    # ─────────────────────────────────────────────────────────
    # Commandes admin
    # ─────────────────────────────────────────────────────────
    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only()
    @app_commands.command(name="supply_special_enable", description="(Admin) Active le supply spécial auto pour ce serveur.")
    async def cmd_enable(self, inter: discord.Interaction):
        st = self._g.setdefault(inter.guild_id, GuildState())
        st.enabled = True
        await inter.response.send_message("✅ Supply spécial **activé** pour ce serveur.", ephemeral=True)

    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only()
    @app_commands.command(name="supply_special_disable", description="(Admin) Désactive le supply spécial auto pour ce serveur.")
    async def cmd_disable(self, inter: discord.Interaction):
        st = self._g.setdefault(inter.guild_id, GuildState())
        st.enabled = False
        await inter.response.send_message("⛔ Supply spécial **désactivé** pour ce serveur.", ephemeral=True)

    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only()
    @app_commands.command(name="supply_special_config", description="(Admin) Paramètre quota messages et nb gagnants.")
    @app_commands.describe(quota_messages="Messages requis depuis le dernier drop (défaut 20)",
                           winners="Nombre de gagnants (défaut 5)")
    async def cmd_config(self, inter: discord.Interaction, quota_messages: Optional[int] = None, winners: Optional[int] = None):
        st = self._g.setdefault(inter.guild_id, GuildState())
        if quota_messages is not None:
            st.msg_quota = max(1, int(quota_messages))
        if winners is not None:
            st.winners = max(1, int(winners))
        await inter.response.send_message(
            f"⚙️ Config mise à jour : quota={st.msg_quota}, gagnants={st.winners}", ephemeral=True
        )

    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only()
    @app_commands.command(name="supply_special_spawn", description="(Admin) Force un supply spécial maintenant.")
    async def cmd_spawn_now(self, inter: discord.Interaction):
        await inter.response.defer(ephemeral=True, thinking=True)
        ok = await self._try_spawn(inter.guild_id, force=True)
        if ok:
            await inter.followup.send("🎁 Supply spécial **déclenché**.", ephemeral=True)
        else:
            await inter.followup.send("⚠️ Impossible de déclencher (pas de salon actif ou déjà actif).", ephemeral=True)

    # ─────────────────────────────────────────────────────────
    # Boucle d’orchestration
    # ─────────────────────────────────────────────────────────
    @tasks.loop(seconds=CHECK_INTERVAL)
    async def _loop_check(self):
        now = discord.utils.utcnow()
        for guild in list(self.bot.guilds):
            st = self._g.setdefault(guild.id, GuildState())
            if not st.enabled:
                continue

            # Détermine tranche + forçage
            w_idx, in_window, force_now = self._window_status(now)
            if w_idx is None:
                # hors tranches → reset daily flags si nouvelle journée
                self._maybe_reset_day(st, now)
                continue

            # Pas 2 drops sans re-atteindre le quota
            if st.active:
                continue

            # Forçage à l'heure pile si rien n'a drop dans la tranche
            if force_now and st.window_dropped.get(w_idx) != "yes":
                await self._try_spawn(guild.id, force=True)
                continue

            # Si on est dans la tranche : besoin du quota atteint depuis le dernier drop
            if in_window and st.msgs_since_last_drop >= st.msg_quota and st.window_dropped.get(w_idx) != "yes":
                # Chance de drop pendant la tranche
                if random.random() < DROP_CHANCE_TICK:
                    await self._try_spawn(guild.id, force=False)

    @_loop_check.before_loop
    async def _before_loop_check(self):
        await self.bot.wait_until_ready()

    # ─────────────────────────────────────────────────────────
    # Logique fenêtre
    # ─────────────────────────────────────────────────────────
    def _window_status(self, dt: discord.utils.utcnow.__class__):
        """Retourne (idx, in_window: bool, force_now: bool)."""
        h = dt.hour
        m = dt.minute
        for idx, (start_h, end_h, force_h) in enumerate(WINDOWS):
            in_win = (h >= start_h) and (h < end_h)
            force = (h == force_h and m == 0)
            if in_win or force:
                return idx, in_win, force
        return None, False, False

    def _maybe_reset_day(self, st: GuildState, dt):
        # reset quotidien des flags "dropped" (simple : à 00:00 l’instance sera hors tranches)
        # on efface si plus ancien que 24h
        if st.window_dropped and len(st.window_dropped) >= 1:
            # on peut faire plus fin si tu veux, mais suffisant pour un reset quotidien
            st.window_dropped = {}

    # ─────────────────────────────────────────────────────────
    # Spawn & claim
    # ─────────────────────────────────────────────────────────
    async def _try_spawn(self, guild_id: int, force: bool) -> bool:
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return False
        st = self._g.setdefault(guild_id, GuildState())
        if st.active:
            return False

        # Choisit dernier salon actif
        channel = None
        if st.last_active_channel_id:
            ch = guild.get_channel(st.last_active_channel_id)
            if isinstance(ch, discord.TextChannel):
                channel = ch

        # fallback : premier salon texte où le bot peut parler
        if channel is None:
            for ch in guild.text_channels:
                perms = ch.permissions_for(guild.me)
                if perms.send_messages and perms.add_reactions and perms.read_message_history:
                    channel = ch
                    break

        if channel is None:
            return False

        # Embed annonce
        desc = (
            "Un **Supply Spécial** vient de tomber dans le secteur !\n\n"
            f"🕒 Disponible pendant ~5 minutes ou jusqu’à **{WINNERS_DEFAULT} gagnants**.\n"
            f"🎯 Soyez parmi les **{st.winners} premiers** à cliquer sur {CLAIM_EMOJI}.\n\n"
            "Récompenses possibles :\n"
            "• 3–5 × Un même objet (pondéré par le réseau)\n"
            "• 50–150 GoldValis\n"
            "• Soin 5–20 (si PV manquants)\n"
            "• Dégâts 5–20 (source système)\n"
            "• 1–3 Tickets 🎫\n"
        )
        embed = discord.Embed(
            title="📡 Supply Spécial — GotValis",
            description=desc,
            color=discord.Color.gold(),
        )
        msg = await channel.send(embed=embed)
        try:
            await msg.add_reaction(CLAIM_EMOJI)
        except Exception:
            pass

        st.active = ActiveSpecial(
            message_id=msg.id,
            channel_id=channel.id,
            guild_id=guild_id,
            winners_max=st.winners,
            started_ts=discord.utils.utcnow().timestamp(),
        )
        # Ce spawn valide la tranche courante
        now = discord.utils.utcnow()
        w_idx, _, _ = self._window_status(now)
        if w_idx is not None:
            st.window_dropped[w_idx] = "yes"

        # reset du quota messages (pas de double drop)
        st.msgs_since_last_drop = 0

        # timer de fin (5 min)
        self.bot.loop.create_task(self._auto_finalize(guild_id, delay=5 * 60))
        return True

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if str(payload.emoji) != CLAIM_EMOJI:
            return
        if payload.user_id == self.bot.user.id:
            return
        st = self._g.get(payload.guild_id)
        if not st or not st.active or payload.message_id != st.active.message_id:
            return

        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return
        member = guild.get_member(payload.user_id)
        if not member or member.bot:
            return

        channel = guild.get_channel(st.active.channel_id)
        if not isinstance(channel, discord.TextChannel):
            return

        async with st.active.lock:
            if len(st.active.winners) >= st.active.winners_max:
                await self._remove_reaction_safe(channel, st.active.message_id, member)
                return
            if member.id in st.active.winners:
                await self._remove_reaction_safe(channel, st.active.message_id, member)
                return
            st.active.winners.add(member.id)

        # Donner récompense
        await self._grant_reward(channel, member)

        # Fin si on a atteint le max de gagnants
        if len(st.active.winners) >= st.active.winners_max:
            await self._finalize(guild.id)

    async def _auto_finalize(self, guild_id: int, delay: int = 300):
        await asyncio.sleep(delay)
        st = self._g.get(guild_id)
        if st and st.active:
            await self._finalize(guild_id)

    async def _finalize(self, guild_id: int):
        st = self._g.get(guild_id)
        if not st or not st.active:
            return
        guild = self.bot.get_guild(guild_id)
        if not guild:
            st.active = None
            return
        channel = guild.get_channel(st.active.channel_id)
        if not isinstance(channel, discord.TextChannel):
            st.active = None
            return

        # Edit du message pour marquer la fin
        try:
            msg = await channel.fetch_message(st.active.message_id)
            emb = discord.Embed(
                title="✅ Supply Spécial terminé",
                description=f"Gagnants : **{len(st.active.winners)}/{st.active.winners_max}**. Merci d’avoir joué.",
                color=discord.Color.dark_grey(),
            )
            await msg.edit(embed=emb)
            await msg.clear_reactions()
        except Exception:
            pass

        st.active = None

    # ─────────────────────────────────────────────────────────
    # Récompenses
    # ─────────────────────────────────────────────────────────
    async def _grant_reward(self, channel: discord.TextChannel, user: discord.Member):
        kind = random.choices(
            population=list(WEIGHTS.keys()),
            weights=list(WEIGHTS.values()),
            k=1
        )[0]

        if kind == "items":
            emoji = await self._pick_item()
            qty = random.randint(3, 5)
            await add_item(user.id, emoji, qty)
            desc = f"**{user.mention}** obtient **{qty}× {emoji}** !"
        elif kind == "coins":
            amount = random.randint(50, 150)
            new_bal = await add_balance(user.id, amount, reason="Supply Spécial 🎁")
            desc = f"**{user.mention}** gagne **{amount} GoldValis** (nouveau solde: {new_bal})."
        elif kind == "heal":
            # soigne seulement si PV manquants, sinon on bascule en items
            hp, hpmax = await get_hp(user.id)
            if hp < hpmax:
                amount = random.randint(5, 20)
                healed = await heal_user(0, user.id, amount)  # source système
                if healed <= 0:
                    # fallback items si full via passifs
                    emoji = await self._pick_item()
                    qty = random.randint(3, 5)
                    await add_item(user.id, emoji, qty)
                    desc = f"**{user.mention}** obtient **{qty}× {emoji}** !"
                else:
                    desc = f"**{user.mention}** est soigné de **{healed} PV**."
            else:
                emoji = await self._pick_item()
                qty = random.randint(3, 5)
                await add_item(user.id, emoji, qty)
                desc = f"**{user.mention}** obtient **{qty}× {emoji}** !"
        elif kind == "damage":
            amount = random.randint(5, 20)
            await deal_damage(0, user.id, amount)  # source = 0 → stats/économie au bot
            desc = f"**{user.mention}** subit **{amount} dégâts** (⚠️ événement spécial)."
        else:  # tickets
            qty = random.randint(1, 3)
            await add_item(user.id, TICKET_EMOJI, qty)
            desc = f"**{user.mention}** récupère **{qty}× {TICKET_EMOJI}**."

        emb = discord.Embed(
            title="🎖️ Récompense — Supply Spécial",
            description=desc,
            color=discord.Color.green(),
        )
        try:
            await channel.send(embed=emb, silent=True)
        except Exception:
            pass

    async def _pick_item(self) -> str:
        # tente plusieurs tirages jusqu’à exclure 📦 & 💰
        for _ in range(128):
            e = _get_random_item()
            if e and e not in EXCLUS_ITEMS:
                return e
        # secours: choisit un item parmi OBJETS hors exclusions
        candidates = [k for k in OBJETS.keys() if k not in EXCLUS_ITEMS]
        return random.choice(candidates) if candidates else "🍀"

    async def _remove_reaction_safe(self, channel: discord.TextChannel, message_id: int, user: discord.Member):
        try:
            msg = await channel.fetch_message(message_id)
            for r in msg.reactions:
                if str(r.emoji) == CLAIM_EMOJI:
                    await r.remove(user)
                    break
        except Exception:
            pass

# ─────────────────────────────────────────────────────────────
# setup
# ─────────────────────────────────────────────────────────────
async def setup(bot: commands.Bot):
    await bot.add_cog(SupplySpecialCog(bot))

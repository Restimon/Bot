# cogs/ravitaillement.py
from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass, field
from typing import Dict, Set, Optional

import discord
from discord.ext import commands

# ─────────────────────────────────────────────────────────────
# Imports utilitaires (inventaire + économie)
# ─────────────────────────────────────────────────────────────
try:
    from utils import get_random_item, give_random_item
except Exception as e:
    raise RuntimeError("utils.py doit fournir get_random_item() et give_random_item().") from e

try:
    from economy_db import add_balance
except Exception:
    # économie facultative : si absente, on ignore les récompenses 💰
    async def add_balance(user_id: int, delta: int, reason: str = "") -> int:  # type: ignore
        return 0


BOX_EMOJI = "📦"

# Fenêtre de réaction en secondes
CLAIM_WINDOW = 30

# Nombre de messages aléatoire entre deux drops
MIN_MSG = 12
MAX_MSG = 30


@dataclass
class ChannelDropState:
    """État d’un canal pour le ravitaillement auto."""
    # compteur de messages depuis le dernier drop complété
    message_count: int = 0
    # prochain palier aléatoire (12..30)
    next_threshold: int = field(default_factory=lambda: random.randint(MIN_MSG, MAX_MSG))

    # drop actif
    active: bool = False
    drop_message_id: Optional[int] = None
    drop_channel_id: Optional[int] = None
    claimers: Set[int] = field(default_factory=set)
    timer_task: Optional[asyncio.Task] = None


class RavitaillementCog(commands.Cog):
    """
    Système de ravitaillement automatique :
    - Ajoute 📦 sur un message utilisateur quand le seuil est atteint.
    - 30s de fenêtre → récap en embed (récupéré / détruit).
    - Récompenses données uniquement à la fin.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # par-guild → par-channel
        self.states: Dict[int, Dict[int, ChannelDropState]] = {}

    # ─────────────────────────────────────────────────────────
    # Helper: accès/creation d’état
    # ─────────────────────────────────────────────────────────
    def _state_for(self, guild_id: int, channel_id: int) -> ChannelDropState:
        gdict = self.states.setdefault(guild_id, {})
        return gdict.setdefault(channel_id, ChannelDropState())

    # ─────────────────────────────────────────────────────────
    # Core: messages
    # ─────────────────────────────────────────────────────────
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Ignore DMs / bots / messages sans guilde
        if not message.guild or message.author.bot:
            return

        # On n'auto-drop que dans les salons textuels
        if not isinstance(message.channel, (discord.TextChannel, discord.Thread, discord.ForumChannel)):
            return

        st = self._state_for(message.guild.id, message.channel.id)

        # Si un drop est déjà actif, on ne compte pas (on attend la fin)
        if st.active:
            return

        # Incrémente le compteur, et déclenche si palier atteint
        st.message_count += 1
        if st.message_count >= st.next_threshold:
            await self._start_drop_on_message(message)

    # ─────────────────────────────────────────────────────────
    # Début d’un drop : on réagit 📦 au message
    # ─────────────────────────────────────────────────────────
    async def _start_drop_on_message(self, message: discord.Message):
        guild_id = message.guild.id
        channel_id = message.channel.id
        st = self._state_for(guild_id, channel_id)

        # Sécurité : si déjà actif, on annule
        if st.active:
            return

        # Tente d'ajouter la réaction 📦 directement sous le message utilisateur
        try:
            await message.add_reaction(BOX_EMOJI)
        except discord.Forbidden:
            # Pas la permission d’ajouter des réactions
            return
        except discord.HTTPException:
            # Autre erreur HTTP → on abandonne ce drop
            return

        # Armement de l’état actif
        st.active = True
        st.drop_message_id = message.id
        st.drop_channel_id = channel_id
        st.claimers.clear()

        # Lance le timer de 30 secondes pour finaliser
        st.timer_task = asyncio.create_task(self._finalize_after_delay(guild_id, channel_id, CLAIM_WINDOW))

    # ─────────────────────────────────────────────────────────
    # Récolte des réactions pendant la fenêtre
    # ─────────────────────────────────────────────────────────
    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.guild_id is None:
            return
        if str(payload.emoji) != BOX_EMOJI:
            return

        st = self._state_for(payload.guild_id, payload.channel_id)
        if not st.active:
            return
        if st.drop_message_id != payload.message_id:
            return

        # Ignore les bots
        if payload.user_id == (self.bot.user.id if self.bot.user else 0):
            return

        st.claimers.add(int(payload.user_id))

    # ─────────────────────────────────────────────────────────
    # Finalisation du drop
    # ─────────────────────────────────────────────────────────
    async def _finalize_after_delay(self, guild_id: int, channel_id: int, delay: int):
        try:
            await asyncio.sleep(delay)

            st = self._state_for(guild_id, channel_id)
            # re-check actif
            if not st.active or not st.drop_message_id:
                return

            # On prépare l’embed de récap
            channel = self.bot.get_channel(channel_id)
            if not isinstance(channel, (discord.TextChannel, discord.Thread)):
                # Reset état même si on ne peut pas poster
                self._reset_state(st)
                return

            # Filtre final des claimers : ignorer les membres sortis/bots
            valid_claimers: list[discord.Member] = []
            try:
                for uid in st.claimers:
                    m = channel.guild.get_member(uid)
                    if m and not m.bot:
                        valid_claimers.append(m)
            except Exception:
                pass

            if not valid_claimers:
                # Personne n'a cliqué → détruit
                embed = discord.Embed(
                    title="📦 Ravitaillement détruit",
                    color=discord.Color.red(),
                )
                embed.add_field(
                    name="Statut",
                    value="Personne n’a réagi à temps.",
                    inline=False,
                )
                await channel.send(embed=embed)
                # Reset et replanification
                self._reset_state(st)
                return

            # Sinon : distribution des loots maintenant
            lines: list[str] = []
            for member in valid_claimers:
                loot = get_random_item()
                if not loot:
                    continue

                if loot == "💰":
                    # Récompense coins
                    amount = random.randint(5, 15)
                    try:
                        await add_balance(member.id, amount, reason="Ravitaillement")
                        lines.append(f"• {member.mention} → {loot} **+{amount}**")
                    except Exception:
                        # Si économie indispo, on n’affiche que l’emoji
                        lines.append(f"• {member.mention} → {loot}")
                else:
                    # Récompense objet
                    try:
                        give_random_item(str(guild_id), str(member.id), loot)
                        lines.append(f"• {member.mention} → {loot}")
                    except Exception:
                        # Si stockage indispo, on liste quand même
                        lines.append(f"• {member.mention} → {loot}")

            # Envoi du récap (sans description, uniquement un field)
            title = f"📦 Ravitaillement récupéré — {len(valid_claimers)} participant(s)"
            embed = discord.Embed(
                title=title,
                color=discord.Color.green(),
            )
            if lines:
                embed.add_field(
                    name="Récompenses",
                    value="\n".join(lines),
                    inline=False,
                )
            else:
                embed.add_field(
                    name="Récompenses",
                    value="Aucune récompense valide n’a pu être attribuée.",
                    inline=False,
                )

            await channel.send(embed=embed)

            # Reset et replanification
            self._reset_state(st)

        except Exception:
            # En cas d’exception, on tente de ne pas bloquer le cycle
            st = self._state_for(guild_id, channel_id)
            self._reset_state(st)

    def _reset_state(self, st: ChannelDropState):
        """Réinitialise l’état du salon et tire un nouveau seuil."""
        st.active = False
        st.drop_message_id = None
        st.drop_channel_id = None
        st.claimers.clear()
        st.timer_task = None
        st.message_count = 0
        st.next_threshold = random.randint(MIN_MSG, MAX_MSG)


# ─────────────────────────────────────────────────────────────
# Hook extension
# ─────────────────────────────────────────────────────────────
async def setup(bot: commands.Bot):
    await bot.add_cog(RavitaillementCog(bot))

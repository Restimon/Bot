# cogs/ravitaillement.py (extrait: imports)
from __future__ import annotations
import asyncio
import random
from typing import Optional

import discord
from discord.ext import commands
from discord import app_commands

# Imports robustes
try:
    from utils import get_random_item, OBJETS
except ImportError:
    from ..utils import get_random_item, OBJETS

try:
    from inventory_db import add_item
except ImportError:
    from ..inventory_db import add_item

try:
    from economy_db import add_balance
except ImportError:
    from ..economy_db import add_balance


BOX_EMOJI = "📦"  # unique émoji pour claim

# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

# Si tu veux exclure certains items des ravitos (ex: ne pas se dropper eux-mêmes)
EXCLUS = {"📦"}  # tu peux rajouter "💉","👟", etc. si besoin

def get_random_item_filtre() -> Optional[str]:
    """Tire un item avec la pondération de utils.OBJETS et exclut EXCLUS."""
    for _ in range(128):  # évite boucles infinies si pool rikiki
        e = _get_random_item()
        if e and e not in EXCLUS:
            return e
    return None

def reward_desc_for_item(user: discord.abc.User, emoji: str, qty: int, new_balance: Optional[int] = None) -> str:
    """Retour texte pour l'embed après claim."""
    if emoji == "💰":
        assert new_balance is not None
        return f"**{user.mention}** récupère **{qty} GoldValis** ! (nouveau solde: {new_balance})"
    # afficher rareté pour info (optionnel)
    r = int(OBJETS.get(emoji, {}).get("rarete", 25))
    return f"**{user.mention}** obtient **{qty}× {emoji}** *(rareté {r})*."

# ─────────────────────────────────────────────────────────────
# État d’un drop actif
# ─────────────────────────────────────────────────────────────

@dataclass
class ActiveDrop:
    message_id: int
    channel_id: int
    guild_id: int
    winners_max: int
    duration_sec: int
    started: float
    winners: Set[int] = field(default_factory=set)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

# ─────────────────────────────────────────────────────────────
# Cog
# ─────────────────────────────────────────────────────────────

class RavitaillementCog(commands.Cog):
    """
    /ravitaillement set_channel #salon   → (facultatif) mémoriser un salon par défaut
    /ravitaillement spawn [winners] [durée] → lance un drop (réaction 📦 pour claim)
    /ravitaillement stop                  → stop le drop actif (si présent)

    Le premier N à réagir à 📦 obtient une récompense pondérée par utils.OBJETS.
    Récompenses:
      - 5% : 💰 (50 à 150)
      - sinon : item (1 à 3 unités)
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._default_channel: Dict[int, int] = {}  # guild_id -> channel_id
        self._active_drop: Dict[int, ActiveDrop] = {}  # guild_id -> ActiveDrop

    # ── Commandes Admin
    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only()
    @app_commands.command(name="ravitaillement_set_channel", description="(Admin) Définit le salon par défaut des ravitaillements.")
    async def set_channel(self, inter: discord.Interaction, channel: discord.TextChannel):
        self._default_channel[inter.guild_id] = channel.id
        await inter.response.send_message(f"✅ Salon par défaut défini pour les ravitaillements : {channel.mention}", ephemeral=True)

    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only()
    @app_commands.command(name="ravitaillement_spawn", description="(Admin) Lance un ravitaillement dans le salon courant ou par défaut.")
    @app_commands.describe(winners="Nombre maximum de gagnants (défaut 5)", duree="Durée en secondes (défaut 300s)")
    async def spawn(self, inter: discord.Interaction, winners: int = 5, duree: int = 300):
        await inter.response.defer(ephemeral=True, thinking=True)

        # déjà un drop en cours ?
        if inter.guild_id in self._active_drop:
            return await inter.followup.send("⚠️ Un ravitaillement est déjà en cours sur ce serveur. Utilise `/ravitaillement_stop` d’abord.", ephemeral=True)

        # salon cible
        ch: discord.TextChannel
        if inter.channel and isinstance(inter.channel, discord.TextChannel):
            ch = inter.channel
        else:
            # salon par défaut
            ch_id = self._default_channel.get(inter.guild_id)
            if not ch_id:
                return await inter.followup.send("❌ Aucun salon par défaut et ici n'est pas un salon texte.", ephemeral=True)
            ch = inter.guild.get_channel(ch_id) or await self.bot.fetch_channel(ch_id)

        # Post du message de drop
        embed = discord.Embed(
            title="Ravitaillement GotValis 📦",
            description=(
                f"Une caisse de ravitaillement vient d'apparaître !\n\n"
                f"**Durée :** {duree} sec\n"
                f"**Gagnants max :** {winners}\n\n"
                f"Réagissez avec {BOX_EMOJI} pour réclamer."
            ),
            color=discord.Color.blurple(),
        )
        msg = await ch.send(embed=embed)
        try:
            await msg.add_reaction(BOX_EMOJI)
        except Exception:
            pass

        # Enregistrer l'état
        self._active_drop[inter.guild_id] = ActiveDrop(
            message_id=msg.id,
            channel_id=msg.channel.id,
            guild_id=inter.guild_id,
            winners_max=max(1, winners),
            duration_sec=max(10, min(3600, duree)),
            started=discord.utils.utcnow().timestamp(),
        )

        await inter.followup.send(f"✅ Ravitaillement lancé dans {ch.mention}.", ephemeral=True)

        # Auto-stop après la durée
        self.bot.loop.create_task(self._auto_stop(inter.guild_id))

    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only()
    @app_commands.command(name="ravitaillement_stop", description="(Admin) Stoppe le ravitaillement en cours.")
    async def stop(self, inter: discord.Interaction):
        await inter.response.defer(ephemeral=True)
        if inter.guild_id not in self._active_drop:
            return await inter.followup.send("ℹ️ Aucun ravitaillement en cours.", ephemeral=True)

        await self._finalize_drop(inter.guild_id, reason="Arrêt manuel")
        await inter.followup.send("🛑 Ravitaillement stoppé.", ephemeral=True)

    # ── Listener de réaction
    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        # filtre: émoji 📦, pas un bot, drop actif
        if str(payload.emoji) != BOX_EMOJI:
            return
        if payload.user_id == self.bot.user.id:
            return
        drop = self._active_drop.get(payload.guild_id)
        if not drop or payload.message_id != drop.message_id:
            return

        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return
        member = guild.get_member(payload.user_id)
        if not member or member.bot:
            return

        # Chan & message
        channel = guild.get_channel(drop.channel_id)
        if not isinstance(channel, discord.TextChannel):
            return

        # Critères de fin
        now = discord.utils.utcnow().timestamp()
        if now - drop.started > drop.duration_sec:
            # trop tard → enlever la réaction pour feedback soft
            await self._remove_user_reaction_safe(channel, drop.message_id, member)
            return

        # Traiter le claim (avec lock)
        async with drop.lock:
            # déjà plein ?
            if len(drop.winners) >= drop.winners_max:
                await self._remove_user_reaction_safe(channel, drop.message_id, member)
                return

            # déjà gagnant ?
            if member.id in drop.winners:
                await self._remove_user_reaction_safe(channel, drop.message_id, member)
                return

            # Ok, on valide ce gagnant
            drop.winners.add(member.id)

        # Récompense
        await self._grant_reward(channel, member)

        # Si on a atteint le max, on finalise
        if len(drop.winners) >= drop.winners_max:
            await self._finalize_drop(payload.guild_id, reason="Gagnants atteints")

    # ─────────────────────────────────────────────────────────
    # Implémentations internes
    # ─────────────────────────────────────────────────────────
    async def _grant_reward(self, channel: discord.TextChannel, user: discord.Member):
        """Attribue une récompense au joueur et envoie un petit embed feedback."""
        emoji = get_random_item_filtre()
        if not emoji:
            # fallback si pool vide pour une raison quelconque
            emoji = "💰"

        if emoji == "💰":
            gain = random.randint(50, 150)
            new_bal = await add_balance(user.id, gain, reason="Ravitaillement 📦")
            desc = reward_desc_for_item(user, emoji, gain, new_balance=new_bal)
        else:
            qty = random.randint(1, 3)
            await add_item(user.id, emoji, qty)
            desc = reward_desc_for_item(user, emoji, qty)

        emb = discord.Embed(
            title="🎁 Récompense de ravitaillement",
            description=desc,
            color=discord.Color.gold(),
        )
        try:
            await channel.send(embed=emb, silent=True)
        except Exception:
            pass

    async def _auto_stop(self, guild_id: int):
        """Stoppe automatiquement après la durée prévue."""
        drop = self._active_drop.get(guild_id)
        if not drop:
            return
        await asyncio.sleep(max(1, drop.duration_sec + 1))
        # Peut avoir été stoppé entre-temps
        if guild_id in self._active_drop:
            await self._finalize_drop(guild_id, reason="Temps écoulé")

    async def _finalize_drop(self, guild_id: int, reason: str = ""):
        """Nettoie l’état et met à jour le message pour indiquer la fin."""
        drop = self._active_drop.pop(guild_id, None)
        if not drop:
            return
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return
        channel = guild.get_channel(drop.channel_id)
        if not isinstance(channel, discord.TextChannel):
            return

        # Editer le message d’origine (si récupérable) pour marquer la fin
        try:
            msg = await channel.fetch_message(drop.message_id)
            winners_count = len(drop.winners)
            embed = discord.Embed(
                title="Ravitaillement terminé 📦",
                description=(
                    f"**Raison :** {reason or '—'}\n"
                    f"**Gagnants :** {winners_count}/{drop.winners_max}\n\n"
                    f"Merci de votre participation."
                ),
                color=discord.Color.dark_grey(),
            )
            await msg.edit(embed=embed)
            # Optionnel: retirer les réactions
            await msg.clear_reactions()
        except Exception:
            pass

    async def _remove_user_reaction_safe(self, channel: discord.TextChannel, message_id: int, user: discord.Member):
        """Best effort pour retirer la réaction d’un utilisateur (silencieux)."""
        try:
            msg = await channel.fetch_message(message_id)
            for reaction in msg.reactions:
                if str(reaction.emoji) == BOX_EMOJI:
                    await reaction.remove(user)
                    break
        except Exception:
            pass

# ─────────────────────────────────────────────────────────────
# Setup
# ─────────────────────────────────────────────────────────────
async def setup(bot: commands.Bot):
    await bot.add_cog(RavitaillementCog(bot))

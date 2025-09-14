# cogs/ravitaillement.py
from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass, field
from typing import Dict, Optional, Set

import discord
from discord.ext import commands
from discord import app_commands

# ─────────────────────────────────────────────────────────────
# Imports robustes (fonctionnent en local et sur Render)
# ─────────────────────────────────────────────────────────────
try:
    from utils import get_random_item, OBJETS  # pool cohérent avec tes raretés
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

# ─────────────────────────────────────────────────────────────
# Constantes
# ─────────────────────────────────────────────────────────────
BOX_EMOJI = "📦"   # une seule réaction pour réclamer

# ─────────────────────────────────────────────────────────────
# État d’un drop par serveur
# ─────────────────────────────────────────────────────────────
@dataclass
class DropState:
    guild_id: int
    channel_id: int
    message_id: Optional[int] = None
    claimed: Set[int] = field(default_factory=set)
    active: bool = False

# Mémoire en RAM : un drop actif par serveur
ACTIVE_DROPS: Dict[int, DropState] = {}

# ─────────────────────────────────────────────────────────────
# Cog
# ─────────────────────────────────────────────────────────────
class RavitaillementCog(commands.Cog):
    """Ravitaillement simple : le bot pose une caisse ; cliquer 📦 pour réclamer un lot."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # -------- Admin: forcer un drop dans un salon ----------
    @app_commands.default_permissions(administrator=True)
    @app_commands.command(name="ravitaillement", description="(Admin) Dépose une caisse à réclamer dans ce salon.")
    async def cmd_ravitaillement(self, inter: discord.Interaction):
        await inter.response.defer(thinking=True, ephemeral=True)

        if not inter.channel or not isinstance(inter.channel, discord.TextChannel):
            return await inter.followup.send("❌ Cette commande doit être utilisée dans un salon textuel.", ephemeral=True)

        guild_id = inter.guild_id
        channel = inter.channel

        # Empêche 2 drops simultanés par serveur
        state = ACTIVE_DROPS.get(guild_id)
        if state and state.active and state.message_id:
            return await inter.followup.send("⚠️ Un ravitaillement est déjà actif dans ce serveur.", ephemeral=True)

        embed = discord.Embed(
            title="Ravitaillement GotValis",
            description=f"Une caisse vient d'être larguée !\n**Clique {BOX_EMOJI} pour réclamer ta récompense.**",
            color=discord.Color.blurple(),
        )
        embed.set_footer(text="GotValis • Ravitaillement standard")

        msg = await channel.send(embed=embed)
        try:
            await msg.add_reaction(BOX_EMOJI)
        except Exception:
            pass

        ACTIVE_DROPS[guild_id] = DropState(
            guild_id=guild_id,
            channel_id=channel.id,
            message_id=msg.id,
            claimed=set(),
            active=True,
        )
        await inter.followup.send("✅ Caisse déployée.", ephemeral=True)

    # -------- Gestion des réactions ----------
    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        # Ignore les bots
        if payload.user_id == self.bot.user.id:
            return

        # On ne gère que l'emoji 📦
        if str(payload.emoji) != BOX_EMOJI:
            return

        guild_id = payload.guild_id
        state = ACTIVE_DROPS.get(guild_id)
        if not state or not state.active:
            return
        if payload.message_id != state.message_id:
            return

        # Récup contexte
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return
        channel = guild.get_channel(state.channel_id)
        if not isinstance(channel, discord.TextChannel):
            return

        user_id = payload.user_id
        member = guild.get_member(user_id)
        if not member or member.bot:
            return

        # Anti double-claim
        if user_id in state.claimed:
            # on nettoie sa réaction pour signaler que c'est déjà pris
            try:
                msg = await channel.fetch_message(state.message_id)
                await msg.remove_reaction(BOX_EMOJI, member)
            except Exception:
                pass
            return

        # Récompense cohérente avec tes raretés (utils.get_random_item)
        emoji = get_random_item() or "🍀"

        # 💰 = coins ; sinon emoji objet → inventaire
        if emoji == "💰":
            coins = random.randint(10, 50)
            try:
                await add_balance(user_id, coins, reason="Ravitaillement")
            except Exception:
                # si l’éco n’est pas dispo, on “convertit” en 🍀
                emoji = "🍀"

        if emoji != "💰":
            # ajoute 1 exemplaire de l’item
            try:
                await add_item(user_id, emoji, 1)
            except Exception:
                # si inventaire indispo, fallback sur coins
                coins = random.randint(10, 50)
                try:
                    await add_balance(user_id, coins, reason="Ravitaillement(Fallback)")
                    emoji = "💰"
                except Exception:
                    # rien à faire
                    return

        # Confirme dans le salon
        if emoji == "💰":
            txt = f"💰 {member.mention} récupère **{coins} GoldValis** dans la caisse !"
        else:
            # petit label si dispo
            label = OBJETS.get(emoji, {}).get("label") or ""
            txt = f"{emoji} {member.mention} récupère **{label or 'un objet'}** !"

        try:
            await channel.send(txt, allowed_mentions=discord.AllowedMentions(users=True))
        except Exception:
            pass

        # Marque comme pris
        state.claimed.add(user_id)

        # (Optionnel) Auto-fermeture si > X claims. Ici on laisse illimité.
        # Pour limiter, par ex:
        # if len(state.claimed) >= 10:
        #     state.active = False
        #     ACTIVE_DROPS[guild_id] = state

    # -------- Nettoyage si message supprimé ----------
    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent):
        # si le message supprimé est un drop, on clôt
        for gid, st in list(ACTIVE_DROPS.items()):
            if st.message_id == payload.message_id:
                st.active = False
                ACTIVE_DROPS[gid] = st

# ─────────────────────────────────────────────────────────────
# Setup
# ─────────────────────────────────────────────────────────────
async def setup(bot: commands.Bot):
    await bot.add_cog(RavitaillementCog(bot))

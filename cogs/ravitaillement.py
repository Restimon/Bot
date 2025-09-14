# cogs/ravitaillement.py
from __future__ import annotations

import asyncio
import random
from typing import Dict, Set, Optional, List

import discord
from discord.ext import commands

# --- Récompenses / persistance
from utils import get_random_item  # renvoie "💰" ou un emoji d'objet selon tes pondérations
from economy_db import add_balance
from inventory_db import add_item

BOX_EMOJI = "📦"
WINDOW_SECONDS = 30  # fenêtre pendant laquelle on peut cliquer pour participer

class RavitaillementCog(commands.Cog):
    """
    Auto-drop :
      • Compte les messages par salon.
      • Seuil aléatoire entre 12 et 30.
      • Ne lance pas de nouveau drop tant que le précédent n’est pas terminé.
      • Ajoute 📦 en réaction sous le message déclencheur.
      • 30s plus tard, poste un embed récap avec les gains.

    Admin menu (clic droit) : "Ravitaillement ici" pour forcer un drop sur un message.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Par salon
        self._msg_count: Dict[int, int] = {}             # channel_id -> compteur de messages
        self._threshold: Dict[int, int] = {}             # channel_id -> prochain seuil aléatoire
        self._active_drop: Dict[int, bool] = {}          # channel_id -> drop en cours ?
        self._participants: Dict[int, Set[int]] = {}     # message_id -> {user_id}
        self._lock: Dict[int, asyncio.Lock] = {}         # channel_id -> lock pour éviter courses

    # ---------------------------
    # Utilitaires internes
    # ---------------------------
    def _get_lock(self, channel_id: int) -> asyncio.Lock:
        if channel_id not in self._lock:
            self._lock[channel_id] = asyncio.Lock()
        return self._lock[channel_id]

    def _ensure_threshold(self, channel_id: int) -> int:
        """Fixe un seuil aléatoire [12..30] s'il n'existe pas encore, puis le retourne."""
        if channel_id not in self._threshold:
            self._threshold[channel_id] = random.randint(12, 30)
        return self._threshold[channel_id]

    def _reset_counter(self, channel_id: int) -> None:
        self._msg_count[channel_id] = 0
        self._threshold[channel_id] = random.randint(12, 30)

    # ---------------------------
    # Auto-drop: écoute des messages
    # ---------------------------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # On ignore MP et bots
        if message.author.bot or not message.guild:
            return

        chan_id = message.channel.id
        lock = self._get_lock(chan_id)

        # Compte + seuil
        self._msg_count[chan_id] = self._msg_count.get(chan_id, 0) + 1
        threshold = self._ensure_threshold(chan_id)

        # Si un drop est actif dans ce salon → on attend la fin (pas d’auto drop)
        if self._active_drop.get(chan_id, False):
            return

        # Si on atteint le seuil, on tente de lancer un drop sur CE message
        if self._msg_count[chan_id] >= threshold:
            # Protège contre une double exécution
            async with lock:
                if self._active_drop.get(chan_id, False):
                    return
                self._active_drop[chan_id] = True

            try:
                await self._launch_drop_on_message(message)
            finally:
                # fin du drop
                async with lock:
                    self._active_drop[chan_id] = False
                    self._reset_counter(chan_id)

    # ---------------------------
    # Admin: clic droit "Ravitaillement ici"
    # ---------------------------
    @discord.app_commands.context_menu(name="Ravitaillement ici")
    @discord.app_commands.default_permissions(manage_guild=True)
    async def drop_on_message(self, interaction: discord.Interaction, message: discord.Message):
        """Force un drop sur un message (admins/mods)."""
        if not interaction.guild or not message.guild or interaction.guild.id != message.guild.id:
            return await interaction.response.send_message("❌ Contexte invalide.", ephemeral=True)

        chan_id = message.channel.id
        lock = self._get_lock(chan_id)

        async with lock:
            if self._active_drop.get(chan_id, False):
                return await interaction.response.send_message("⚠️ Un ravitaillement est déjà en cours dans ce salon.", ephemeral=True)
            self._active_drop[chan_id] = True

        await interaction.response.send_message("✅ Ravitaillement lancé.", ephemeral=True)

        try:
            await self._launch_drop_on_message(message)
        finally:
            async with lock:
                self._active_drop[chan_id] = False
                self._reset_counter(chan_id)

    # ---------------------------
    # Noyau: lance un drop sur un message donné
    # ---------------------------
    async def _launch_drop_on_message(self, message: discord.Message):
        """
        • Ajoute 📦 sous le message.
        • Attend WINDOW_SECONDS.
        • Récupère les réacteurs, attribue les gains, puis envoie un embed récap.
        """
        # On note localement les participants pour éviter les edits bizarres
        self._participants.clear()

        try:
            await message.add_reaction(BOX_EMOJI)
        except Exception:
            # Si on ne peut pas réagir (permissions), on annule proprement
            try:
                await message.channel.send("⚠️ Impossible d'ajouter la réaction 📦 (permissions manquantes).")
            except Exception:
                pass
            return

        # Laisser du temps pour cliquer
        await asyncio.sleep(WINDOW_SECONDS)

        # Récupère les utilisateurs ayant réagi à 📦
        users: List[discord.User] = []
        try:
            # Re-fetch la réaction pour être sûr d’avoir la liste
            msg = await message.channel.fetch_message(message.id)
            react = discord.utils.get(msg.reactions, emoji=BOX_EMOJI)
            if react:
                async for u in react.users():
                    if u.bot:
                        continue
                    users.append(u)
        except Exception:
            users = []

        # Applique les récompenses + compose le récap
        fields = []
        for u in users:
            reward = get_random_item()
            if reward == "💰":
                amount = random.randint(8, 20)
                try:
                    await add_balance(u.id, amount, reason="Ravitaillement")
                    fields.append(("💰 Gains", f"{u.mention} reçoit **{amount} GoldValis**.", False))
                except Exception:
                    fields.append(("⚠️ Erreur", f"Impossible d’ajouter des GoldValis à {u.mention}.", False))
            elif isinstance(reward, str):
                try:
                    await add_item(u.id, reward, 1)
                    fields.append(("🎁 Objet", f"{u.mention} récupère **{reward}** !", False))
                except Exception:
                    fields.append(("⚠️ Erreur", f"Impossible d’ajouter l’objet à {u.mention}.", False))
            else:
                # fallback si rien tiré
                amount = random.randint(5, 10)
                try:
                    await add_balance(u.id, amount, reason="Ravitaillement (fallback)")
                    fields.append(("💰 Gains", f"{u.mention} reçoit **{amount} GoldValis**.", False))
                except Exception:
                    fields.append(("⚠️ Erreur", f"Impossible d’ajouter la récompense à {u.mention}.", False))

        # Envoie du récap (sous forme d’embed propre)
        try:
            if users:
                embed = discord.Embed(
                    title="📦 Ravitaillement terminé",
                    description=f"Fenêtre close ({WINDOW_SECONDS}s). Voici les récompenses :",
                    color=discord.Color.blurple(),
                )
                # Regroupe joliment
                for name, value, inline in fields:
                    embed.add_field(name=name, value=value, inline=inline)
                embed.set_footer(text="GotValis • Ravitaillement automatique")
                await message.reply(embed=embed, mention_author=False)
            else:
                await message.reply(
                    embed=discord.Embed(
                        title="📦 Ravitaillement terminé",
                        description="Personne n’a participé… la caisse repart dans les limbes.",
                        color=discord.Color.dark_grey(),
                    ),
                    mention_author=False,
                )
        except Exception:
            # Si l’embed échoue, silencieux.
            pass


async def setup(bot: commands.Bot):
    await bot.add_cog(RavitaillementCog(bot))

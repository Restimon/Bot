# cogs/ravitaillement.py
from __future__ import annotations

import asyncio
import random
from typing import Dict, Set, Optional

import discord
from discord.ext import commands

# Notre tirage pondéré par rareté + emojis disponibles
from utils import get_random_item
# Persistance inventaire (SQLite)
from inventory_db import add_item

BOX_EMOJI = "📦"
CLAIM_WINDOW_SECONDS = 30
AUTO_MIN_MSG = 12
AUTO_MAX_MSG = 30

class RavitaillementCog(commands.Cog):
    """
    Ravitaillement automatique par salon :
      • Un drop peut se déclencher aléatoirement entre 12 et 30 messages (par salon).
      • Le drop place une réaction 📦 sous le message déclencheur.
      • Les membres cliquent 📦 pendant 30s.
      • À la fin, on attribue les loots (pondérés par rareté) PUIS on poste un récap :
           📦 Ravitaillement récupéré !
           - @A → 🔫
           - @B → 🍀
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # État par salon
        # channel_id -> {
        #   "msg_count": int,
        #   "threshold": int,
        #   "active": bool,
        #   "message_id": Optional[int],
        #   "participants": Set[int],
        # }
        self.state: Dict[int, Dict] = {}

    # -------------------------------
    # Utilitaires d'état par salon
    # -------------------------------
    def _get_state(self, channel_id: int) -> Dict:
        st = self.state.setdefault(channel_id, {
            "msg_count": 0,
            "threshold": random.randint(AUTO_MIN_MSG, AUTO_MAX_MSG),
            "active": False,
            "message_id": None,
            "participants": set(),  # type: Set[int]
        })
        # garde des types corrects
        st["participants"] = set(st.get("participants", set()))
        return st

    def _reset_threshold(self, channel_id: int):
        st = self._get_state(channel_id)
        st["msg_count"] = 0
        st["threshold"] = random.randint(AUTO_MIN_MSG, AUTO_MAX_MSG)

    # -------------------------------
    # Listener messages
    # -------------------------------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Ignorer bots / DM / messages sans salon
        if message.author.bot or not isinstance(message.channel, discord.TextChannel):
            return

        ch = message.channel
        st = self._get_state(ch.id)

        # Si un drop est déjà actif sur ce salon → on ne prépare pas un nouveau
        if st["active"]:
            return

        # Incrémente le compteur de messages vers le prochain drop auto
        st["msg_count"] += 1
        if st["msg_count"] < st["threshold"]:
            return

        # Seuil atteint → déclenche un drop sur CE message
        await self._spawn_drop(message)

    # -------------------------------
    # Création du drop
    # -------------------------------
    async def _spawn_drop(self, trigger_message: discord.Message):
        ch = trigger_message.channel
        st = self._get_state(ch.id)

        # Armer l'état
        st["active"] = True
        st["message_id"] = trigger_message.id
        st["participants"] = set()

        try:
            # Ajoute la réaction 📦 sous le message du joueur
            await trigger_message.add_reaction(BOX_EMOJI)
        except Exception:
            # Si on ne peut pas réagir (manque de permissions ?), on annule et on replanifie.
            st["active"] = False
            st["message_id"] = None
            self._reset_threshold(ch.id)
            return

        # Attendre la fenêtre de claims
        await asyncio.sleep(CLAIM_WINDOW_SECONDS)

        # Finaliser : figer la liste des participants
        participants: Set[int] = set(st["participants"])

        # Distribuer les loots (selon rareté) — puis construire le récap
        lines = []
        if not participants:
            lines.append("Personne n’a réagi à temps.")
        else:
            for uid in participants:
                # Tirage pondéré par rareté (utils.get_random_item)
                item = get_random_item()
                # sécurité: si None (pool vide), on skip
                if not item:
                    continue
                # Persiste dans l'inventaire
                try:
                    await add_item(uid, item, 1)
                except Exception:
                    # si inventaire KO, au moins afficher dans le récap
                    pass
                # Ligne du récap
                member = trigger_message.guild.get_member(uid)
                mention = member.mention if member else f"<@{uid}>"
                lines.append(f"- {mention} a obtenu {item}")

        # Poster le récap (sans description superflue)
        # Titre demandé : "📦 Ravitaillement récupéré !"
        embed = discord.Embed(
            title="📦 Ravitaillement récupéré !",
            color=discord.Color.gold(),
        )
        if lines:
            embed.add_field(name="\u200b", value="\n".join(lines), inline=False)

        try:
            await ch.send(embed=embed, reference=trigger_message, mention_author=False)
        except Exception:
            # fallback si référence impossible
            await ch.send(embed=embed)

        # Réinitialiser l'état pour le prochain drop
        st["active"] = False
        st["message_id"] = None
        st["participants"] = set()
        self._reset_threshold(ch.id)

    # -------------------------------
    # Collecte des réactions 📦
    # -------------------------------
    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        # On ne garde que 📦
        if str(payload.emoji) != BOX_EMOJI:
            return
        if payload.user_id == getattr(self.bot.user, "id", None):
            return

        channel_id = payload.channel_id
        st = self._get_state(channel_id)

        # Uniquement si un drop est actif ET sur le bon message
        if not st["active"] or not st["message_id"]:
            return
        if payload.message_id != st["message_id"]:
            return

        # On enregistre le participant
        st["participants"].add(payload.user_id)

    # (facultatif) Si quelqu’un retire sa réaction avant la fin : on l’enlève de la liste.
    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        if str(payload.emoji) != BOX_EMOJI:
            return
        channel_id = payload.channel_id
        st = self._get_state(channel_id)
        if not st["active"] or not st["message_id"]:
            return
        if payload.message_id != st["message_id"]:
            return
        try:
            st["participants"].discard(payload.user_id)
        except Exception:
            pass


async def setup(bot: commands.Bot):
    await bot.add_cog(RavitaillementCog(bot))

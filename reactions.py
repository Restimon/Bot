# reaction.py
# Ravitaillement par réaction sur les messages du chat.
# - Compte les messages par salon, déclenche un drop après un seuil ALÉATOIRE (ex. 18–32)
# - Choisit 1 item selon sa rareté
# - Ajoute la RÉACTION = emoji de l'item sur le message d'un membre
# - Fenêtre 30s pour cliquer; les 4 premiers (non-bots) gagnent l'item
# - Envoie un embed "📦 Ravitaillement récupéré" et met à jour l'inventaire

from __future__ import annotations

import asyncio
import random
import time
from typing import Dict, List, Tuple, Optional

import discord
from discord.ext import commands

# --- Dépendances de TON projet ---
from utils import OBJETS  # dict {emoji -> meta}
from storage import get_user_data, inventaire  # inventaire[guild_id][user_id] = list d'emojis
from data import sauvegarder  # persistance

# Si tu as un interrupteur global (optionnel). Sinon, toujours activé.
try:
    from special_supply import is_special_supply_enabled
except Exception:
    def is_special_supply_enabled(guild_id: str) -> bool:
        return True


# ======================
# Réglages faciles à tuner
# ======================

# Seuil de messages aléatoire avant drop
MIN_MSG_THRESHOLD = 18
MAX_MSG_THRESHOLD = 32

# Fenêtre pour "claimer" via la réaction
CLAIM_WINDOW_SEC = 30

# Nombre maximum de gagnants
MAX_WINNERS = 4

# Est-ce que les messages de bot peuvent déclencher un ravitaillement ?
ALLOW_BOTS_TO_TRIGGER = False

# Pondération par rareté (plus le poids est grand, plus c’est fréquent)
RARITY_WEIGHTS = {
    "commun": 100,
    "common": 100,
    "rare": 30,
    "epique": 10,
    "épique": 10,
    "legendary": 2,
    "légendaire": 2,
}

# Exclusion de certains items (ex. utilitaires) si besoin
EXCLUDED_TYPES = set()  # ex: {"utilitaire"}


# ======================
# Helpers liés aux items
# ======================

def _rarity_of(emoji: str) -> str:
    meta = OBJETS.get(emoji) or {}
    r = meta.get("rarete") or meta.get("rarity") or meta.get("tier") or ""
    return str(r).lower().strip()

def _type_of(emoji: str) -> str:
    meta = OBJETS.get(emoji) or {}
    return str(meta.get("type", "")).lower().strip()

def _is_drop_eligible(emoji: str) -> bool:
    """Filtre les items éligibles au ravitaillement (par rareté reconnue + type non exclu)."""
    if emoji not in OBJETS:
        return False
    if _type_of(emoji) in EXCLUDED_TYPES:
        return False
    return _rarity_of(emoji) in RARITY_WEIGHTS

def _weighted_choice_by_rarity(candidates: List[str]) -> str:
    pool: List[Tuple[str, int]] = []
    for e in candidates:
        w = RARITY_WEIGHTS.get(_rarity_of(e), 0)
        if w > 0:
            pool.append((e, w))
    if not pool:
        # fallback total si rien de pondérable
        return random.choice(candidates)
    population, weights = zip(*pool)
    return random.choices(population, weights=weights, k=1)[0]


class ReactionSupply(commands.Cog):
    """
    Ravitaillement par réactions sur les messages de discussion.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # État par salon
        self._counters: Dict[int, int] = {}     # channel_id -> nb de messages vus
        self._thresholds: Dict[int, int] = {}   # channel_id -> prochain seuil aléatoire
        # Drops actifs par message
        self._active_drops: Dict[int, Dict] = {}  # message_id -> info (emoji, guild_id, start, etc.)

    # ----------------
    # Outils internes
    # ----------------
    def _next_threshold(self) -> int:
        return random.randint(MIN_MSG_THRESHOLD, MAX_MSG_THRESHOLD)

    def _ensure_channel_state(self, channel_id: int):
        if channel_id not in self._counters:
            self._counters[channel_id] = 0
        if channel_id not in self._thresholds:
            self._thresholds[channel_id] = self._next_threshold()

    def _pick_drop_item(self) -> Optional[str]:
        """Choisit un item parmi OBJETS selon rareté (pondérée)."""
        candidates = [e for e in OBJETS.keys() if _is_drop_eligible(e)]
        if not candidates:
            # dernier recours : tout l'univers des objets
            candidates = list(OBJETS.keys())
        if not candidates:
            return None
        return _weighted_choice_by_rarity(candidates)

    async def _award_item(self, guild_id: str, user_id: str, emoji: str):
        """Ajoute l’item (emoji) à l’inventaire du joueur puis sauvegarde."""
        user_inv, _, _ = get_user_data(guild_id, user_id)
        user_inv.append(emoji)

        # reflète la mutation dans le dict global inventaire
        if guild_id not in inventaire:
            inventaire[guild_id] = {}
        inventaire[guild_id][user_id] = user_inv

        try:
            sauvegarder()
        except Exception:
            pass

    # --------------
    # Listener chat
    # --------------
    @commands.Cog.listener("on_message")
    async def handle_message_for_reaction_supply(self, message: discord.Message):
        """Déclenche un ravitaillement (via réaction) après un certain nombre de messages aléatoires."""
        # Ignorer DMs / webhooks / système
        if not message.guild or message.webhook_id or message.author.system:
            return
        # Option : pas de déclenchement via messages de bots
        if not ALLOW_BOTS_TO_TRIGGER and message.author.bot:
            return

        guild_id = str(message.guild.id)
        if not is_special_supply_enabled(guild_id):  # si tu veux un switch global
            return

        ch = message.channel
        self._ensure_channel_state(ch.id)

        # Incrémente le compteur pour ce salon
        self._counters[ch.id] += 1

        # Pas encore au seuil ?
        if self._counters[ch.id] < self._thresholds[ch.id]:
            return

        # Réinitialise le seuil pour le prochain drop
        self._counters[ch.id] = 0
        self._thresholds[ch.id] = self._next_threshold()

        # Choisir un item
        emoji = self._pick_drop_item()
        if not emoji:
            return

        # Ajouter la réaction sur CE message (si perms OK)
        try:
            await message.add_reaction(emoji)
        except Exception:
            # pas les permissions / emoji invalide / etc.
            return

        # Mémoriser l'état de ce drop
        self._active_drops[message.id] = {
            "emoji": emoji,
            "guild_id": guild_id,
            "channel_id": ch.id,
            "start": time.time(),
        }

        # Lancer la collecte async
        self.bot.loop.create_task(self._collect_claims_and_award(message))

    async def _collect_claims_and_award(self, message: discord.Message):
        """Après CLAIM_WINDOW_SEC, lit les réactions et prime les 4 premiers (non-bots)."""
        info = self._active_drops.get(message.id)
        if not info:
            return

        emoji = info["emoji"]
        guild_id = info["guild_id"]

        # Attendre la fenêtre de claim
        try:
            await asyncio.sleep(CLAIM_WINDOW_SEC)
        except asyncio.CancelledError:
            return

        # Recharger le message pour avoir les réactions finales
        try:
            message = await message.channel.fetch_message(message.id)
        except Exception:
            self._active_drops.pop(message.id, None)
            return

        # Trouver la bonne réaction
        target_reaction: Optional[discord.Reaction] = None
        for r in message.reactions:
            try:
                if str(r.emoji) == str(emoji):
                    target_reaction = r
                    break
            except Exception:
                pass

        winners: List[discord.Member] = []
        if target_reaction:
            # Récupère les utilisateurs ayant réagi
            try:
                users = await target_reaction.users().flatten()
            except Exception:
                users = []

            # Prend les 4 premiers non-bots (dans l'ordre d'arrivée)
            for u in users:
                if len(winners) >= MAX_WINNERS:
                    break
                if getattr(u, "bot", False):
                    continue
                if isinstance(u, discord.Member):
                    winners.append(u)
                else:
                    # Si c'est un User, tente de le convertir en Member
                    try:
                        m = message.guild.get_member(u.id) or await message.guild.fetch_member(u.id)
                        if m and not m.bot:
                            winners.append(m)
                    except Exception:
                        pass

        # Récompenses et annonce
        if winners:
            for m in winners:
                try:
                    await _safe_award(self._award_item, guild_id, str(m.id), emoji)
                except Exception:
                    pass

            # Embed de résultat
            embed = discord.Embed(
                title="📦 Ravitaillement récupéré",
                description=(
                    f"Le dépôt de **GotValis** contenant {emoji} a été récupéré par :\n\n" +
                    "\n".join(f"• {m.mention}" for m in winners)
                ),
                color=discord.Color.green()
            )
            try:
                await message.channel.send(embed=embed)
            except Exception:
                pass

        # Nettoyage
        self._active_drops.pop(message.id, None)


async def _safe_award(fn, guild_id: str, user_id: str, emoji: str):
    """Petit wrapper au cas où un award plante un joueur sans casser les autres."""
    try:
        await fn(guild_id, user_id, emoji)
    except Exception:
        pass


async def setup(bot: commands.Bot):
    await bot.add_cog(ReactionSupply(bot))

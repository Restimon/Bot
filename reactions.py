# reactions.py
# Helpers pour ajouter des réactions en fonction de la rareté / probabilité d'un item.
# Utilisation simple (ancien système) :
#   from reactions import add_rarity_reaction
#   msg = await interaction.followup.send(embed=embed)
#   await add_rarity_reaction(msg, item_emoji)
#
# Utilisation avancée (avec barre de proba si définie dans OBJETS) :
#   from reactions import add_drop_reactions
#   msg = await interaction.followup.send(embed=embed)
#   await add_drop_reactions(msg, item_emoji)

from __future__ import annotations

import discord
from typing import Dict, List, Optional

# On suppose que utils.py expose ton dictionnaire global OBJETS: Dict[str, dict]
try:
    from utils import OBJETS  # noqa: F401
except Exception:
    # Fallback pour éviter un import error si utils n'est pas chargé au moment de l'import.
    OBJETS: Dict[str, dict] = {}  # type: ignore


# =========
# Réglages
# =========

# Map rareté -> emoji de réaction (ancien système)
RARITY_REACTIONS: Dict[str, str] = {
    "commun": "🟩",
    "common": "🟩",
    "rare": "🟦",
    "epique": "🟪",
    "épique": "🟪",
    "legendary": "🟨",
    "légendaire": "🟨",
}

# Pour la barre de probabilité (optionnelle)
PROB_BAR_SEGMENTS = 5            # nombre de cases dans la jauge
PROB_BAR_FILL_EMOJI = "🟩"
PROB_BAR_EMPTY_EMOJI = "⬜"


# ==================
# Outils d’extraction
# ==================

def get_item_meta(emoji: str) -> Optional[dict]:
    """Retourne la meta d'un item depuis OBJETS[emoji]."""
    if not isinstance(emoji, str):
        return None
    return OBJETS.get(emoji)

def get_rarity(emoji: str) -> Optional[str]:
    """Récupère la rareté depuis plusieurs clés possibles."""
    meta = get_item_meta(emoji)
    if not meta:
        return None
    r = meta.get("rarete") or meta.get("rarity") or meta.get("tier")
    return str(r).lower().strip() if r else None

def get_drop_chance(emoji: str) -> Optional[float]:
    """Récupère une proba (0..1) si tu l'as stockée dans l'item."""
    meta = get_item_meta(emoji)
    if not meta:
        return None
    val = meta.get("drop_rate") or meta.get("chance") or meta.get("prob")
    try:
        f = float(val)
        if 0.0 <= f <= 1.0:
            return f
    except Exception:
        pass
    return None

def make_probability_bar(chance: float) -> List[str]:
    """Construit la liste d'emojis pour afficher une petite jauge."""
    steps = int(round(chance * PROB_BAR_SEGMENTS))
    steps = max(0, min(PROB_BAR_SEGMENTS, steps))
    return [PROB_BAR_FILL_EMOJI] * steps + [PROB_BAR_EMPTY_EMOJI] * (PROB_BAR_SEGMENTS - steps)


# ==================
# Apis de réactions
# ==================

async def add_rarity_reaction(message: discord.Message, item_emoji: str) -> None:
    """
    Ancien système : ajoute 1 réaction basée sur la rareté (commun/rare/épique/légendaire).
    - Ignore silencieusement si le message est éphémère ou si l'item est inconnu.
    """
    if not isinstance(message, discord.Message):
        return
    # pas de réaction possible sur les messages éphémères
    try:
        if getattr(message, "flags", None) and message.flags.ephemeral:
            return
    except Exception:
        pass

    rarity = get_rarity(item_emoji)
    if not rarity:
        return
    react = RARITY_REACTIONS.get(rarity)
    if not react:
        return

    try:
        await message.add_reaction(react)
    except Exception:
        # permissions manquantes / emoji externe non autorisé / etc.
        pass


async def add_drop_reactions(message: discord.Message, item_emoji: str, with_probability_bar: bool = True) -> None:
    """
    Système avancé : ajoute la réaction de rareté + éventuellement une barre de probabilité.
    - with_probability_bar=True => tente d'ajouter une jauge si chance présente dans OBJETS.
    - Ignore silencieusement si le message est éphémère ou si l'item est inconnu.
    """
    if not isinstance(message, discord.Message):
        return
    try:
        if getattr(message, "flags", None) and message.flags.ephemeral:
            return
    except Exception:
        pass

    # 1) Rareté
    await add_rarity_reaction(message, item_emoji)

    # 2) Barre de proba (optionnelle)
    if with_probability_bar:
        chance = get_drop_chance(item_emoji)
        if isinstance(chance, float):
            for e in make_probability_bar(chance):
                try:
                    await message.add_reaction(e)
                except Exception:
                    # On ignore les erreurs individuellement pour ne pas interrompre la série
                    pass


# =====================
# Helpers d’intégration
# =====================

async def send_with_reactions(
    interaction: discord.Interaction,
    *,
    content: Optional[str] = None,
    embed: Optional[discord.Embed] = None,
    item_emoji: Optional[str] = None,
    use_followup: bool = True,
    probability_bar: bool = True,
) -> Optional[discord.Message]:
    """
    Envoie un message (content ou embed) via Interaction, puis ajoute les réactions liées à l'item.
    - use_followup=True : utilise interaction.followup.send (après defer)
    - use_followup=False : utilise interaction.response.send_message + original_response()
    Retourne l'objet Message (ou None en cas d'échec).
    """
    msg: Optional[discord.Message] = None

    try:
        if use_followup:
            # Nécessite un defer préalable
            msg = await interaction.followup.send(content=content, embed=embed)
        else:
            await interaction.response.send_message(content=content, embed=embed)
            msg = await interaction.original_response()
    except Exception:
        return None

    if msg and item_emoji:
        try:
            await add_drop_reactions(msg, item_emoji, with_probability_bar=probability_bar)
        except Exception:
            pass

    return msg

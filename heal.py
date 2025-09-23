# logic/heal.py
from __future__ import annotations

import json
from typing import Dict, Optional, Tuple

import discord

# DB soins / stats
from stats_db import heal_user, get_hp
try:
    from stats_db import add_heal_stat  # optionnel
except Exception:
    async def add_heal_stat(*args, **kwargs): return None

# Effets pour la régénération
from effects_db import add_or_refresh_effect

# Inventaire
from inventory_db import get_item_qty, remove_item

# Passifs (tous optionnels — stubs si absents)
try:
    from passifs import trigger as passifs_trigger
except Exception:
    async def passifs_trigger(*args, **kwargs): return {}

# Catalogue d’objets
try:
    from utils import OBJETS  # type: ignore
except Exception:
    OBJETS = {}


# ─────────────────────────────────────────────────────────
# Helpers inventaire / objets
# ─────────────────────────────────────────────────────────
async def _consume_item(user_id: int, emoji: str) -> bool:
    try:
        qty = await get_item_qty(user_id, emoji)
        if int(qty or 0) <= 0:
            return False
        return await remove_item(user_id, emoji, 1)
    except Exception:
        return False

def _obj_info(emoji: str) -> Optional[Dict]:
    info = OBJETS.get(emoji)
    return dict(info) if isinstance(info, dict) else None


# ─────────────────────────────────────────────────────────
# Embeds
# ─────────────────────────────────────────────────────────
def _build_heal_embed(
    healer: discord.Member,
    target: discord.Member,
    emoji: str,
    healed: int,
    hp_before: int,
    hp_after: int
) -> discord.Embed:
    e = discord.Embed(title=f"{emoji} Soin", color=discord.Color.green())
    lines = [
        f"{healer.mention} soigne {target.mention} avec {emoji} pour **{healed} PV**.",
        f"❤️ **{hp_before}** → **{hp_after}** PV",
    ]
    e.description = "\n".join(lines)
    return e

def _build_regen_embed(
    applier: discord.Member,
    target: discord.Member,
    emoji: str,
    value: int,
    interval: int,
    duration: int
) -> discord.Embed:
    e = discord.Embed(
        title="💕 Régénération posée",
        description=(
            f"{applier.mention} applique **{emoji}** sur {target.mention} : "
            f"+**{value} PV** toutes les **{max(1, interval)}s** pendant **{max(1, duration)}s**."
        ),
        color=discord.Color.blurple()
    )
    return e


# ─────────────────────────────────────────────────────────
# Actions
# ─────────────────────────────────────────────────────────
async def apply_direct_heal(
    inter: discord.Interaction,
    healer: discord.Member,
    target: discord.Member,
    emoji: str,
    info: Dict,
) -> Tuple[discord.Embed, Dict]:
    """
    Soins instantanés (OBJET type="soin")
    """
    amount = int(info.get("soin", info.get("value", info.get("valeur", 0))) or 0)
    amount = max(0, amount)

    hp_before, _mx = await get_hp(target.id)
    healed = await heal_user(healer.id, target.id, amount)
    hp_after, _mx2 = await get_hp(target.id)

    # passifs post-soin (optionnel)
    try:
        await passifs_trigger("on_heal", healer_id=healer.id, target_id=target.id, healed=healed)
    except Exception:
        pass
    if healed > 0:
        await add_heal_stat(healer.id, int(healed))

    embed = _build_heal_embed(healer, target, emoji, healed, hp_before, hp_after)
    return embed, {"healed": healed}


async def apply_regen(
    inter: discord.Interaction,
    applier: discord.Member,
    target: discord.Member,
    emoji: str,
    info: Dict,
) -> Tuple[discord.Embed, Dict]:
    """
    Régénération (OBJET type="regen") → effet à ticks
    """
    value = int(info.get("valeur", info.get("value", 0)) or 0)
    interval = int(info.get("intervalle", info.get("interval", 60)) or 60)
    duration = int(info.get("duree", info.get("duration", 300)) or 300)

    # passifs : pré-application (immunité ou blocage)
    try:
        pre = await passifs_trigger("on_effect_pre_apply", user_id=target.id, eff_type="regen") or {}
        if pre.get("blocked"):
            e = discord.Embed(
                title="⛔ Effet bloqué",
                description=pre.get("reason", "Impossible d’appliquer la régénération."),
                color=discord.Color.red()
            )
            return e, {"applied": False}
    except Exception:
        pass

    ok = await add_or_refresh_effect(
        user_id=target.id, eff_type="regen", value=float(value),
        duration=duration, interval=interval,
        source_id=applier.id, meta_json=json.dumps({"from": applier.id, "emoji": emoji})
    )
    if not ok:
        e = discord.Embed(
            title="⛔ Effet refusé",
            description="La régénération n’a pas pu être appliquée (règle spéciale / immunité).",
            color=discord.Color.red()
        )
        return e, {"applied": False}

    embed = _build_regen_embed(applier, target, emoji, value, interval, duration)
    return embed, {"applied": True, "value": value, "interval": interval, "duration": duration}


# ─────────────────────────────────────────────────────────
# Sélecteur générique pour /heal
# ─────────────────────────────────────────────────────────
async def select_and_apply(
    inter: discord.Interaction,
    emoji: str,
    cible: Optional[discord.Member] = None,
) -> Tuple[discord.Embed, Dict]:
    """
    Déduit le type de l’objet (soin / regen), consomme l’item puis applique.
    - cible par défaut = soi-même
    """
    target = cible or inter.user

    info = _obj_info(emoji)
    if not info:
        raise ValueError("Objet inconnu.")
    typ = str(info.get("type", ""))

    if typ not in ("soin", "regen"):
        raise ValueError("Objet invalide : il faut un **objet de soin**.")

    # Consommer l’objet
    if not await _consume_item(inter.user.id, emoji):
        raise RuntimeError(f"Tu n’as pas **{emoji}** dans ton inventaire.")

    # Appliquer
    if typ == "soin":
        return await apply_direct_heal(inter, inter.user, target, emoji, info)
    else:
        return await apply_regen(inter, inter.user, target, emoji, info)

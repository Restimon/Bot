# logic/use.py
from __future__ import annotations

import json
import random
from typing import Dict, Optional, Tuple

import discord

# ── Inventaire
from inventory_db import get_item_qty, remove_item, add_item

# ── Effets (buffs & nettoyage)
from effects_db import add_or_refresh_effect, remove_effect, has_effect

# ── Bouclier persistant (PB)
try:
    from shields_db import add_shield, get_shield, get_max_shield
except Exception:
    async def add_shield(uid: int, delta: int, cap_to_max: bool = True) -> int:  # type: ignore
        return 0
    async def get_shield(uid: int) -> int:  # type: ignore
        return 0
    async def get_max_shield(uid: int) -> int:  # type: ignore
        return 50

# ── Stats (pour afficher PV actuels quand utile)
try:
    from stats_db import get_hp
except Exception:
    async def get_hp(uid: int) -> Tuple[int, int]:  # type: ignore
        return (100, 100)

# ── Passifs (hooks optionnels)
try:
    from passifs import trigger as passifs_trigger
except Exception:
    async def passifs_trigger(*args, **kwargs): return {}

# ── Catalogue d’objets & utilitaires
try:
    from utils import OBJETS, get_random_item  # type: ignore
except Exception:
    OBJETS = {}
    def get_random_item(debug: bool = False):
        return random.choice(["🍀", "❄️", "🧪", "🩹", "💊"])


# ─────────────────────────────────────────────────────────
# Helpers communs
# ─────────────────────────────────────────────────────────
def _obj_info(emoji: str) -> Optional[Dict]:
    info = OBJETS.get(emoji)
    return dict(info) if isinstance(info, dict) else None

async def _consume_item(user_id: int, emoji: str) -> bool:
    try:
        qty = await get_item_qty(user_id, emoji)
        if int(qty or 0) <= 0:
            return False
        return await remove_item(user_id, emoji, 1)
    except Exception:
        return False

def _ok_embed(title: str, desc: str) -> discord.Embed:
    return discord.Embed(title=title, description=desc, color=discord.Color.green())

def _warn_embed(title: str, desc: str) -> discord.Embed:
    return discord.Embed(title=title, description=desc, color=discord.Color.orange())

def _err_embed(title: str, desc: str) -> discord.Embed:
    return discord.Embed(title=title, description=desc, color=discord.Color.red())


# ─────────────────────────────────────────────────────────
# Actions concrètes par type d’objet
# ─────────────────────────────────────────────────────────

# ——— BOUCLIER ———
async def apply_shield(
    inter: discord.Interaction,
    applier: discord.Member,
    target: discord.Member,
    emoji: str,
    info: Dict
) -> Tuple[discord.Embed, Dict]:
    val = int(info.get("valeur", info.get("value", 0)) or 0)
    if val <= 0:
        return _warn_embed("Bouclier", "Valeur de bouclier invalide."), {"applied": False}

    # hook passif pré-application (ex: cap temporaire, blocage)
    try:
        pre = await passifs_trigger("on_effect_pre_apply", user_id=target.id, eff_type="bouclier") or {}
        if pre.get("blocked"):
            return _err_embed("⛔ Bloqué", pre.get("reason", "Impossible d’appliquer le bouclier.")), {"applied": False}
    except Exception:
        pass

    new_pb = await add_shield(target.id, val, cap_to_max=True)
    mx_pb  = await get_max_shield(target.id)
    hp, mx = await get_hp(target.id)

    e = discord.Embed(
        title=f"{emoji} Bouclier",
        description=(
            f"{applier.mention} confère un **bouclier** à {target.mention} :\n"
            f"🛡 **{new_pb}/{mx_pb} PB** | ❤️ **{hp}/{mx} PV**"
        ),
        color=discord.Color.blurple()
    )
    return e, {"applied": True, "new_pb": new_pb}


# ——— VACCIN (cleanse) ———
async def apply_vaccine(
    inter: discord.Interaction,
    applier: discord.Member,
    target: discord.Member,
    emoji: str,
    info: Dict
) -> Tuple[discord.Embed, Dict]:
    # liste d’états négatifs à retirer
    negatives = ("poison", "infection", "virus", "brulure")
    removed = []
    for eff in negatives:
        try:
            if await has_effect(target.id, eff):
                await remove_effect(target.id, eff)
                removed.append(eff)
        except Exception:
            continue

    if not removed:
        e = _warn_embed("Vaccin", f"Aucun effet négatif détecté sur {target.mention}.")
    else:
        label = ", ".join(f"**{t}**" for t in removed)
        e = _ok_embed("💉 Vaccin appliqué", f"{applier.mention} retire {label} sur {target.mention}.")
    return e, {"removed": removed}


# ——— BUFFS (esquive+ / réduction / immunité) ———
async def apply_buff(
    inter: discord.Interaction,
    applier: discord.Member,
    target: discord.Member,
    emoji: str,
    info: Dict,
    eff_type: str
) -> Tuple[discord.Embed, Dict]:
    value    = float(info.get("valeur", info.get("value", 0)) or 0)
    duration = int(info.get("duree", info.get("duration", 3600)) or 3600)

    # hook passif pré-application
    try:
        pre = await passifs_trigger("on_effect_pre_apply", user_id=target.id, eff_type=str(eff_type)) or {}
        if pre.get("blocked"):
            return _err_embed("⛔ Bloqué", pre.get("reason", "Impossible d’appliquer cet effet.")), {"applied": False}
    except Exception:
        pass

    ok = await add_or_refresh_effect(
        user_id=target.id,
        eff_type=str(eff_type),
        value=float(value),
        duration=int(duration),
        interval=0,
        source_id=applier.id,
        meta_json=json.dumps({"from": applier.id, "emoji": emoji})
    )
    if not ok:
        return _err_embed("⛔ Refusé", "L’effet n’a pas pu être appliqué."), {"applied": False}

    names = {"esquive+": "👟 Esquive+", "reduction": "🪖 Réduction de dégâts", "immunite": "⭐ Immunité"}
    desc = f"{applier.mention} applique **{emoji}** sur {target.mention}."
    e = discord.Embed(title=names.get(eff_type, "Buff"), description=desc, color=discord.Color.teal())
    return e, {"applied": True, "value": value, "duration": duration}


# ——— MYSTERY BOX ———
async def open_box(
    inter: discord.Interaction,
    user: discord.Member,
    emoji: str
) -> Tuple[discord.Embed, Dict]:
    got = get_random_item(debug=False)
    await add_item(user.id, got, 1)
    e = discord.Embed(
        title="📦 Box ouverte",
        description=f"{user.mention} obtient **{got}** !",
        color=discord.Color.gold()
    )
    # hook passif post-ouverture (bonus ?)
    try:
        post = await passifs_trigger("on_box_open", user_id=user.id) or {}
    except Exception:
        post = {}
    if int(post.get("extra_items", 0) or 0) > 0:
        extra = get_random_item(debug=False)
        await add_item(user.id, extra, 1)
        e.description += f"\n🎁 Bonus: **{extra}**"
    return e, {"item": got}


# ——— VOL ———
async def try_theft(
    inter: discord.Interaction,
    thief: discord.Member,
    target: Optional[discord.Member]
) -> Tuple[discord.Embed, Dict]:
    if target:
        try:
            res = await passifs_trigger("on_theft_attempt", attacker_id=thief.id, target_id=target.id) or {}
        except Exception:
            res = {}
        if res.get("blocked"):
            return _warn_embed("🛡 Protégé", f"{target.mention} est **intouchable** (anti-vol)."), {"stolen": False}

    success = (random.random() < 0.25)
    if success:
        got = get_random_item(debug=False)
        await add_item(thief.id, got, 1)
        e = discord.Embed(title="🕵️ Vol", description=f"Vol réussi ! Tu obtiens **{got}**.", color=discord.Color.dark_grey())
        return e, {"stolen": True, "item": got}
    else:
        e = discord.Embed(title="🕵️ Vol", description="Vol raté...", color=discord.Color.dark_grey())
        return e, {"stolen": False}


# ─────────────────────────────────────────────────────────
# Sélecteur générique pour /use
# ─────────────────────────────────────────────────────────
async def select_and_apply(
    inter: discord.Interaction,
    emoji: str,
    cible: Optional[discord.Member] = None,
) -> Tuple[discord.Embed, Dict]:
    """
    Détermine l’action selon OBJETS[emoji]['type'] puis applique.
    Consomme l’objet (sauf si un passif renvoie dont_consume).
    Redirige vers fight/heal si objet offensif ou de soin.
    """
    info = _obj_info(emoji)
    if not info:
        raise ValueError("Objet inconnu.")
    typ = str(info.get("type", ""))

    # redirections
    if typ in ("attaque", "attaque_chaine"):
        if not isinstance(cible, discord.Member):
            raise RuntimeError("Il faut une **cible** pour attaquer.")
        # déléguer à logic.fight si dispo
        try:
            from logic.fight import apply_attack, apply_chain_attack  # type: ignore
        except Exception:
            raise RuntimeError("La logique d’attaque n’est pas disponible (logic/fight.py).")
        # consommer
        if not await _consume_item(inter.user.id, emoji):
            raise RuntimeError(f"Tu n’as pas **{emoji}** dans ton inventaire.")
        if typ == "attaque":
            embed, meta = await apply_attack(inter, inter.user, cible, emoji, info)
        else:
            embed, meta = await apply_chain_attack(inter, inter.user, cible, emoji, info)

    elif typ in ("soin", "regen"):
        # déléguer à logic.heal
        try:
            from logic.heal import select_and_apply as heal_select  # type: ignore
        except Exception:
            raise RuntimeError("La logique de soin n’est pas disponible (logic/heal.py).")
        embed, meta = await heal_select(inter, emoji, cible)

    else:
        # pour les utilitaires, consommer ici
        if not await _consume_item(inter.user.id, emoji):
            raise RuntimeError(f"Tu n’as pas **{emoji}** dans ton inventaire.")

        target = cible or inter.user

        if typ == "bouclier":
            embed, meta = await apply_shield(inter, inter.user, target, emoji, info)

        elif typ == "vaccin":
            embed, meta = await apply_vaccine(inter, inter.user, target, emoji, info)

        elif typ == "mysterybox":
            embed, meta = await open_box(inter, inter.user, emoji)

        elif typ == "vol":
            embed, meta = await try_theft(inter, inter.user, target if isinstance(target, discord.Member) else None)

        elif typ in ("esquive+", "reduction", "immunite"):
            embed, meta = await apply_buff(inter, inter.user, target, emoji, info, typ)

        else:
            embed = _warn_embed("Objet non géré", f"{emoji} (**{typ}**) n’a pas de logique dédiée pour le moment.")
            meta = {"applied": False}

    # hook post-usage (ex: “dont_consume”)
    try:
        post = await passifs_trigger("on_use_item", user_id=inter.user.id, item_emoji=emoji, item_type=typ) or {}
        if post.get("dont_consume"):
            try:
                await add_item(inter.user.id, emoji, 1)
            except Exception:
                pass
    except Exception:
        pass

    return embed, meta

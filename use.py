# logic/use.py
from __future__ import annotations

import json
import random
from typing import Dict, Optional, Tuple, List

import discord

# ── Inventaire
from inventory_db import (
    get_item_qty,
    remove_item,
    add_item,
    get_all_items,
    transfer_item,  # si implémenté de façon atomique
)

# ── Économie (coins pour la Box)
from economy_db import add_balance

# ── Effets (buffs & nettoyage)
from effects_db import add_or_refresh_effect, remove_effect, has_effect

# ── Passifs (hooks optionnels)
try:
    from passifs import trigger as passifs_trigger
except Exception:
    async def passifs_trigger(*args, **kwargs):  # type: ignore
        return {}

# ── Catalogue d’objets & utilitaires
try:
    from utils import OBJETS, get_random_item, get_evade_chance  # type: ignore
except Exception:
    OBJETS = {}
    def get_random_item(debug: bool = False):
        return random.choice(["🍀", "❄️", "🧪", "🩹", "💊"])
    def get_evade_chance(gid: str, uid: str) -> float:
        return 0.04  # 4% fallback


# ─────────────────────────────────────────────────────────
# Helpers communs
# ─────────────────────────────────────────────────────────
def _obj_info(emoji: str) -> Optional[Dict]:
    info = OBJETS.get(emoji)
    return dict(info) if isinstance(info, dict) else None

def _obj_gif(emoji: str) -> Optional[str]:
    """Récupère un GIF pertinent depuis utils. gif_heal pour soins/vaccin, sinon gif/gif_attack."""
    data = OBJETS.get(emoji, {})
    typ = str(data.get("type", ""))
    if typ in ("soin", "regen") or emoji in ("💉",):
        return data.get("gif_heal") or data.get("gif")
    return data.get("gif") or data.get("gif_attack")

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
# Mystery Box — pool pondérée (26 - rarete) + option Coins
# ─────────────────────────────────────────────────────────
def _weighted_pool_for_box(exclude_box: bool = True) -> List[str]:
    pool: List[str] = []
    for emoji, data in OBJETS.items():
        if exclude_box and emoji == "📦":
            continue
        r = int(data.get("rarete", 25))
        w = 26 - r
        if w > 0:
            pool.extend([emoji] * w)
    # coins “pseudo-item” (poids ≈ 14 ; équiv. rarete ~12)
    pool.extend(["💰COINS"] * 14)
    return pool


# ─────────────────────────────────────────────────────────
# Actions concrètes par type d’objet
# ─────────────────────────────────────────────────────────

# ——— VACCIN (cleanse) ———
async def apply_vaccine(
    inter: discord.Interaction,
    applier: discord.Member,
    target: discord.Member,
    emoji: str,
    info: Dict
) -> Tuple[discord.Embed, Dict]:
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
    gif = _obj_gif(emoji)
    if gif:
        e.set_image(url=gif)
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
    gif = _obj_gif(emoji)
    if gif:
        e.set_image(url=gif)
    return e, {"applied": True, "value": value, "duration": duration}

# ——— MYSTERY BOX (3 récompenses, items pondérés OU coins) ———
async def open_box(
    inter: discord.Interaction,
    user: discord.Member,
    emoji: str
) -> Tuple[discord.Embed, Dict]:
    pool = _weighted_pool_for_box(exclude_box=True)
    rewards: List[str] = []
    coins_total = 0

    for _ in range(3):
        if not pool:
            break
        pick = random.choice(pool)
        if pick == "💰COINS":
            amt = random.randint(15, 25)
            await add_balance(user.id, amt, reason="mysterybox")
            coins_total += amt
            rewards.append(f"💰 +{amt} GotCoins")
        else:
            await add_item(user.id, pick, 1)
            rewards.append(f"{pick} +1")

    desc = "\n".join(f"• {r}" for r in rewards) if rewards else "—"
    e = discord.Embed(
        title="📦 Box ouverte",
        description=f"{user.mention} reçoit :\n{desc}",
        color=discord.Color.gold()
    )
    gif = _obj_gif(emoji)
    if gif:
        e.set_image(url=gif)

    # Hook passif post-ouverture (bonus éventuel)
    try:
        post = await passifs_trigger("on_box_open", user_id=user.id) or {}
        extra_n = int(post.get("extra_items", 0) or 0)
        for _ in range(max(0, extra_n)):
            pick = random.choice(pool) if pool else None
            if not pick:
                break
            if pick == "💰COINS":
                amt = random.randint(15, 25)
                await add_balance(user.id, amt, reason="mysterybox_bonus")
                e.description += f"\n🎁 Bonus: 💰 +{amt} GotCoins"
            else:
                await add_item(user.id, pick, 1)
                e.description += f"\n🎁 Bonus: {pick} +1"
    except Exception:
        pass

    return e, {"rewards": rewards, "coins_total": coins_total}

# ——— VOL (réel, avec esquive et transfert DB) ———
async def try_theft(
    inter: discord.Interaction,
    thief: discord.Member,
    target: Optional[discord.Member]
) -> Tuple[discord.Embed, Dict]:
    # validations
    if target is None or target.bot or target.id == thief.id:
        return _warn_embed("🕵️ Vol", "Choisis une **cible valide** (humaine, différente de toi)."), {"stolen": False}

    # passif “anti-vol” éventuel
    try:
        res = await passifs_trigger("on_theft_attempt", attacker_id=thief.id, target_id=target.id) or {}
        if res.get("blocked"):
            return _warn_embed("🛡 Protégé", f"{target.mention} est **intouchable** (anti-vol)."), {"stolen": False}
    except Exception:
        pass

    # esquive (4% base, modifiable par buffs/passifs)
    evade = float(get_evade_chance(str(inter.guild_id), str(target.id)))
    if random.random() < max(0.0, min(0.95, evade)):
        e = _warn_embed("🕵️ Vol", f"{target.mention} **esquive** ta tentative ({int(evade*100)}%).")
        gif = _obj_gif("🔍")
        if gif:
            e.set_image(url=gif)
        return e, {"stolen": False}

    # sac pondéré par quantités de la cible
    inv = await get_all_items(target.id)  # [(emoji, qty)]
    bag: List[str] = []
    for emoji, qty in inv:
        q = int(qty or 0)
        if q > 0:
            bag.extend([emoji] * q)

    if not bag:
        e = _warn_embed("🕵️ Vol", f"{target.mention} n'a **rien** à voler.")
        gif = _obj_gif("🔍")
        if gif:
            e.set_image(url=gif)
        return e, {"stolen": False}

    stolen = random.choice(bag)

    # transfert réel (préférer transfer_item si atomique)
    ok = await transfer_item(target.id, thief.id, stolen, 1)
    if not ok:
        # fallback sécurisé : re-vérifier le stock, remove + add
        qty_left = await get_item_qty(target.id, stolen)
        if qty_left <= 0 or not await remove_item(target.id, stolen, 1):
            e = _err_embed("🕵️ Vol", "Le transfert a échoué.")
            gif = _obj_gif("🔍")
            if gif:
                e.set_image(url=gif)
            return e, {"stolen": False}
        await add_item(thief.id, stolen, 1)

    e = discord.Embed(
        title="🕵️ Vol",
        description=f"Vol réussi ! Tu dérobes **{stolen}** à {target.mention}.",
        color=discord.Color.dark_grey()
    )
    gif = _obj_gif("🔍")
    if gif:
        e.set_image(url=gif)
    return e, {"stolen": True, "item": stolen, "from": target.id}


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

    # redirections (attaque/soin utilisent leurs modules)
    if typ in ("attaque", "attaque_chaine"):
        if not isinstance(cible, discord.Member):
            raise RuntimeError("Il faut une **cible** pour attaquer.")
        try:
            from logic.fight import apply_attack, apply_chain_attack  # type: ignore
        except Exception:
            raise RuntimeError("La logique d’attaque n’est pas disponible (logic/fight.py).")
        if not await _consume_item(inter.user.id, emoji):
            raise RuntimeError(f"Tu n’as pas **{emoji}** dans ton inventaire.")
        if typ == "attaque":
            embed, meta = await apply_attack(inter, inter.user, cible, emoji, info)
        else:
            embed, meta = await apply_chain_attack(inter, inter.user, cible, emoji, info)

    elif typ in ("soin", "regen"):
        try:
            from logic.heal import select_and_apply as heal_select  # type: ignore
        except Exception:
            raise RuntimeError("La logique de soin n’est pas disponible (logic/heal.py).")
        # heal module gère la conso
        embed, meta = await heal_select(inter, emoji, cible)

    else:
        # utilitaires : consommer ici
        if not await _consume_item(inter.user.id, emoji):
            raise RuntimeError(f"Tu n’as pas **{emoji}** dans ton inventaire.")

        target = cible or inter.user

        if typ == "vaccin":
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

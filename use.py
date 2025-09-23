from __future__ import annotations

import json
import random
from typing import Dict, Optional, Tuple, List

import discord

# Inventaire
from inventory_db import (
    get_item_qty, remove_item, add_item,
    get_all_items, transfer_item,
)

# Économie (coins pour la Box)
from economy_db import add_balance

# Effets (buffs & nettoyage)
from effects_db import add_or_refresh_effect, remove_effect, has_effect

# Bouclier persistant (PB)
try:
    from shields_db import add_shield, get_shield, get_max_shield
except Exception:
    async def add_shield(uid: int, delta: int, cap_to_max: bool = True) -> int:  # type: ignore
        return 0
    async def get_shield(uid: int) -> int:  # type: ignore
        return 0
    async def get_max_shield(uid: int) -> int:  # type: ignore
        return 50

# Stats (pour afficher PV actuels)
try:
    from stats_db import get_hp
except Exception:
    async def get_hp(uid: int) -> Tuple[int, int]:  # type: ignore
        return (100, 100)

# Passifs (hooks optionnels)
try:
    from passifs import trigger as passifs_trigger
except Exception:
    async def passifs_trigger(*args, **kwargs): return {}

# Catalogue & utilitaires
try:
    from utils import OBJETS, get_random_item, get_evade_chance  # type: ignore
except Exception:
    OBJETS = {}
    def get_random_item(debug: bool = False):
        return random.choice(["🍀", "❄️", "🧪", "🩹", "💊"])
    def get_evade_chance(gid: str, uid: str) -> float:
        return 0.04  # 4% fallback

# ─── helpers ─────────────────────────────────────────────
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

def _ok(title: str, desc: str) -> discord.Embed:
    return discord.Embed(title=title, description=desc, color=discord.Color.green())

def _warn(title: str, desc: str) -> discord.Embed:
    return discord.Embed(title=title, description=desc, color=discord.Color.orange())

def _err(title: str, desc: str) -> discord.Embed:
    return discord.Embed(title=title, description=desc, color=discord.Color.red())

# ─── Mystery Box (3 rewards, pondérées + coins) ──────────
def _weighted_pool_for_box(exclude_box: bool = True) -> List[str]:
    pool: List[str] = []
    for emoji, data in OBJETS.items():
        if exclude_box and emoji == "📦":
            continue
        r = int(data.get("rarete", 25))
        w = 26 - r
        if w > 0:
            pool.extend([emoji] * w)
    pool.extend(["💰COINS"] * 14)  # poids ~ rarete 12
    return pool

async def open_box(inter: discord.Interaction, user: discord.Member, emoji: str) -> Tuple[discord.Embed, Dict]:
    pool = _weighted_pool_for_box(exclude_box=True)
    rewards: List[str] = []
    for _ in range(3):
        if not pool:
            break
        pick = random.choice(pool)
        if pick == "💰COINS":
            amt = random.randint(15, 25)
            await add_balance(user.id, amt, reason="mysterybox")
            rewards.append(f"💰 +{amt} GotCoins")
        else:
            await add_item(user.id, pick, 1)
            rewards.append(f"{pick} +1")

    desc = "\n".join(f"• {r}" for r in rewards) if rewards else "—"
    e = discord.Embed(title="📦 Box ouverte", description=f"{user.mention} reçoit :\n{desc}", color=discord.Color.gold())

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

    return e, {"rewards": rewards}

# ─── Vol (vrai retrait chez la cible) ────────────────────
async def try_theft(inter: discord.Interaction, thief: discord.Member, target: Optional[discord.Member]) -> Tuple[discord.Embed, Dict]:
    if target is None or target.bot or target.id == thief.id:
        return _warn("🕵️ Vol", "Choisis une **cible valide** (humaine, différente de toi)."), {"stolen": False}

    try:
        res = await passifs_trigger("on_theft_attempt", attacker_id=thief.id, target_id=target.id) or {}
        if res.get("blocked"):
            return _warn("🛡 Protégé", f"{target.mention} est **intouchable** (anti-vol)."), {"stolen": False}
    except Exception:
        pass

    evade = float(get_evade_chance(str(inter.guild_id), str(target.id)))
    if random.random() < max(0.0, min(0.95, evade)):
        return _warn("🕵️ Vol", f"{target.mention} **esquive** ta tentative ({int(evade*100)}%)."), {"stolen": False}

    inv = await get_all_items(target.id)  # [(emoji, qty)]
    bag: List[str] = []
    for emoji, qty in inv:
        q = int(qty or 0)
        if q > 0:
            bag.extend([emoji] * q)

    if not bag:
        return _warn("🕵️ Vol", f"{target.mention} n'a **rien** à voler."), {"stolen": False}

    stolen = random.choice(bag)

    ok = await transfer_item(target.id, thief.id, stolen, 1)
    if not ok:
        # fallback ultra-sécurisé : recheck + remove/add
        q = await get_item_qty(target.id, stolen)
        if q <= 0:
            return _warn("🕵️ Vol", f"{target.mention} n’a **plus** cet objet."), {"stolen": False}
        if not await remove_item(target.id, stolen, 1):
            return _err("🕵️ Vol", "Le transfert a échoué."), {"stolen": False}
        await add_item(thief.id, stolen, 1)

    e = discord.Embed(title="🕵️ Vol", description=f"Vol réussi ! Tu dérobes **{stolen}** à {target.mention}.", color=discord.Color.dark_grey())
    return e, {"stolen": True, "item": stolen, "from": target.id}

# ─── Buffs / Vaccin / Bouclier ───────────────────────────
async def apply_vaccine(inter: discord.Interaction, applier: discord.Member, target: discord.Member, emoji: str, info: Dict) -> Tuple[discord.Embed, Dict]:
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
        e = _warn("Vaccin", f"Aucun effet négatif détecté sur {target.mention}.")
    else:
        label = ", ".join(f"**{t}**" for t in removed)
        e = _ok("💉 Vaccin appliqué", f"{applier.mention} retire {label} sur {target.mention}.")
    return e, {"removed": removed}

async def apply_shield(inter: discord.Interaction, applier: discord.Member, target: discord.Member, emoji: str, info: Dict) -> Tuple[discord.Embed, Dict]:
    val = int(info.get("valeur", info.get("value", 0)) or 0)
    if val <= 0:
        return _warn("Bouclier", "Valeur de bouclier invalide."), {"applied": False}
    try:
        pre = await passifs_trigger("on_effect_pre_apply", user_id=target.id, eff_type="bouclier") or {}
        if pre.get("blocked"):
            return _err("⛔ Bloqué", pre.get("reason", "Impossible d’appliquer le bouclier.")), {"applied": False}
    except Exception:
        pass
    new_pb = await add_shield(target.id, val, cap_to_max=True)
    mx_pb  = await get_max_shield(target.id)
    hp, mx = await get_hp(target.id)
    e = discord.Embed(
        title=f"{emoji} Bouclier",
        description=f"{applier.mention} confère un **bouclier** à {target.mention} :\n🛡 **{new_pb}/{mx_pb} PB** | ❤️ **{hp}/{mx} PV**",
        color=discord.Color.blurple()
    )
    return e, {"applied": True, "new_pb": new_pb}

async def apply_buff(inter: discord.Interaction, applier: discord.Member, target: discord.Member, emoji: str, info: Dict, eff_type: str) -> Tuple[discord.Embed, Dict]:
    value    = float(info.get("valeur", info.get("value", 0)) or 0)
    duration = int(info.get("duree", info.get("duration", 3600)) or 3600)
    try:
        pre = await passifs_trigger("on_effect_pre_apply", user_id=target.id, eff_type=str(eff_type)) or {}
        if pre.get("blocked"):
            return _err("⛔ Bloqué", pre.get("reason", "Impossible d’appliquer cet effet.")), {"applied": False}
    except Exception:
        pass
    ok = await add_or_refresh_effect(
        user_id=target.id, eff_type=str(eff_type), value=float(value),
        duration=int(duration), interval=0, source_id=applier.id,
        meta_json=json.dumps({"from": applier.id, "emoji": emoji})
    )
    if not ok:
        return _err("⛔ Refusé", "L’effet n’a pas pu être appliqué."), {"applied": False}
    names = {"esquive+": "👟 Esquive+", "reduction": "🪖 Réduction de dégâts", "immunite": "⭐ Immunité"}
    e = discord.Embed(title=names.get(eff_type, "Buff"), description=f"{applier.mention} applique **{emoji}** sur {target.mention}.", color=discord.Color.teal())
    return e, {"applied": True, "value": value, "duration": duration}

# ─── Sélecteur générique pour /use ───────────────────────
async def select_and_apply(inter: discord.Interaction, emoji: str, cible: Optional[discord.Member] = None) -> Tuple[discord.Embed, Dict]:
    info = _obj_info(emoji)
    if not info:
        raise ValueError("Objet inconnu.")
    typ = str(info.get("type", ""))

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
            return await apply_attack(inter, inter.user, cible, emoji, info)
        return await apply_chain_attack(inter, inter.user, cible, emoji, info)

    elif typ in ("soin", "regen"):
        try:
            from logic.heal import select_and_apply as heal_select  # type: ignore
        except Exception:
            raise RuntimeError("La logique de soin n’est pas disponible (logic/heal.py).")
        return await heal_select(inter, emoji, cible)

    # utilitaires : consomme ici
    if not await _consume_item(inter.user.id, emoji):
        raise RuntimeError(f"Tu n’as pas **{emoji}** dans ton inventaire.")
    target = cible or inter.user

    if typ == "bouclier":
        return await apply_shield(inter, inter.user, target, emoji, info)
    if typ == "vaccin":
        return await apply_vaccine(inter, inter.user, target, emoji, info)
    if typ == "mysterybox":
        return await open_box(inter, inter.user, emoji)
    if typ == "vol":
        return await try_theft(inter, inter.user, target if isinstance(target, discord.Member) else None)
    if typ in ("esquive+", "reduction", "immunite"):
        return await apply_buff(inter, inter.user, target, emoji, info, typ)

    return _warn("Objet non géré", f"{emoji} (**{typ}**) n’a pas de logique dédiée pour le moment."), {"applied": False}

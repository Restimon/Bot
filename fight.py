# logic/fight.py
from __future__ import annotations

import asyncio
import json
import random
from typing import Dict, Optional, Tuple

import discord

# DB combat / stats
from stats_db import deal_damage, heal_user, get_hp, is_dead, revive_full
try:
    from stats_db import add_damage_stat  # optionnel
except Exception:
    async def add_damage_stat(*args, **kwargs): return None

# Effets (ticks + utilitaires offensifs)
from effects_db import (
    add_or_refresh_effect,
    remove_effect,
    has_effect,
    list_effects,
    effects_loop,
    set_broadcaster,
    transfer_virus_on_attack,
    get_outgoing_damage_penalty,
)

# Inventaire (consommation d’objet)
from inventory_db import get_item_qty, remove_item

# Passifs (tous optionnels : on pose des stubs)
try:
    from passifs import trigger as passifs_trigger
except Exception:
    async def passifs_trigger(*args, **kwargs): return {}

try:
    from passifs import get_extra_dodge_chance
except Exception:
    async def get_extra_dodge_chance(*args, **kwargs): return 0.0

try:
    from passifs import get_extra_reduction_percent
except Exception:
    async def get_extra_reduction_percent(*args, **kwargs): return 0.0

try:
    from passifs import king_execute_ready
except Exception:
    async def king_execute_ready(*args, **kwargs): return False

try:
    from passifs import undying_zeyra_check_and_mark
except Exception:
    async def undying_zeyra_check_and_mark(*args, **kwargs): return False

# Catalogue d’objets
try:
    from utils import OBJETS, FIGHT_GIFS  # type: ignore
except Exception:
    OBJETS = {}
    FIGHT_GIFS = {}

# ─────────────────────────────────────────────────────────
# Helpers inventaire
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
# Calculs défensifs (dodge / réduction)
# ─────────────────────────────────────────────────────────
async def _sum_effect_value(user_id: int, *types_: str) -> float:
    out = 0.0
    try:
        rows = await list_effects(user_id)
        wanted = set(types_)
        for eff_type, value, interval, next_ts, end_ts, source_id, meta_json in rows:
            if eff_type in wanted:
                try:
                    out += float(value)
                except Exception:
                    pass
    except Exception:
        pass
    return out

async def _compute_dodge_chance(user_id: int) -> float:
    base = float(await get_extra_dodge_chance(user_id))
    buffs = await _sum_effect_value(user_id, "esquive", "esquive+")
    return min(base + float(buffs), 0.95)

async def _compute_reduction_pct(user_id: int) -> float:
    base = float(await get_extra_reduction_percent(user_id))
    buffs = await _sum_effect_value(user_id, "reduction", "reduction_temp", "reduction_valen")
    return min(base + float(buffs), 0.90)

async def _calc_outgoing_penalty(attacker_id: int, base: int) -> int:
    try:
        try:
            res = await get_outgoing_damage_penalty(attacker_id, base)  # type: ignore
            return max(0, int(res or 0))
        except TypeError:
            pass
        try:
            res = await get_outgoing_damage_penalty(attacker_id, base=base)  # type: ignore
            return max(0, int(res or 0))
        except TypeError:
            pass
        res = await get_outgoing_damage_penalty(attacker_id)  # type: ignore
        if isinstance(res, dict):
            flat = int(res.get("flat", 0) or 0)
            pct = float(res.get("percent", 0) or 0.0)
            return max(0, int(flat + round(base * pct)))
        return max(0, int(res or 0))
    except Exception:
        return 0

# ─────────────────────────────────────────────────────────
# Mécanique d’un coup (resolve)
# ─────────────────────────────────────────────────────────
async def _resolve_hit(
    attacker: discord.Member,
    target: discord.Member,
    base_damage: int,
    is_crit_flag: bool = False,
) -> Tuple[int, int, bool, str]:
    """
    Retourne (dmg_final, absorbed, dodged, ko_txt)
    """
    # Esquive ?
    dodge = await _compute_dodge_chance(target.id)
    if random.random() < dodge:
        try:
            await passifs_trigger("on_defense_after",
                                  defender_id=target.id, attacker_id=attacker.id,
                                  final_taken=0, dodged=True)
        except Exception:
            pass
        return 0, 0, True, "\n🛰️ **Esquive !**"

    # Hooks pré-défense (peuvent annuler/halfer)
    try:
        predef = await passifs_trigger("on_defense_pre",
                                       defender_id=target.id,
                                       attacker_id=attacker.id,
                                       incoming=int(base_damage)) or {}
    except Exception:
        predef = {}
    cancel = bool(predef.get("cancel"))
    half   = bool(predef.get("half"))
    flat   = int(predef.get("flat_reduce", 0))
    counter_frac = float(predef.get("counter_frac", 0.0) or 0.0)

    dr_pct = await _compute_reduction_pct(target.id)

    if cancel:
        dmg_final = 0
    else:
        dmg_final = int(base_damage * (0.5 if half else 1.0))
        dmg_final = int(dmg_final * (1.0 - dr_pct))
        dmg_final = max(0, dmg_final - flat)

    res = await deal_damage(attacker.id, target.id, int(dmg_final))
    absorbed = int(res.get("absorbed", 0) or 0)

    # Contre-attaque passive (si définie)
    if counter_frac > 0 and dmg_final > 0:
        try:
            counter = max(1, int(round(dmg_final * counter_frac)))
            await deal_damage(target.id, attacker.id, counter)
        except Exception:
            pass

    # KO ?
    ko_txt = ""
    if await is_dead(target.id):
        if await undying_zeyra_check_and_mark(target.id):
            await heal_user(target.id, target.id, 1)  # se “relève” à 1 PV
            ko_txt = "\n⭐ **Volonté de Fracture** : survit à 1 PV."
        else:
            await revive_full(target.id)
            ko_txt = "\n💥 **Cible mise KO** (réanimée en PV/PB)."

    try:
        await passifs_trigger("on_defense_after",
                              defender_id=target.id, attacker_id=attacker.id,
                              final_taken=dmg_final, dodged=False)
    except Exception:
        pass

    return int(dmg_final), absorbed, False, ko_txt

# ─────────────────────────────────────────────────────────
# Embeds d’affichage
# ─────────────────────────────────────────────────────────
def _gif_for(emoji: str) -> Optional[str]:
    gif = FIGHT_GIFS.get(emoji) if isinstance(FIGHT_GIFS, dict) else None
    if isinstance(gif, str) and (gif.startswith("http://") or gif.startswith("https://")):
        return gif
    return None

def build_attack_embed(
    emoji: str,
    attacker: discord.Member,
    target: discord.Member,
    hp_before: int,
    pv_lost: int,
    hp_after: int,
    ko_txt: str,
    dodged: bool
) -> discord.Embed:
    title = f"{emoji} Action de GotValis"
    e = discord.Embed(title=title, color=discord.Color.orange())
    if dodged:
        e.description = f"{attacker.mention} tente {emoji} sur {target.mention}…\n🛰️ **Esquive !**{ko_txt}"
    else:
        lines = [
            f"{attacker.mention} inflige **{pv_lost}** dégâts à {target.mention} avec {emoji} !",
            f"{target.mention} perd (**{pv_lost} PV**)",
            f"❤️ **{hp_before} PV** - (**{pv_lost} PV**) = ❤️ **{hp_after} PV**"
        ]
        if ko_txt:
            lines.append(ko_txt.strip())
        e.description = "\n".join(lines)
    gif = _gif_for(emoji)
    if gif:
        e.set_image(url=gif)
    return e

def build_dot_embed(
    label: str,
    applier: discord.Member,
    target: discord.Member,
    emoji: str,
    value: int,
    interval: int,
    duration: int
) -> discord.Embed:
    e = discord.Embed(
        title=label,
        description=(
            f"{applier.mention} applique **{emoji}** sur {target.mention} "
            f"(valeur **{value}**, toutes les **{max(1, interval)}s**, pendant **{max(1, duration)}s**)."
        ),
        color=discord.Color.dark_orange()
    )
    return e

# ─────────────────────────────────────────────────────────
# Actions publiques
# ─────────────────────────────────────────────────────────
async def apply_attack(
    inter: discord.Interaction,
    attacker: discord.Member,
    target: discord.Member,
    emoji: str,
    info: Dict,
) -> Tuple[discord.Embed, Dict]:
    """
    Dégâts directs. Retourne (embed, meta).
    """
    base = int(info.get("degats", info.get("dmg", info.get("valeur", 0))) or 0)
    if await king_execute_ready(attacker.id, target.id):
        base = max(base, 10_000_000)

    # malus sortant + virus
    base = max(0, base - int(await _calc_outgoing_penalty(attacker.id, base)))
    await transfer_virus_on_attack(attacker.id, target.id)

    hp_before, _ = await get_hp(target.id)
    dmg_final, absorbed, dodged, ko_txt = await _resolve_hit(inter.user, target, base, False)
    hp_after, _ = await get_hp(target.id)

    try:
        await passifs_trigger("on_attack", attacker_id=attacker.id, target_id=target.id, damage_done=dmg_final)
    except Exception:
        pass
    if dmg_final > 0:
        await add_damage_stat(attacker.id, int(dmg_final))

    embed = build_attack_embed(emoji, attacker, target, hp_before, dmg_final, hp_after, ko_txt, dodged)
    return embed, {"damage_done": dmg_final, "absorbed": absorbed, "dodged": dodged}

async def apply_chain_attack(
    inter: discord.Interaction,
    attacker: discord.Member,
    target: discord.Member,
    emoji: str,
    info: Dict,
) -> Tuple[discord.Embed, Dict]:
    """
    Dégâts en 2 étapes: principal puis secondaire (même cible ici).
    """
    d1 = int(info.get("degats_principal", info.get("dmg_main", info.get("valeur", 0))) or 0)
    d2 = int(info.get("degats_secondaire", info.get("dmg_chain", 0)) or 0)

    # malus sortant + virus
    d1 = max(0, d1 - int(await _calc_outgoing_penalty(attacker.id, d1)))
    d2 = max(0, d2 - int(await _calc_outgoing_penalty(attacker.id, d2)))
    await transfer_virus_on_attack(attacker.id, target.id)

    hp_before, _ = await get_hp(target.id)
    dmg_total = 0; absorbed_total = 0; dodged_any = False; ko_txt_all = ""

    for part in (d1, d2):
        if part <= 0:
            continue
        dmg_final, absorbed, dodged, ko_txt = await _resolve_hit(attacker, target, part, False)
        dmg_total += int(dmg_final)
        absorbed_total += int(absorbed)
        dodged_any = dodged_any or dodged
        if ko_txt:
            ko_txt_all = ko_txt  # garde le dernier

    hp_after, _ = await get_hp(target.id)
    try:
        await passifs_trigger("on_attack", attacker_id=attacker.id, target_id=target.id, damage_done=dmg_total)
    except Exception:
        pass
    if dmg_total > 0:
        await add_damage_stat(attacker.id, int(dmg_total))

    embed = build_attack_embed(emoji, attacker, target, hp_before, dmg_total, hp_after, ko_txt_all, dodged_any)
    return embed, {"damage_done": dmg_total, "absorbed": absorbed_total, "dodged": dodged_any}

async def apply_dot(
    inter: discord.Interaction,
    applier: discord.Member,
    target: discord.Member,
    emoji: str,
    info: Dict,
    eff_type: str,
    label: str,
) -> Tuple[discord.Embed, Dict]:
    """
    Applique un DOT/état négatif (poison, infection, virus, brulure).
    """
    value = int(info.get("degats", info.get("value", info.get("valeur", 0))) or 0)
    interval = int(info.get("intervalle", info.get("interval", 60)) or 60)
    duration = int(info.get("duree", info.get("duration", 300)) or 300)

    # Hook passifs pré-application (certaines immunités)
    try:
        pre = await passifs_trigger("on_effect_pre_apply", user_id=target.id, eff_type=str(eff_type)) or {}
        if pre.get("blocked"):
            e = discord.Embed(
                title="⛔ Effet bloqué",
                description=pre.get("reason", "Impossible d’appliquer cet effet pour le moment."),
                color=discord.Color.red()
            )
            return e, {"applied": False}
    except Exception:
        pass

    ok = await add_or_refresh_effect(
        user_id=target.id, eff_type=str(eff_type), value=float(value),
        duration=duration, interval=interval,
        source_id=applier.id, meta_json=json.dumps({"from": applier.id, "emoji": emoji})
    )
    if not ok:
        e = discord.Embed(
            title="⛔ Effet refusé",
            description="L’effet n’a pas pu être appliqué (immunité, règle spéciale, etc.).",
            color=discord.Color.red()
        )
        return e, {"applied": False}

    embed = build_dot_embed(label, applier, target, emoji, value, interval, duration)
    return embed, {"applied": True, "value": value, "interval": interval, "duration": duration}

# ─────────────────────────────────────────────────────────
# Sélecteur générique pour /fight
# ─────────────────────────────────────────────────────────
async def select_and_apply(
    inter: discord.Interaction,
    cible: discord.Member,
    emoji: str,
) -> Tuple[discord.Embed, Dict]:
    """
    Consomme l’objet si possédé, vérifie son type et applique.
    Retourne (embed, meta).
    """
    if inter.user.id == cible.id:
        raise ValueError("Tu ne peux pas t’attaquer toi-même.")

    info = _obj_info(emoji)
    if not info:
        raise ValueError("Objet inconnu.")
    typ = str(info.get("type", ""))

    if typ not in ("attaque", "attaque_chaine", "poison", "infection", "virus", "brulure"):
        raise ValueError("Objet invalide : il faut un **objet offensif**.")

    if not await _consume_item(inter.user.id, emoji):
        raise RuntimeError(f"Tu n’as pas **{emoji}** dans ton inventaire.")

    # Déroule selon type
    if typ == "attaque":
        return await apply_attack(inter, inter.user, cible, emoji, info)
    if typ == "attaque_chaine":
        return await apply_chain_attack(inter, inter.user, cible, emoji, info)

    labels = {
        "poison": "🧪 Poison",
        "infection": "🧟 Infection",
        "virus": "🦠 Virus (transfert sur attaque)",
        "brulure": "🔥 Brûlure",
    }
    return await apply_dot(inter, inter.user, cible, emoji, info, eff_type=typ, label=labels[typ])

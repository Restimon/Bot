# combat.py
from __future__ import annotations

import random
from typing import Dict, Any, Optional, List

from inventory import remove_item, add_item, get_item_qty
from stats_db import (
    deal_damage,
    heal_user,
    add_shield,
    get_hp,
    is_dead,
    revive_full,
    get_shield,
)
from effects_db import (
    add_or_refresh_effect,
    transfer_virus_on_attack,
    has_effect as has_status,
    remove_effect as remove_status,
    get_effect as get_status,   # pour lire les valeurs (esquive/reduction)
    _pack_meta,
)
from ravitaillement import OBJETS, GIFS
from passifs import (
    get_equipped_code,
    crit_multiplier_against_defender_code,
    get_extra_dodge_chance,
    get_extra_reduction_percent,
    maybe_preserve_consumable,
    king_execute_ready,
    valen_reduction_bonus,
    undying_zeyra_check_and_mark,
    on_attack_after,
    on_heal_after,
    on_use_after,
    bonus_damage_vs_infected,
)

# ─────────────────────────────────────────────────────────────
# Réglages globaux
# ─────────────────────────────────────────────────────────────
BASE_CRIT_MULT = 2.0             # crit x2
COLOR_ATTACK = 0xED4245
COLOR_HEAL   = 0x57F287
COLOR_USE    = 0xFEE75C

INFECTION_PROPAGATE_CHANCE = 0.25      # 25% (si attaquant infecté)
POISON_OUTGOING_PENALTY    = 1         # −1 dmg direct si l’attaquant est empoisonné

# ─────────────────────────────────────────────────────────────
# Utils locaux
# ─────────────────────────────────────────────────────────────
def _clamp(n: float, a: float, b: float) -> float:
    return max(a, min(b, n))

def _gif_for(item_key: str) -> Optional[str]:
    return GIFS.get(item_key) or None

async def _consume_item_if_needed(user_id: int, item_key: str) -> bool:
    """
    Consomme l’objet à la fin de l’action, sauf si passif 'ne consomme pas' s’active.
    Retourne True si l’objet a été consommé.
    """
    preserve = await maybe_preserve_consumable(user_id, item_key)
    if preserve:
        return False
    await remove_item(user_id, item_key, 1)
    return True

async def _status_dodge_bonus(user_id: int) -> float:
    """
    Bonus d'esquive depuis un statut (effects_db 'esquive'), sinon 0.
    """
    row = await get_status(user_id, "esquive")
    if not row:
        return 0.0
    value, *_ = row
    try:
        return float(value)
    except Exception:
        return 0.0

async def _status_reduction_bonus(user_id: int) -> float:
    """
    Somme des réductions depuis statuts (effects_db) :
      - reduction, reduction_temp, reduction_valen
    """
    total = 0.0
    for key in ("reduction", "reduction_temp", "reduction_valen"):
        row = await get_status(user_id, key)
        if row:
            v, *_ = row
            try:
                total += float(v)
            except Exception:
                pass
    return _clamp(total, 0.0, 0.9)

async def _current_esquive_chance(defender_id: int) -> float:
    """
    Esquive totale du défenseur :
      - statut 'esquive' (effects_db)
      - bonus passifs (Nova +5%, Elira +10%, etc.)
    """
    status = await _status_dodge_bonus(defender_id)
    extra  = await get_extra_dodge_chance(defender_id) or 0.0
    return _clamp(status + extra, 0.0, 0.95)

async def _current_reduction_percent(defender_id: int) -> float:
    """
    Réduction en % (n’affecte PAS les DOT, déjà géré côté effects_db).
    Sources :
      - Statuts : reduction*, etc.
      - Passifs : get_extra_reduction_percent + paliers Valen
    """
    status = await _status_reduction_bonus(defender_id)
    extra  = await get_extra_reduction_percent(defender_id) or 0.0
    valen  = await valen_reduction_bonus(defender_id) or 0.0
    return _clamp(status + extra + valen, 0.0, 0.90)

async def _is_immune(defender_id: int) -> bool:
    """Immunité bloque les dégâts directs (les DOT sont bloqués dans effects_db)."""
    return await has_status(defender_id, "immunite")

def _roll_crit_mult(base_chance: float, defender_code: Optional[str]) -> float:
    """
    Retourne le multiplicateur (1.0 = pas crit, >1 = crit).
    Le multiplicateur subit les modifs défenseur (ex: Zeyra divise par 2).
    """
    if base_chance <= 0:
        return 1.0
    if random.random() >= base_chance:
        return 1.0
    mult = BASE_CRIT_MULT
    if defender_code:
        mult *= crit_multiplier_against_defender_code(defender_code) or 1.0
    return mult

async def _apply_direct_damage(attacker_id: int, defender_id: int, raw_damage: int) -> Dict[str, Any]:
    """
    Applique des dégâts **directs** :
      - esquive (évite tout) — pas pour DOT
      - immunité (bloque tout) — pas pour DOT
      - réduction (%), puis deal_damage (PB → PV)
    Retour : {'dmg_in','dmg_after_reduc','absorbed','lost','dodged','immune','ko'}
    """
    # Esquive ?
    dodge_chance = await _current_esquive_chance(defender_id)
    if random.random() < dodge_chance:
        return {"dmg_in": raw_damage, "dmg_after_reduc": 0, "absorbed": 0, "lost": 0, "dodged": True, "immune": False, "ko": False}

    # Immunité ?
    if await _is_immune(defender_id):
        return {"dmg_in": raw_damage, "dmg_after_reduc": 0, "absorbed": 0, "lost": 0, "dodged": False, "immune": True, "ko": False}

    # Réduction
    reduc = await _current_reduction_percent(defender_id)
    eff_damage = max(0, int(round(raw_damage * (1.0 - reduc))))

    # Application (PB → PV dans stats_db)
    res = await deal_damage(attacker_id, defender_id, eff_damage)  # {'absorbed': X, 'lost': Y}
    ko = await is_dead(defender_id)

    return {
        "dmg_in": raw_damage,
        "dmg_after_reduc": eff_damage,
        "absorbed": res.get("absorbed", 0),
        "lost": res.get("lost", 0),
        "dodged": False,
        "immune": False,
        "ko": ko,
    }

# ─────────────────────────────────────────────────────────────
# Résolution d’ATTAQUE / SOIN / USE
# ─────────────────────────────────────────────────────────────
async def fight(attacker_id: int, target_id: int, item_key: str, guild_id: int, channel_id: int) -> Dict[str, Any]:
    """
    Attaque / DOT / attaque_chaine :
      - −1 dmg si attaquant empoisonné (direct only)
      - bonus vs infectés
      - crit x2 (modif Zeyra)
      - réduction → PB → PV
      - application DOT avec meta (salon)
      - virus transfert (5 sortant + 5 entrant, timer conservé)
      - infection contagion 25% (+5 dmg immédiat)
      - Exécution Roi (≤10 PV) ignore défenses
      - Undying Zeyra (1/j)
    """
    it = OBJETS.get(item_key, {})
    typ = it.get("type")
    lines: List[str] = []
    color = COLOR_ATTACK
    title = "⚔️ Attaque"
    consumed = False

    if typ not in {"attaque", "attaque_chaine", "poison", "virus", "infection"}:
        return {"title": "❌ Objet d'attaque invalide", "lines": [], "color": 0xFF0000}

    if await get_item_qty(attacker_id, item_key) <= 0:
        return {"title": "❌ Plus d’objet", "lines": ["Tu n’as plus cet objet."], "color": 0xFF0000}

    # Exécution du Roi ?
    if await king_execute_ready(attacker_id, target_id):
        # Idée simple : dégâts “énormes” pour passer malgré reduc/PB
        hp, _ = await get_hp(target_id)
        sh = await get_shield(target_id)
        huge = hp + sh + 9999
        await deal_damage(attacker_id, target_id, huge)
        lines.append("👑 **Exécution Royale !** (ignore défenses)")
        # Heal +10 PV à l’attaquant
        healed = await heal_user(attacker_id, attacker_id, 10)
        if healed > 0:
            lines.append(f"❤️ +{healed} PV à l’exécuteur.")
        consumed = not (await maybe_preserve_consumable(attacker_id, item_key))
        if consumed:
            await remove_item(attacker_id, item_key, 1)

        # KO handling + Zeyra Undying
        if await is_dead(target_id):
            undy = await undying_zeyra_check_and_mark(target_id)
            if undy:
                await revive_full(target_id)   # 100 PV
                await deal_damage(0, target_id, 99)  # retour à 1 PV
                lines.append("💥 **Volonté de Fracture** : survit à 1 PV !")
            else:
                await revive_full(target_id)
        await on_attack_after(attacker_id, target_id, item_key)
        return {"title": title, "lines": lines, "color": color, "gif": _gif_for(item_key), "consumed": consumed}

    meta = _pack_meta(guild_id, channel_id)

    # DOT & statut pur : applique l’effet et termine
    if typ == "poison":
        await add_or_refresh_effect(
            target_id, "poison",
            int(it.get("degats", 1)),
            int(it.get("duree", 3600)),
            interval=int(it.get("intervalle", 1800)),
            source_id=attacker_id, meta_json=meta
        )
        consumed = await _consume_item_if_needed(attacker_id, item_key)
        lines.append("🧪 Poison appliqué.")
    elif typ == "virus":
        await add_or_refresh_effect(
            target_id, "virus",
            int(it.get("degats", 1)),
            int(it.get("duree", 3600)),
            interval=int(it.get("intervalle", 1800)),
            source_id=attacker_id, meta_json=meta
        )
        consumed = await _consume_item_if_needed(attacker_id, item_key)
        lines.append("🦠 Virus appliqué.")
    elif typ == "infection":
        await add_or_refresh_effect(
            target_id, "infection",
            int(it.get("degats", 5)),
            int(it.get("duree", 3*3600)),
            interval=int(it.get("intervalle", 1800)),
            source_id=attacker_id, meta_json=meta
        )
        consumed = await _consume_item_if_needed(attacker_id, item_key)
        lines.append("🧟 Infection appliquée.")
    else:
        # Dégâts directs (attaque / attaque_chaine)
        # Base
        if typ == "attaque":
            base = int(it.get("degats", 0))
            # malus poison (direct only)
            if await has_status(attacker_id, "poison"):
                base = max(0, base - POISON_OUTGOING_PENALTY)
            # bonus vs infectés
            if await has_status(target_id, "infection"):
                base += (await bonus_damage_vs_infected(attacker_id) or 0)
            # crit
            defender_code = await get_equipped_code(target_id)
            crit_mult = _roll_crit_mult(float(it.get("crit", 0.0)), defender_code)
            dmg = int(round(base * crit_mult))

        else:  # attaque_chaine (principal)
            base = int(it.get("degats_principal", 0))
            # malus poison
            if await has_status(attacker_id, "poison"):
                base = max(0, base - POISON_OUTGOING_PENALTY)
            # bonus vs infectés
            if await has_status(target_id, "infection"):
                base += (await bonus_damage_vs_infected(attacker_id) or 0)
            defender_code = await get_equipped_code(target_id)
            crit_mult = _roll_crit_mult(float(it.get("crit", 0.0)), defender_code)
            dmg = int(round(base * crit_mult))

        # Application
        apply = await _apply_direct_damage(attacker_id, target_id, dmg)
        consumed = await _consume_item_if_needed(attacker_id, item_key)

        if apply.get("dodged"):
            lines.append("👟 Esquive !")
        elif apply.get("immune"):
            lines.append("⭐ Immunité : aucun dégât.")
        else:
            if crit_mult > 1.0:
                lines.append("💫 **Coup critique !**")
            if apply["absorbed"] > 0:
                lines.append(f"🛡 {apply['absorbed']} PB absorbés.")
            lines.append(f"💥 {apply['lost']} dégâts infligés.")

        if typ == "attaque_chaine":
            lines.append("☠️ Attaque en chaîne (cible principale).")
            # Si tu veux enchaîner d’autres cibles plus tard, c’est ici.

    # Effets secondaires liés aux statuts de l’ATTAQUANT
    # Virus : 5 dmg sortie (ancien porteur) + 5 dmg entrée (nouvelle cible) + transfert (timer conservé)
    await transfer_virus_on_attack(attacker_id, target_id)

    # Infection : 25% de propager à la cible + 5 dmg instant si contamine
    if await has_status(attacker_id, "infection"):
        if random.random() < INFECTION_PROPAGATE_CHANCE:
            src = OBJETS.get("🧟", {"degats": 5, "intervalle": 1800, "duree": 3*3600})
            await add_or_refresh_effect(
                target_id, "infection",
                int(src.get("degats", 5)),
                int(src.get("duree", 3*3600)),
                interval=int(src.get("intervalle", 1800)),
                source_id=attacker_id, meta_json=meta
            )
            await deal_damage(attacker_id, target_id, 5)
            lines.append("🧟 Contagion : la cible devient infectée (+5 dmg).")

    # KO → Undying Zeyra, sinon revive (règle 14 pour attaques directes)
    if await is_dead(target_id):
        undy = await undying_zeyra_check_and_mark(target_id)
        if undy:
            await revive_full(target_id)
            await deal_damage(0, target_id, 99)  # revient à 1 PV
            lines.append("💥 **Volonté de Fracture** : survit à 1 PV !")
        else:
            await revive_full(target_id)

    # Hooks post-attaque (loot etc.)
    await on_attack_after(attacker_id, target_id, item_key)

    return {
        "title": title,
        "lines": lines,
        "color": color,
        "gif": _gif_for(item_key),
        "consumed": consumed,
    }


async def heal(healer_id: int, target_id: int, item_key: str, guild_id: int, channel_id: int) -> Dict[str, Any]:
    """
    Soins & régénérations :
      - soins directs (cap PV max côté stats_db)
      - régénération (ticks, meta pour le salon)
      - hooks post-soin (ex: gain PB, etc.)
    """
    it = OBJETS.get(item_key, {})
    typ = it.get("type")
    lines: List[str] = []
    color = COLOR_HEAL
    title = "💊 Soin"
    consumed = False

    if typ not in {"soin", "regen"}:
        return {"title": "❌ Objet de soin invalide", "lines": [], "color": 0xFF0000}

    if await get_item_qty(healer_id, item_key) <= 0:
        return {"title": "❌ Plus d’objet", "lines": ["Tu n’as plus cet objet."], "color": 0xFF0000}

    if typ == "soin":
        amount = int(it.get("soin", 0))
        healed = await heal_user(healer_id, target_id, amount)
        consumed = await _consume_item_if_needed(healer_id, item_key)
        if healed <= 0:
            lines.append("ℹ️ Aucun PV soigné (déjà au max ?).")
        else:
            lines.append(f"❤️ +{healed} PV.")
    else:  # regen
        meta = _pack_meta(guild_id, channel_id)
        await add_or_refresh_effect(
            target_id,
            "regen",
            float(it.get("valeur", 1)),
            int(it.get("duree", 3600)),
            interval=int(it.get("intervalle", 1800)),
            source_id=healer_id,
            meta_json=meta
        )
        consumed = await _consume_item_if_needed(healer_id, item_key)
        lines.append("💕 Régénération appliquée.")

    await on_heal_after(healer_id, target_id, item_key)

    return {
        "title": title,
        "lines": lines,
        "color": color,
        "gif": _gif_for(item_key),
        "consumed": consumed,
    }


async def use_item(user_id: int, target_id: int, item_key: str, guild_id: int, channel_id: int) -> Dict[str, Any]:
    """
    Utilisation non-offensive :
      - bouclier (cap 20 / 25 selon passif côté stats_db)
      - vaccin (retire poison, virus, infection)
      - vol (pas de tickets)
      - immunité / esquive+ / réduction (statuts)
      - mysterybox (loot simple)
    """
    it = OBJETS.get(item_key, {})
    typ = it.get("type")
    lines: List[str] = []
    color = COLOR_USE
    title = "🧰 Utilisation"
    consumed = False

    if typ not in {"bouclier", "vaccin", "vol", "immunite", "esquive+", "reduction", "mysterybox"}:
        return {"title": "❌ Objet non-utilisable invalide", "lines": [], "color": 0xFF0000}

    if await get_item_qty(user_id, item_key) <= 0:
        return {"title": "❌ Plus d’objet", "lines": ["Tu n’as plus cet objet."], "color": 0xFF0000}

    meta = _pack_meta(guild_id, channel_id)

    if typ == "bouclier":
        val = int(it.get("valeur", 0))
        gained = await add_shield(target_id, val)
        consumed = await _consume_item_if_needed(user_id, item_key)
        lines.append(f"🛡 +{gained} PB appliqués.")

    elif typ == "vaccin":
        await remove_status(target_id, "poison")
        await remove_status(target_id, "virus")
        await remove_status(target_id, "infection")
        consumed = await _consume_item_if_needed(user_id, item_key)
        lines.append("💉 Vaccination : poison/virus/infection retirés.")

    elif typ == "vol":
        # Vol d’un item aléatoire (sauf tickets)
        pool = [k for k in OBJETS.keys() if k != "🎟️"]
        if not pool:
            return {"title": "ℹ️ Rien à voler", "lines": [], "color": 0xAAAAAA}
        # essaie quelques tirages pour trouver un item détenu
        choice = None
        for _ in range(10):
            c = random.choice(pool)
            if await get_item_qty(target_id, c) > 0:
                choice = c
                break
        if not choice:
            lines.append("🕵️ Rien d’utile n’a été trouvé.")
        else:
            await remove_item(target_id, choice, 1)
            await add_item(user_id, choice, 1)
            lines.append(f"🕵️ Vol réussi : {choice}")
        consumed = await _consume_item_if_needed(user_id, item_key)

    elif typ == "immunite":
        await add_or_refresh_effect(target_id, "immunite", 1.0, int(it.get("duree", 2*3600)), source_id=user_id, meta_json=meta)
        consumed = await _consume_item_if_needed(user_id, item_key)
        lines.append("⭐ Immunité temporaire appliquée.")

    elif typ == "esquive+":
        await add_or_refresh_effect(target_id, "esquive", float(it.get("valeur", 0.2)), int(it.get("duree", 3*3600)), source_id=user_id, meta_json=meta)
        consumed = await _consume_item_if_needed(user_id, item_key)
        lines.append("👟 Esquive augmentée (temporaire).")

    elif typ == "reduction":
        await add_or_refresh_effect(target_id, "reduction_temp", float(it.get("valeur", 0.5)), int(it.get("duree", 4*3600)), source_id=user_id, meta_json=meta)
        consumed = await _consume_item_if_needed(user_id, item_key)
        lines.append("🪖 Réduction des dégâts appliquée (temporaire).")

    elif typ == "mysterybox":
        pulls = random.randint(1, 3)
        pool = [k for k in OBJETS.keys() if k != "🎟️"]
        won: Dict[str, int] = {}
        for _ in range(pulls):
            k = random.choice(pool)
            won[k] = won.get(k, 0) + 1
        for k, q in won.items():
            await add_item(user_id, k, q)
        consumed = await _consume_item_if_needed(user_id, item_key)
        pretty = " ".join(f"{k} x{q}" for k, q in won.items())
        lines.append(f"📦 {pretty}")

    await on_use_after(user_id, target_id, item_key)

    return {
        "title": title,
        "lines": lines,
        "color": color,
        "gif": _gif_for(item_key),
        "consumed": consumed,
    }

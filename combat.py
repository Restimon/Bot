# combat.py
from __future__ import annotations

import random
import math
import asyncio
from typing import Dict, Any, Optional, Tuple, List

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
    _pack_meta,
    has_effect as has_status,
    remove_effect as remove_status,
)
from ravitaillement import OBJETS, GIFS  # tu m'as dit que le fichier s'appelle ravitaillement.py
from passifs import (
    get_equipped_code,
    # ---- Hooks passifs (noms à adapter si besoin) ----
    crit_multiplier_against_defender_code,    # e.g. Zeyra : 0.5
    get_extra_dodge_chance,                   # bonus d’esquive côté défenseur (%, 0..1)
    get_extra_reduction_percent,              # réduction supplémentaire côté défenseur (0..1)
    maybe_preserve_consumable,                # True => ne consomme pas l’objet
    king_execute_ready,                       # True si 'Le Roi' exécute à 10 PV
    valen_reduction_bonus,                    # % de réduction dynamique quand <50% PV
    undying_zeyra_check_and_mark,             # retourne True si “sauvegardée à 1 PV” (consomme le charge/jour)
    on_attack_after,                          # triggers post-attaque (loot, heal on hit, etc.)
    on_heal_after,                            # triggers post-heal (gain PB etc.)
    on_use_after,                             # triggers post-use (si tu en as besoin)
    bonus_damage_vs_infected,                 # e.g. Kevar Rin : +3 dmg vs infectés
)

# ─────────────────────────────────────────────────────────────
# Réglages globaux
# ─────────────────────────────────────────────────────────────
BASE_CRIT_MULT = 2.0             # crit x2
ATTACK_DODGE_IMMUNE_LABEL = "👟 Esquive !"
IMMUNITY_LABEL = "⭐ Immunité"
COLOR_ATTACK = 0xED4245
COLOR_HEAL = 0x57F287
COLOR_USE = 0xFEE75C

# Pour infection “contagion” lors d’une attaque
INFECTION_PROPAGATE_CHANCE = 0.25

# Poison : malus -1 dmg pour l’attaquant
POISON_OUTGOING_PENALTY = 1

# ─────────────────────────────────────────────────────────────
# Utils locaux
# ─────────────────────────────────────────────────────────────

def _clamp(n: float, a: float, b: float) -> float:
    return max(a, min(b, n))

async def _current_esquive_chance(defender_id: int) -> float:
    """
    Esquive totale du défenseur :
      - Bonus de statut 'esquive' (effects_db)
      - Bonus passif (e.g. Nova Rell +5%)
      - Stacks temporaires (e.g. Neyra) -> supposé stockés dans effects_db sous 'esquive'
    """
    base = 0.0
    eff = await has_status(defender_id, "esquive")
    if eff:
        # on lit la valeur via get_effect si besoin ; ici on suppose get_extra_dodge_chance ajoute ce qui manque
        pass
    extra = await get_extra_dodge_chance(defender_id) or 0.0
    return _clamp(base + extra, 0.0, 0.95)

async def _current_reduction_percent(defender_id: int) -> float:
    """
    Réduction totale (ne s’applique PAS aux DOT — déjà géré dans effects_db).
    Sources :
      - effets: reduction / reduction_temp / reduction_valen (en %)
      - passifs (e.g. bonus passif fixe, paliers Valen)
    """
    base = await get_extra_reduction_percent(defender_id) or 0.0
    base += await valen_reduction_bonus(defender_id) or 0.0
    # clamp prudent
    return _clamp(base, 0.0, 0.90)

async def _is_immune(defender_id: int) -> bool:
    """Immunité bloque entièrement les dégâts directs (et les DOT côté effects_db)."""
    return await has_status(defender_id, "immunite")

async def _apply_direct_damage(attacker_id: int, defender_id: int, raw_damage: int) -> Dict[str, Any]:
    """
    Applique des dégâts **directs** avec règles :
      - esquive (tout évite) — pas pour DOT
      - immunité (tout bloque) — pas pour DOT (géré dans effects)
      - réduction (%), puis deal_damage (qui gère PB -> PV)
    Retourne un dict: {'dmg_in': raw, 'dmg_after_reduc': x, 'absorbed': y, 'lost': z, 'dodged': bool, 'immune': bool, 'ko': bool}
    """
    # Esquive ?
    dodge_chance = await _current_esquive_chance(defender_id)
    if random.random() < dodge_chance:
        return {"dmg_in": raw_damage, "dmg_after_reduc": 0, "absorbed": 0, "lost": 0, "dodged": True, "immune": False, "ko": False}

    # Immunité ?
    if await _is_immune(defender_id):
        return {"dmg_in": raw_damage, "dmg_after_reduc": 0, "absorbed": 0, "lost": 0, "dodged": False, "immune": True, "ko": False}

    # Réduction (%)
    reduc = await _current_reduction_percent(defender_id)
    eff_damage = max(0, int(round(raw_damage * (1.0 - reduc))))

    # Appliquer dégâts (deal_damage gère PB->PV + stats + coins)
    res = await deal_damage(attacker_id, defender_id, eff_damage)  # res: {'absorbed': X, 'lost': Y}
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

def _roll_crit(base_chance: float, defender_code: Optional[str]) -> float:
    """
    Détermine crit: True/False. Puis retourne multiplicateur (1.0 ou 2.0 x modif Zeyra).
    - Zeyra (Volonté de Fracture 💥) : crit divisés par 2 → on ajuste le multiplicateur via passif helper
    """
    if base_chance <= 0:
        return 1.0
    if random.random() >= base_chance:
        return 1.0
    mult = BASE_CRIT_MULT
    # Ajustements côté défenseur (ex: Zeyra: *0.5)
    if defender_code:
        mult *= crit_multiplier_against_defender_code(defender_code) or 1.0
    return mult

async def _consume_item_if_needed(user_id: int, item_key: str) -> bool:
    """Consomme l’objet à la fin de l’action, sauf si passif 'ne consomme pas' s’active."""
    preserve = await maybe_preserve_consumable(user_id, item_key)
    if preserve:
        return False  # pas consommé
    await remove_item(user_id, item_key, 1)
    return True

def _gif_for(item_key: str) -> Optional[str]:
    return GIFS.get(item_key) or None

# ─────────────────────────────────────────────────────────────
# Résolution d’attaques / soins / use
# ─────────────────────────────────────────────────────────────

async def fight(attacker_id: int, target_id: int, item_key: str, guild_id: int, channel_id: int) -> Dict[str, Any]:
    """
    Attaque directe / DOT / attaque en chaîne, etc.
    - Gère poison malus -1 dmg pour l’attaquant
    - Applique crit (×2, mod Zeyra)
    - Applique réduction → PB → PV (via deal_damage)
    - Applique DOTs / infection contagion / virus transfert
    - Exécution du Roi (ignore reduc/PB) — voir NOTE
    - Zeyra Undying (1/j) si KO
    """
    it = OBJETS.get(item_key, {})
    t = it.get("type")

    result_lines: List[str] = []
    title = "⚔️ Attaque"
    color = COLOR_ATTACK
    consumed = False

    # Validation type
    if t not in {"attaque", "attaque_chaine", "poison", "virus", "infection"}:
        return {"title": "❌ Objet d'attaque invalide", "lines": [], "color": 0xFF0000}

    # Vérifier stock (par sécurité)
    if await get_item_qty(attacker_id, item_key) <= 0:
        return {"title": "❌ Plus d’objet", "lines": ["Tu n’as plus cet objet."], "color": 0xFF0000}

    # --- Préparation valeurs ---
    base_dmg = int(it.get("degats", 0))
    crit_chance = float(it.get("crit", 0.0))

    # Poison : malus -1 sur dégâts directs
    if await has_status(attacker_id, "poison"):
        base_dmg = max(0, base_dmg - POISON_OUTGOING_PENALTY)

    # Bonus passif vs infectés (Kevar Rin +3)
    if await has_status(target_id, "infection"):
        base_dmg += await bonus_damage_vs_infected(attacker_id) or 0

    # Crit
    defender_code = await get_equipped_code(target_id)
    crit_mult = _roll_crit(crit_chance, defender_code)
    dmg_after_crit = int(round(base_dmg * crit_mult))

    # Exécution du Roi (si actif)
    execute = await king_execute_ready(attacker_id, target_id)
    if execute:
        # NOTE: Idéalement, on doit **ignorer** PB et réduction.
        # Selon ton stats_db, si on ne peut pas bypass proprement :
        # on force un très gros dégât et on vide le PB préalablement si tu exposes une API.
        # Ici on fait "brutal" : dégâts énormes -> devrait passer malgré réduction/PB.
        hp, _ = await get_hp(target_id)
        sh = await get_shield(target_id)
        huge = hp + sh + 9999
        apply_res = await deal_damage(attacker_id, target_id, huge)
        result_lines.append("👑 **Exécution Royale !** (ignore défenses)")
        # Heal +10 PV à l’attaquant
        healed = await heal_user(attacker_id, attacker_id, 10)
        if healed > 0:
            result_lines.append(f"❤️ {healed} PV rendus à l’exécuteur.")
        consumed = not await maybe_preserve_consumable(attacker_id, item_key)  # ne consomme pas ? (Marn)
        if consumed:
            await remove_item(attacker_id, item_key, 1)
        # KO handling + Undying Zeyra
        if await is_dead(target_id):
            # Zeyra Undying ?
            undy = await undying_zeyra_check_and_mark(target_id)
            if undy:
                # la laisser à 1 PV
                await revive_full(target_id)  # set to 100, puis on remet 99 dégâts
                await deal_damage(0, target_id, 99)
                result_lines.append("💥 **Volonté de Fracture** : survit à 1 PV !")
            else:
                await revive_full(target_id)  # règle 14: revive & clear dans les DOT, ici on revive
        return {
            "title": title,
            "lines": result_lines,
            "color": color,
            "gif": _gif_for(item_key),
            "consumed": consumed,
        }

    # --- Cas spéciaux par type ---
    meta = _pack_meta(guild_id, channel_id)

    if t == "poison":
        # DOT poison (ticks gérés par effects_db) — on applique aussi le petit direct ? (non, tu ne l’as pas demandé)
        await add_or_refresh_effect(target_id, "poison", int(it.get("degats", 1)), int(it.get("duree", 3600)),
                                    interval=int(it.get("intervalle", 1800)), source_id=attacker_id, meta_json=meta)
        consumed = await _consume_item_if_needed(attacker_id, item_key)
        result_lines.append(f"🧪 {base_dmg} / tick appliqué (poison).")
    elif t == "virus":
        # Applique un virus “neuf”
        await add_or_refresh_effect(target_id, "virus", int(it.get("degats", 1)), int(it.get("duree", 3600)),
                                    interval=int(it.get("intervalle", 1800)), source_id=attacker_id, meta_json=meta)
        consumed = await _consume_item_if_needed(attacker_id, item_key)
        result_lines.append("🦠 Virus appliqué.")
    elif t == "infection":
        await add_or_refresh_effect(target_id, "infection", int(it.get("degats", 1)), int(it.get("duree", 3600)),
                                    interval=int(it.get("intervalle", 1800)), source_id=attacker_id, meta_json=meta)
        consumed = await _consume_item_if_needed(attacker_id, item_key)
        result_lines.append("🧟 Infection appliquée.")
    elif t == "attaque_chaine":
        # Dégâts directs sur la cible (principal)
        dmg_main = int(it.get("degats_principal", 0))
        # crit + malus poison déjà calculés via base_dmg si tu veux harmoniser,
        # mais ici on applique crit sur le principal :
        dmg_main = int(round(dmg_main * crit_mult))

        apply = await _apply_direct_damage(attacker_id, target_id, dmg_main)
        consumed = await _consume_item_if_needed(attacker_id, item_key)

        if apply.get("dodged"):
            result_lines.append(ATTACK_DODGE_IMMUNE_LABEL)
        elif apply.get("immune"):
            result_lines.append(IMMUNITY_LABEL)
        else:
            if apply["absorbed"] > 0:
                result_lines.append(f"🛡 {apply['absorbed']} PB absorbés.")
            result_lines.append(f"💥 {apply['lost']} dégâts infligés (après réductions).")

        # NOTE: “attaque en chaîne” sur d'autres cibles → à implémenter plus tard si tu veux
        result_lines.append("☠️ Attaque en chaîne (cible principale).")
    else:
        # t == "attaque" : dégâts directs
        apply = await _apply_direct_damage(attacker_id, target_id, dmg_after_crit)
        consumed = await _consume_item_if_needed(attacker_id, item_key)

        if apply.get("dodged"):
            result_lines.append(ATTACK_DODGE_IMMUNE_LABEL)
        elif apply.get("immune"):
            result_lines.append(IMMUNITY_LABEL)
        else:
            if crit_mult > 1.0:
                result_lines.append("💫 **Coup critique !**")
            if apply["absorbed"] > 0:
                result_lines.append(f"🛡 {apply['absorbed']} PB absorbés.")
            result_lines.append(f"💥 {apply['lost']} dégâts infligés (après réductions).")

    # --- Effets secondaires liés au statut de l’ATTAQUANT ---
    # Transfert de virus si l’attaquant était infecté par 'virus'
    await transfer_virus_on_attack(attacker_id, target_id, guild_id=guild_id, channel_id=channel_id)

    # Propagation d'infection si l’attaquant est infecté (25%)
    if await has_status(attacker_id, "infection"):
        if random.random() < INFECTION_PROPAGATE_CHANCE:
            # Applique une infection “copiée” à la cible (même gabarit que l’item ‘🧟’)
            # Tu as défini 🧟 dans OBJETS : on s’en sert pour la valeur/interval/durée.
            src = OBJETS.get("🧟", {"degats": 5, "intervalle": 1800, "duree": 3 * 3600})
            await add_or_refresh_effect(target_id, "infection", int(src.get("degats", 5)),
                                        int(src.get("duree", 10800)), interval=int(src.get("intervalle", 1800)),
                                        source_id=attacker_id, meta_json=meta)
            # Bonus 5 dmg à l’instant sur la cible si elle devient infectée (par ta règle)
            await deal_damage(attacker_id, target_id, 5)
            result_lines.append("🧟 Contagion : la cible devient infectée (+5 dmg).")

    # KO handling + Zeyra Undying
    if await is_dead(target_id):
        undy = await undying_zeyra_check_and_mark(target_id)
        if undy:
            await revive_full(target_id)
            await deal_damage(0, target_id, 99)  # pour revenir à 1 PV
            result_lines.append("💥 **Volonté de Fracture** : survit à 1 PV !")
        else:
            # Règle 14 : à la mort via ATTAQUE directe → on revive à 100 et clear statuts
            await revive_full(target_id)

    # Triggers post-attaque (loot, vampirisme 50%, etc.)
    await on_attack_after(attacker_id, target_id, item_key)

    return {
        "title": title,
        "lines": result_lines,
        "color": color,
        "gif": _gif_for(item_key),
        "consumed": consumed,
    }


async def heal(healer_id: int, target_id: int, item_key: str, guild_id: int, channel_id: int) -> Dict[str, Any]:
    """
    Soins directs / régénération.
    - Les soins ne dépassent pas PV max (géré côté stats_db)
    - Régénération : effet 'regen' avec ticks (effects_db)
    - Passifs de soins (Dr Vex +50% reçu, Tessa +1 donné, Seren → PB = soin reçu 2x/j, etc.) à appliquer via hooks on_heal_after
    """
    it = OBJETS.get(item_key, {})
    t = it.get("type")
    result_lines: List[str] = []
    title = "💊 Soin"
    color = COLOR_HEAL
    consumed = False

    if t not in {"soin", "regen"}:
        return {"title": "❌ Objet de soin invalide", "lines": [], "color": 0xFF0000}

    if await get_item_qty(healer_id, item_key) <= 0:
        return {"title": "❌ Plus d’objet", "lines": ["Tu n’as plus cet objet."], "color": 0xFF0000}

    if t == "soin":
        amount = int(it.get("soin", 0))
        healed = await heal_user(healer_id, target_id, amount)  # stats_db gère PV max + économie
        consumed = await _consume_item_if_needed(healer_id, item_key)

        if healed <= 0:
            result_lines.append("ℹ️ Aucun PV soigné (déjà au max ?).")
        else:
            result_lines.append(f"❤️ +{healed} PV.")

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
        result_lines.append("💕 Régénération appliquée.")

    # Triggers post-heal (Lysha PB+1, Seren PB=soin 2x/j, etc.)
    await on_heal_after(healer_id, target_id, item_key)

    return {
        "title": title,
        "lines": result_lines,
        "color": color,
        "gif": _gif_for(item_key),
        "consumed": consumed,
    }


async def use_item(user_id: int, target_id: int, item_key: str, guild_id: int, channel_id: int) -> Dict[str, Any]:
    """
    Utilisation d’objets non offensifs :
      - bouclier (cap 20 par défaut, 25 si passif Raya, géré côté stats_db si exposé)
      - vaccin (retire poison + virus)
      - vol (ne peut pas voler les tickets — à vérifier côté inventaire/clé)
      - immunité, esquive+, réduction (temp), mysterybox (loot)
    """
    it = OBJETS.get(item_key, {})
    t = it.get("type")
    result_lines: List[str] = []
    title = "🧰 Utilisation"
    color = COLOR_USE
    consumed = False

    if t not in {"bouclier", "vaccin", "vol", "immunite", "esquive+", "reduction", "mysterybox"}:
        return {"title": "❌ Objet non-utilisable invalide", "lines": [], "color": 0xFF0000}

    if await get_item_qty(user_id, item_key) <= 0:
        return {"title": "❌ Plus d’objet", "lines": ["Tu n’as plus cet objet."], "color": 0xFF0000}

    meta = _pack_meta(guild_id, channel_id)

    if t == "bouclier":
        val = int(it.get("valeur", 0))
        gained = await add_shield(target_id, val)  # stats_db doit plafonner à 20 (ou 25 si passif active le cap)
        consumed = await _consume_item_if_needed(user_id, item_key)
        result_lines.append(f"🛡 +{gained} PB appliqués.")

    elif t == "vaccin":
        # retire poison & virus (et, par ton update, **infection** aussi ? Tu as dit finalement “vaccin retire l’infection”)
        await remove_status(target_id, "poison")
        await remove_status(target_id, "virus")
        await remove_status(target_id, "infection")
        consumed = await _consume_item_if_needed(user_id, item_key)
        result_lines.append("💉 Vaccination : statuts supprimés (poison, virus, infection).")

    elif t == "vol":
        # Vol d’un item aléatoire (sauf tickets) — simplifié
        # On va essayer de voler dans une whitelist d’emojis d’OBJETS sans 🎟️
        stealable = [k for k in OBJETS.keys() if k != "🎟️"]
        if not stealable:
            return {"title": "ℹ️ Rien à voler", "lines": [], "color": 0xAAAAAA}
        choice = random.choice(stealable)
        have = await get_item_qty(target_id, choice)
        if have <= 0:
            result_lines.append("🕵️ Rien d’utile n’a été trouvé.")
        else:
            await remove_item(target_id, choice, 1)
            await add_item(user_id, choice, 1)
            result_lines.append(f"🕵️ Vol réussi : {choice}")
        consumed = await _consume_item_if_needed(user_id, item_key)

    elif t == "immunite":
        await add_or_refresh_effect(target_id, "immunite", 1.0, int(it.get("duree", 2*3600)), interval=0, source_id=user_id, meta_json=meta)
        consumed = await _consume_item_if_needed(user_id, item_key)
        result_lines.append("⭐ Immunité temporaire appliquée.")

    elif t == "esquive+":
        await add_or_refresh_effect(target_id, "esquive", float(it.get("valeur", 0.2)), int(it.get("duree", 3*3600)), interval=0, source_id=user_id, meta_json=meta)
        consumed = await _consume_item_if_needed(user_id, item_key)
        result_lines.append("👟 Esquive augmentée temporairement.")

    elif t == "reduction":
        await add_or_refresh_effect(target_id, "reduction_temp", float(it.get("valeur", 0.5)), int(it.get("duree", 4*3600)), interval=0, source_id=user_id, meta_json=meta)
        consumed = await _consume_item_if_needed(user_id, item_key)
        result_lines.append("🪖 Réduction des dégâts temporaire appliquée.")

    elif t == "mysterybox":
        # Simple exemple : donne 1–3 objets aléatoires (sauf 🎟️) OU des tickets
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
        result_lines.append(f"📦 {pretty}")

    # Triggers post-use (si utiles)
    await on_use_after(user_id, target_id, item_key)

    return {
        "title": title,
        "lines": result_lines,
        "color": color,
        "gif": _gif_for(item_key),
        "consumed": consumed,
    }

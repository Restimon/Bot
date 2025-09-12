# passifs.py
from __future__ import annotations
import json, math, random, time
from typing import Dict, Any, Optional

import aiosqlite

from personnage import PERSONNAGES, PASSIF_CODE_MAP
from effects_db import (
    add_or_refresh_effect, has_effect, list_effects, remove_effect,
)
from stats_db import get_hp, get_shield, set_shield, heal_user

# economie.add_balance est déjà appelé dans stats_db via deal_damage/heal_user
try:
    from economie import add_balance  # noqa: F401
except Exception:
    async def add_balance(*args, **kwargs):  # fallback neutre
        return

DB_PATH = "gotvalis.sqlite3"

SCHEMA = """
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS player_passives(
  user_id     TEXT PRIMARY KEY,
  code        TEXT NOT NULL,
  meta        TEXT NOT NULL DEFAULT '{}',
  updated_ts  INTEGER NOT NULL DEFAULT 0
);
"""

def _now() -> int: return int(time.time())

# ─────────────────────────────────────────────────────────────
# DB helpers
# ─────────────────────────────────────────────────────────────
async def _init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(SCHEMA)
        await db.commit()

async def _get_row(user_id: int):
    await _init_db()
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT code, meta, updated_ts FROM player_passives WHERE user_id=?",
            (str(user_id),)
        ) as cur:
            return await cur.fetchone()

async def _set_row(user_id: int, code: str, meta: Dict[str, Any]):
    await _init_db()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO player_passives(user_id, code, meta, updated_ts)
               VALUES(?,?,?,?)
               ON CONFLICT(user_id) DO UPDATE SET
                 code=excluded.code, meta=excluded.meta, updated_ts=excluded.updated_ts
            """,
            (str(user_id), code, json.dumps(meta or {}), _now()),
        )
        await db.commit()

def _meta_load(s: str) -> Dict[str, Any]:
    try: return json.loads(s or "{}")
    except: return {}

# ─────────────────────────────────────────────────────────────
# API publique : équiper / lire
# ─────────────────────────────────────────────────────────────
async def set_equipped_from_personnage(user_id: int, personnage_nom: str) -> bool:
    p = PERSONNAGES.get(personnage_nom)
    if not p: return False
    code = PASSIF_CODE_MAP.get(p["passif"]["nom"], "")
    if not code: return False
    await _set_row(user_id, code, {})
    return True

async def set_equipped_code(user_id: int, code: str) -> None:
    await _set_row(user_id, code, {})

async def get_equipped_code(user_id: int) -> Optional[str]:
    row = await _get_row(user_id)
    return row[0] if row else None

# Utilitaires pour /use
async def can_be_stolen(victim_id: int) -> bool:
    """False si la cible est immunisée au vol (Lyss)."""
    return (await get_equipped_code(victim_id)) != "anti_vol_total"

async def maybe_preserve_consumable(attacker_id: int) -> bool:
    """
    Marn Velk — 5% chance de NE PAS consommer l’objet utilisé.
    À appeler dans /fight et /use juste après une conso.
    """
    return (await get_equipped_code(attacker_id)) == "chance_ne_pas_consommer_objet" and (random.random() < 0.05)

# ─────────────────────────────────────────────────────────────
# HOOKS combat — appelés depuis cogs/combat.py
# ─────────────────────────────────────────────────────────────
async def before_damage(attacker_id: int, target_id: int, damage: int, ctx: Dict[str, Any]) -> Dict[str, Any]:
    """
    Pré-traitement dégâts. Retourne un dict "overrides" optionnel :
      - damage (int)          : remplacer la base
      - multiplier (float)    : multiplier les dégâts
      - flat_reduction (int)  : retirer X après mul
      - ignore_all_defense    : True = ignore réduction/PB/immunité (exécution)
      - flags (dict)          : informations pour embed (ex: {"execute": True})
    """
    out: Dict[str, Any] = {}
    code_att = await get_equipped_code(attacker_id)
    code_def = await get_equipped_code(target_id)

    # ----------------- ATTAQUANT -----------------
    # Kevar Rin — +3 dégats si la cible est infectée
    if code_att == "bonus_degats_vs_infectes" and await has_effect(target_id, "infection"):
        out["damage"] = max(0, damage + 3)

    # Varkhel Drayne — +1 dégât / 10 PV perdus (sur l'attaquant)
    if code_att == "bonus_degats_par_10pv_perdus":
        hp, _ = await get_hp(attacker_id)
        bonus = max(0, (100 - hp) // 10)
        out["damage"] = max(0, out.get("damage", damage) + bonus)

    # Le Roi — exécute à 10 PV (ignore tout)
    if code_att == "execute_a_10pv_ignores_et_heal":
        thp, _ = await get_hp(target_id)
        if thp <= 10:
            out["ignore_all_defense"] = True
            out["damage"] = max(1, out.get("damage", damage))
            out["flags"] = {"execute": True}

    # Abomination Rampante — +30% dégats si cible déjà infectée
    if code_att == "infection_chance_et_bonus_vs_infecte_kill_heal" and await has_effect(target_id, "infection"):
        out["multiplier"] = float(out.get("multiplier", 1.0)) * 1.30

    # ----------------- DÉFENSEUR -----------------
    # Cielya — -25% si la cible a un PB
    if code_def == "reduc_degats_si_pb":
        if (await get_shield(target_id)) > 0:
            out["multiplier"] = float(out.get("multiplier", 1.0)) * 0.75

    # Darin / (Alen via même code) — 10% moitié dégâts
    if code_def == "chance_reduc_moitie_degats" and random.random() < 0.10:
        out["multiplier"] = float(out.get("multiplier", 1.0)) * 0.5

    # Veylor — -1 plat + 50% chance -2 supplémentaires
    if code_def == "reduc_degats_fixe_et_chance_sup":
        red = 1 + (2 if random.random() < 0.5 else 0)
        out["flat_reduction"] = int(out.get("flat_reduction", 0)) + red

    # Zeyra — réduction plate -1 (le x0.5 sur CRIT est géré côté combat si tu actives son mod critique)
    if code_def == "undying_1pv_jour_scaling_dmg_half_crit_flat_reduc":
        out["flat_reduction"] = int(out.get("flat_reduction", 0)) + 1

    # Neyra — -10% permanent
    if code_def == "reduc_degats_perma_et_stacks":
        out["multiplier"] = float(out.get("multiplier", 1.0)) * 0.90

    return out

async def after_damage(attacker_id: int, target_id: int, summary: Dict[str, Any]) -> None:
    """
    Post-traitement après application des dégâts (directs):
    summary = {
      "emoji": str, "type": str,
      "damage": int, "absorbed": int,
      "target_hp": int, "target_shield": int,
      "killed": bool
    }
    """
    code_att = await get_equipped_code(attacker_id)
    code_def = await get_equipped_code(target_id)
    dmg = int(summary.get("damage", 0))
    killed = bool(summary.get("killed", False))
    typ = summary.get("type", "")

    # Cassiane — +1% reduc 24h par attaque reçue (stack, cap soft à 90%)
    if code_def == "stack_resistance_par_attaque":
        cur = 0.0
        for et, val, *_ in await list_effects(target_id):
            if et == "reduction":
                try: cur = float(val)
                except: cur = 0.0
        cur = min(0.90, cur + 0.01)
        await add_or_refresh_effect(target_id, "reduction", cur, 24 * 3600)

    # Liora — 25% : +3% esquive 24h
    if code_def == "buff_esquive_apres_coup" and random.random() < 0.25:
        ev = 0.0
        for et, val, *_ in await list_effects(target_id):
            if et == "esquive":
                try: ev = float(val)
                except: ev = 0.0
        ev = min(0.95, ev + 0.03)
        await add_or_refresh_effect(target_id, "esquive", ev, 24 * 3600)

    # Kael Dris — vampirisme 50% des dégâts infligés
    if code_att == "vampirisme_50pct" and dmg > 0:
        await heal_user(attacker_id, attacker_id, dmg // 2)

    # Yann Tann — 10% : applique brûlure (1 dmg/heure pendant 3h)
    if code_att == "chance_brule_1h_x3" and typ.startswith("attaque") and random.random() < 0.10:
        await add_or_refresh_effect(target_id, "brulure", 1, 3 * 3600, interval=3600, source_id=attacker_id)

    # Neyra — sur CHAQUE attaque reçue : -5% dégâts reçus (temp 1h, stack) +3% esquive (1h, stack)
    if code_def == "reduc_degats_perma_et_stacks":
        # reduc stack temporaire
        rcur = 0.0
        for et, val, *_ in await list_effects(target_id):
            if et == "reduction_temp":
                try: rcur = float(val)
                except: rcur = 0.0
        rcur = min(0.50, rcur + 0.05)  # cap 50% temp
        await add_or_refresh_effect(target_id, "reduction_temp", rcur, 3600)
        # esquive stack
        ecur = 0.0
        for et, val, *_ in await list_effects(target_id):
            if et == "esquive":
                try: ecur = float(val)
                except: ecur = 0.0
        ecur = min(0.95, ecur + 0.03)
        await add_or_refresh_effect(target_id, "esquive", ecur, 3600)

    # Valen — seuils 40/30/20/10 : à chaque palier franchi: +5 PB & +10% reduc (stack)
    if code_def == "drastique_reduc_chance_scaling_pb_dr_immune":
        row = await _get_row(target_id); meta = _meta_load(row[1]) if row else {}
        hit = set(meta.get("valen_hit", []))
        hp_now, _ = await get_hp(target_id)
        for seuil in (40, 30, 20, 10):
            if hp_now <= seuil and seuil not in hit:
                # +5 PB
                cur_pb = await get_shield(target_id)
                await set_shield(target_id, cur_pb + 5)
                # +10% reduc cumul
                r = 0.0
                for et, val, *_ in await list_effects(target_id):
                    if et == "reduction_valen":
                        try: r = float(val)
                        except: r = 0.0
                r = min(0.75, r + 0.10)
                await add_or_refresh_effect(target_id, "reduction_valen", r, 24 * 3600)
                hit.add(seuil)
        meta["valen_hit"] = sorted(list(hit))
        await _set_row(target_id, "drastique_reduc_chance_scaling_pb_dr_immune", meta)

    # Kills — effets on-kill spécifiques
    if killed:
        # Abomination — +3 PV
        if code_att == "infection_chance_et_bonus_vs_infecte_kill_heal":
            await heal_user(attacker_id, attacker_id, 3)
        # Le Roi — +10 PV si l’exécution a tué
        if code_att == "execute_a_10pv_ignores_et_heal":
            await heal_user(attacker_id, attacker_id, 10)

async def on_heal(healer_id: int, target_id: int, healed_amount: int, ctx: Dict[str, Any]) -> Optional[int]:
    """
    Modifie la valeur à soigner.
    Retourne la nouvelle valeur (int) ou None pour inchangé.
    """
    code_h = await get_equipped_code(healer_id)
    code_t = await get_equipped_code(target_id)
    base = int(healed_amount)

    # Tessa — +1 sur soins prodigués
    if code_h == "soins_plus_un":
        base += 1

    # Aelran — +50% sur soins reçus
    if code_t == "soin_recu_x1_5":
        base = int(math.ceil(base * 1.5))

    # Lysha — le soigneur gagne +1 PB
    if code_h == "gain_pb_quand_soigne":
        cur = await get_shield(healer_id)
        await set_shield(healer_id, cur + 1)

    # Kerin — 5% se soigne de 1
    if code_h == "chance_self_heal_si_soin_autrui" and random.random() < 0.05:
        await heal_user(healer_id, healer_id, 1)

    # Seren — 2x/j : convertit les PV soignés en PB
    if code_t == "pb_egal_soin_limite" and base > 0:
        row = await _get_row(target_id); meta = _meta_load(row[1]) if row else {}
        day = _now() // 86400
        if meta.get("seren_day") != day:
            meta["seren_day"] = day
            meta["seren_cnt"] = 0
        if meta.get("seren_cnt", 0) < 2:
            cur_pb = await get_shield(target_id)
            await set_shield(target_id, cur_pb + base)
            meta["seren_cnt"] = meta.get("seren_cnt", 0) + 1
            await _set_row(target_id, "pb_egal_soin_limite", meta)

    return base

async def on_status_apply(source_id: int, target_id: int, eff_type: str, value: float, duration: int, ctx: Dict[str, Any]) -> Dict[str, Any]:
    """
    Permet d’annuler ou modifier un statut à l’application.
    Retourne un dict optionnel: {"value": X, "duration": Y}
    """
    out: Dict[str, Any] = {}
    code_src = await get_equipped_code(source_id)
    code_tgt = await get_equipped_code(target_id)

    # Dr Elwin Kaas — immun au POISON
    if eff_type == "poison" and code_tgt == "pb_plus_un_par_heure_anti_poison":
        out["value"] = 0; out["duration"] = 0
        return out

    # Valen Drexar — immun à TOUS les statuts (poison, virus, infection, regen, brulure...)
    if code_tgt == "drastique_reduc_chance_scaling_pb_dr_immune":
        out["value"] = 0; out["duration"] = 0
        return out

    # Anna — +1 dégâts sur l'INFECTION appliquée
    if eff_type == "infection" and code_src == "infection_buff_source_pas_degats":
        out["value"] = max(0, int(value) + 1)

    return out

async def on_kill(attacker_id: int, target_id: int, ctx: Dict[str, Any]) -> None:
    # (déjà traité les heals/bonus dans after_damage)
    return

async def on_death(target_id: int, attacker_id: int, ctx: Dict[str, Any]) -> None:
    # (le Undying de Zeyra est géré par try_undying() appelé dans combat avant revive)
    return

# Cap PB dynamique (Raya 25 max)
async def modify_shield_cap_async(user_id: int, default_cap: int) -> int:
    code = await get_equipped_code(user_id)
    if code == "max_pb_25":
        return max(default_cap, 25)
    return default_cap

# ─────────────────────────────────────────────────────────────
# UNDYING (Zeyra) & crit modifiers — helpers pour combat
# ─────────────────────────────────────────────────────────────
async def try_undying(user_id: int) -> bool:
    """
    Zeyra Kael — 1 fois / jour :
    Si la cible allait mourir, annule le KO et la laisse à 1 PV.
    Retourne True si la mort doit être ANNULÉE (donc NE PAS revive/clean).
    """
    code = await get_equipped_code(user_id)
    if code != "undying_1pv_jour_scaling_dmg_half_crit_flat_reduc":
        return False

    row = await _get_row(user_id); meta = _meta_load(row[1]) if row else {}
    day = _now() // 86400
    if meta.get("zeyra_day") == day and meta.get("zeyra_used", 0) >= 1:
        return False  # déjà utilisé aujourd'hui

    # place/maintient à 1 PV
    hp, _ = await get_hp(user_id)
    if hp <= 0:
        await heal_user(user_id, user_id, 1)
    meta["zeyra_day"] = day
    meta["zeyra_used"] = 1
    await _set_row(user_id, code, meta)
    return True

def crit_multiplier_against_defender_code(defender_code: Optional[str]) -> float:
    """
    Si la DEFENSEURE est Zeyra, les coups critiques subis sont divisés par 2.
    À utiliser côté combat pour ajuster le multiplicateur de crit avant d'appliquer les dégâts.
    """
    if defender_code == "undying_1pv_jour_scaling_dmg_half_crit_flat_reduc":
        return 0.5
    return 1.0

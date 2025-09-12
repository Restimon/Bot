# passifs.py
from __future__ import annotations
import json
import math
import random
import time
from typing import Dict, Any, Optional, Tuple

import aiosqlite

from personnage import PERSONNAGES, PASSIF_CODE_MAP
from effects_db import add_or_refresh_effect, get_effect, has_effect, remove_effect, list_effects
from stats_db import (
    get_hp, get_shield, set_shield,
    heal_user, deal_damage,
)
# (optionnel) économie si certains passifs donnent des coins
try:
    from economie import add_balance  # add_balance(user_id, delta)
except Exception:
    async def add_balance(user_id: int, delta: int) -> None:
        return

DB_PATH = "gotvalis.sqlite3"

SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS player_passives(
  user_id   TEXT PRIMARY KEY,
  code      TEXT NOT NULL,       -- ex: 'max_pb_25'
  meta      TEXT NOT NULL DEFAULT '{}', -- compteurs journaliers, flags, etc.
  updated_ts INTEGER NOT NULL DEFAULT 0
);
"""

# ─────────────────────────────────────────────────────────────
# Utils internes
# ─────────────────────────────────────────────────────────────
def _now() -> int:
    return int(time.time())

async def _init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(SCHEMA)
        await db.commit()

async def _get_row(user_id: int) -> Optional[Tuple[str, str, int]]:
    await _init_db()
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT code, meta, updated_ts FROM player_passives WHERE user_id=?",
            (str(user_id),),
        ) as cur:
            row = await cur.fetchone()
    return row if row else None

async def _set_row(user_id: int, code: str, meta: Dict[str, Any]):
    await _init_db()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO player_passives(user_id, code, meta, updated_ts) VALUES(?,?,?,?)
            ON CONFLICT(user_id) DO UPDATE SET code=excluded.code, meta=excluded.meta, updated_ts=excluded.updated_ts
            """,
            (str(user_id), code, json.dumps(meta or {}), _now()),
        )
        await db.commit()

def _parse_meta(meta: str) -> Dict[str, Any]:
    try:
        return json.loads(meta or "{}")
    except Exception:
        return {}

# ─────────────────────────────────────────────────────────────
# API publique — gestion d’équipement
# ─────────────────────────────────────────────────────────────
async def set_equipped_from_personnage(user_id: int, personnage_nom: str) -> bool:
    """Enregistre le passif équipé selon le nom du personnage (via PASSIF_CODE_MAP)."""
    p = PERSONNAGES.get(personnage_nom)
    if not p:
        return False
    code = PASSIF_CODE_MAP.get(p["passif"]["nom"], "")
    if not code:
        return False
    await _set_row(user_id, code, {})
    return True

async def set_equipped_code(user_id: int, code: str) -> None:
    """Force un code (debug/admin)."""
    await _set_row(user_id, code, {})

async def get_equipped_code(user_id: int) -> Optional[str]:
    row = await _get_row(user_id)
    return row[0] if row else None

# ─────────────────────────────────────────────────────────────
# Helpers utilitaires exportés (pour /use, vol, etc.)
# ─────────────────────────────────────────────────────────────
async def can_be_stolen(victim_id: int) -> bool:
    """Lyss Tenra — anti vol total."""
    code = await get_equipped_code(victim_id)
    return code != "anti_vol_total"

async def maybe_preserve_consumable(attacker_id: int) -> bool:
    """
    Marn Velk — 5% de chance de NE PAS consommer l’objet utilisé.
    (À utiliser côté /fight et /use juste avant remove_item).
    """
    code = await get_equipped_code(attacker_id)
    if code == "chance_ne_pas_consommer_objet":
        return random.random() < 0.05
    return False

# ─────────────────────────────────────────────────────────────
# HOOKS — utilisés par cogs/combat.py
# (les ctx contiennent au minimum {guild_id, channel_id, emoji, type})
# ─────────────────────────────────────────────────────────────
async def before_damage(attacker_id: int, target_id: int, damage: int, ctx: Dict[str, Any]) -> Dict[str, Any]:
    """
    Peut retourner:
      - {"damage": int} pour écraser les dégâts
      - {"multiplier": float} pour appliquer un multiplicateur
      - {"flat_reduction": int} pour enlever X dégâts (après réduction %)
    """
    code_att = await get_equipped_code(attacker_id)
    code_def = await get_equipped_code(target_id)

    overrides: Dict[str, Any] = {}

    # ---- Attaquant
    # Kevar Rin — +3 dégâts contre infectés
    if code_att == "bonus_degats_vs_infectes":
        if await has_effect(target_id, "infection"):
            overrides["damage"] = max(0, damage + 3)

    # Varkhel Drayne — +1 dégât par 10 PV perdus (arrondi bas)
    if code_att == "bonus_degats_par_10pv_perdus":
        hp, _ = await get_hp(attacker_id)
        bonus = max(0, (100 - hp) // 10)
        overrides["damage"] = max(0, overrides.get("damage", damage) + bonus)

    # ---- Défenseur
    # Cielya Morn — si PB>0 → -25% dégâts (multiplicatif)
    if code_def == "reduc_degats_si_pb":
        if (await get_shield(target_id)) > 0:
            # multiplicateur
            existing = float(overrides.get("multiplier", 1.0))
            overrides["multiplier"] = existing * 0.75

    # Darin Venhal — 10% de chance de réduire de moitié
    if code_def == "chance_reduc_moitie_degats":
        if random.random() < 0.10:
            existing = float(overrides.get("multiplier", 1.0))
            overrides["multiplier"] = existing * 0.5

    # Alen Drave — 5% de chance de réduire de moitié
    if code_def == "chance_reduc_moitie_degats":
        # (même code que Darin — tu peux distinguer si tu préfères)
        if random.random() < 0.05:
            existing = float(overrides.get("multiplier", 1.0))
            overrides["multiplier"] = existing * 0.5

    # Veylor Cassian — -1 dégât fixe, et 50% de chance -2 de plus
    if code_def == "reduc_degats_fixe_et_chance_sup":
        flat = 1 + (2 if random.random() < 0.5 else 0)
        overrides["flat_reduction"] = flat

    return overrides

async def after_damage(attacker_id: int, target_id: int, summary: Dict[str, Any]) -> None:
    """
    summary fourni par combat.py:
      { "emoji": str, "type": str, "damage": int, "absorbed": int,
        "target_hp": int, "target_shield": int, "killed": bool }
    """
    code_att = await get_equipped_code(attacker_id)
    code_def = await get_equipped_code(target_id)

    dmg = int(summary.get("damage", 0))
    killed = bool(summary.get("killed", False))

    # Cassiane Vale — +1% réduction pendant 24h par attaque reçue (stack)
    if code_def == "stack_resistance_par_attaque":
        # on empile dans un effet reduction "privé" (on additionne)
        cur = 0.0
        for et, val, *_ in await list_effects(target_id):
            if et == "reduction":
                try: cur = float(val)
                except: cur = 0.0
        cur = min(0.9, cur + 0.01)  # cap 90% pour éviter les abus
        await add_or_refresh_effect(target_id, "reduction", cur, 24 * 3600)

    # Liora Venhal — 25% chance: +3% esquive 24h
    if code_def == "buff_esquive_apres_coup":
        if random.random() < 0.25:
            # On additionne à l'esquive existante
            cur = 0.0
            for et, val, *_ in await list_effects(target_id):
                if et == "esquive":
                    try: cur = float(val)
                    except: cur = 0.0
            cur = min(0.95, cur + 0.03)
            await add_or_refresh_effect(target_id, "esquive", cur, 24 * 3600)

    # Kael Dris — Vampirisme 50% des dégâts infligés
    if code_att == "vampirisme_50pct":
        heal = max(0, dmg // 2)
        if heal:
            await heal_user(attacker_id, attacker_id, heal)

    # Darn Kol — 10% chance: gagne 1 PV quand il inflige des dégâts
    if code_att == "vampirisme_50pct":  # déjà pris par Kael; Darn = "Éclats utiles ⚙️"
        pass
    if code_att == "stack_resistance_par_attaque":  # nope, mauvaise clé
        pass
    # Darn Kol = Éclats utiles ⚙️  → code non listé; utilisons un code custom:
    # Ajoute-le dans PASSIF_CODE_MAP si tu veux: "Éclats utiles ⚙️": "darn_heal_on_damage"
    if code_att == "darn_heal_on_damage":
        if random.random() < 0.10:
            await heal_user(attacker_id, attacker_id, 1)

    # Sive Arden — 5% chance: +1 coin après une attaque
    if code_att == "trouvaille_coin_5pct":
        if random.random() < 0.05:
            await add_balance(attacker_id, 1)

    # Seren Iskar — PB égal au soin (géré dans on_heal) — compteur 2×/jour
    # (rien ici)

    # Kill hooks simples
    if killed:
        # Abomination Rampante — +3 PV par kill (et autres bonus gérés ailleurs)
        if code_att == "infection_chance_et_bonus_vs_infecte_kill_heal":
            await heal_user(attacker_id, attacker_id, 3)

async def on_heal(healer_id: int, target_id: int, healed_amount: int, ctx: Dict[str, Any]) -> Optional[int]:
    """
    Peut retourner un int pour remplacer le heal final.
    """
    code_healer = await get_equipped_code(healer_id)
    code_target = await get_equipped_code(target_id)

    base = healed_amount

    # Tessa Korrin — +1 PV sur les soins PRODIGUÉS
    if code_healer == "soins_plus_un":
        base += 1

    # Dr Aelran Vex — +50% soins REÇUS
    if code_target == "soin_recu_x1_5":
        base = int(math.ceil(base * 1.5))

    # Lysha Varn — le soigneur gagne +1 PB
    if code_healer == "gain_pb_quand_soigne":
        cur = await get_shield(healer_id)
        await set_shield(healer_id, cur + 1)

    # Kerin Dross — 5% chance: quand il soigne, il se soigne de 1 aussi
    if code_healer == "chance_self_heal_si_soin_autrui":
        if random.random() < 0.05:
            await heal_user(healer_id, healer_id, 1)

    # Seren Iskar — à chaque soin REÇU (direct/regen), gagne autant de PB que PV soignés, **2×/jour**
    if code_target == "pb_egal_soin_limite":
        row = await _get_row(target_id)
        meta = _parse_meta(row[1]) if row else {}
        day = int(time.time() // 86400)
        used_day = meta.get("seren_day", -1)
        used_cnt = meta.get("seren_cnt", 0)
        if used_day != day:
            used_day = day
            used_cnt = 0
        if used_cnt < 2 and base > 0:
            cur = await get_shield(target_id)
            await set_shield(target_id, cur + base)
            used_cnt += 1
        meta["seren_day"] = used_day
        meta["seren_cnt"] = used_cnt
        await _set_row(target_id, code_target, meta)

    return base

async def on_status_apply(source_id: int, target_id: int, eff_type: str, value: float, duration: int, ctx: Dict[str, Any]) -> Dict[str, Any]:
    """
    Peut retourner overrides: {"value": new_value, "duration": new_duration}
    """
    code_src = await get_equipped_code(source_id)
    code_tgt = await get_equipped_code(target_id)

    out: Dict[str, Any] = {}

    # Dr Elwin Kaas — immunisé contre POISON
    if eff_type == "poison" and code_tgt == "pb_plus_un_par_heure_anti_poison":
        # ignorer l'application (en faisant value=0 et dur=0)
        out["value"] = 0
        out["duration"] = 0
        return out

    # Anna Lereux (Hôte Brisé) — quand il infecte, +1 aux dégâts d'infection
    if eff_type == "infection" and code_src == "infection_buff_source_pas_degats":
        out["value"] = max(0, int(value) + 1)

    # (Autres idées: résistance statuts, etc.)

    return out

async def on_kill(attacker_id: int, target_id: int, ctx: Dict[str, Any]) -> None:
    code = await get_equipped_code(attacker_id)

    # Abomination Rampante — +3 PV déjà géré dans after_damage (au moment du kill)
    # Le Roi — heal +10 sur exécution (nécessite logique d’execute; à implémenter dans combat)
    if code == "execute_a_10pv_ignores_et_heal":
        # Si on arrive ici c'est déjà mort, donc on peut donner +10 PV
        await heal_user(attacker_id, attacker_id, 10)

async def on_death(target_id: int, attacker_id: int, ctx: Dict[str, Any]) -> None:
    code = await get_equipped_code(target_id)
    # Zeyra Kael — "undying 1/jour" demanderait d’intercepter AVANT le KO, donc côté combat
    # Ici on ne peut plus empêcher la mort, on ne fait rien.
    return

def modify_shield_cap(user_id: int, default_cap: int) -> int:
    """
    Peut renvoyer un cap PB différent.
    (Raya Nys → 25 PB)
    """
    # Note: sync pour usage direct dans combat; on lit la DB de façon synchrone via loop.run_until_complete ?
    # → plus simple : on garde une valeur par défaut si pas d’event loop; ici, on retourne default car sync.
    # Mieux: on expose aussi une version async si besoin; mais combat nous appelle en sync, donc:
    return default_cap  # (combat appelle cette fonction directement; on ne peut pas await ici)

# Variante ASYNC pour un usage aisé si tu veux changer combat:
async def modify_shield_cap_async(user_id: int, default_cap: int) -> int:
    code = await get_equipped_code(user_id)
    if code == "max_pb_25":
        return max(default_cap, 25)
    return default_cap

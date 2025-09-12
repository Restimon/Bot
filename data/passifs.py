# passifs.py
from __future__ import annotations
import aiosqlite
import random
import datetime
from typing import Optional

from stats_db import get_hp, get_shield
from personnage import PERSONNAGES, PASSIF_CODE_MAP

DB_PATH = "gotvalis.sqlite3"

SCHEMA = """
PRAGMA journal_mode=WAL;

-- Personnage équipé par joueur
CREATE TABLE IF NOT EXISTS player_equipment(
  user_id TEXT PRIMARY KEY,
  char_name TEXT NOT NULL,
  passif_code TEXT NOT NULL
);

-- Compteurs/flags journaliers (ex: undying Zeyra)
CREATE TABLE IF NOT EXISTS passive_counters(
  user_id TEXT NOT NULL,
  key     TEXT NOT NULL,
  value   INTEGER NOT NULL DEFAULT 0,
  day_ymd TEXT NOT NULL,     -- 'YYYY-MM-DD' pour reset quotidien
  PRIMARY KEY(user_id, key)
);
"""

# Codes internes (doivent matcher personnage.PASSIF_CODE_MAP)
CODE_ROI      = PASSIF_CODE_MAP.get("Finisher Royal 👑⚔️") or "execute_a_10pv_ignores_et_heal"
CODE_VALEN    = PASSIF_CODE_MAP.get("Domaine de Contrôle Absolu 🧠") or "drastique_reduc_chance_scaling_pb_dr_immune"
CODE_ZEYRA    = PASSIF_CODE_MAP.get("Volonté de Fracture 💥") or "undying_1pv_jour_scaling_dmg_half_crit_flat_reduc"
CODE_NOVA     = PASSIF_CODE_MAP.get("Réflexes Accélérés 🚗💨") or "bonus_esquive_constant"
CODE_ELIRA    = PASSIF_CODE_MAP.get("Clé du Dédale Miroir 🗝️") or "redirect_si_esquive_et_gain_pb"
CODE_CIELYA   = PASSIF_CODE_MAP.get("Filtrage actif 🎧") or "reduc_degats_si_pb"
CODE_KEVAR    = PASSIF_CODE_MAP.get("Zone propre 🧼") or "bonus_degats_vs_infectes"
CODE_MARN     = PASSIF_CODE_MAP.get("Rémanence d’usage ♻️") or "chance_ne_pas_consommer_objet"
CODE_NATHANIEL= PASSIF_CODE_MAP.get("Aura d’Autorité Absolue 🏛️") or "chance_reduc_moitie_malus_attaquant_resist_status"
CODE_VEYLOR   = PASSIF_CODE_MAP.get("Faveur de l’Hôte 🌙") or "reduc_degats_fixe_et_chance_sup"

# ─────────────────────────────────────────────────────────────
# INIT
# ─────────────────────────────────────────────────────────────

async def init_passifs_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(SCHEMA)
        await db.commit()

# ─────────────────────────────────────────────────────────────
# ÉQUIPEMENT — set/get
# ─────────────────────────────────────────────────────────────

async def set_equipped(user_id: int, char_name: str) -> bool:
    """
    Équipe un personnage pour le joueur. Retourne True si ok.
    char_name doit exister dans PERSONNAGES.
    """
    if char_name not in PERSONNAGES:
        return False
    code = PASSIF_CODE_MAP.get(PERSONNAGES[char_name]["passif"]["nom"], "")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO player_equipment(user_id, char_name, passif_code)
            VALUES(?,?,?)
            ON CONFLICT(user_id) DO UPDATE SET char_name=excluded.char_name, passif_code=excluded.passif_code
            """,
            (str(user_id), char_name, code)
        )
        await db.commit()
    return True

async def get_equipped_name(user_id: int) -> Optional[str]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT char_name FROM player_equipment WHERE user_id=?", (str(user_id),)) as cur:
            row = await cur.fetchone()
    return row[0] if row else None

async def get_equipped_code(user_id: int) -> Optional[str]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT passif_code FROM player_equipment WHERE user_id=?", (str(user_id),)) as cur:
            row = await cur.fetchone()
    return row[0] if row else None

# ─────────────────────────────────────────────────────────────
# HELPERS DIVERS
# ─────────────────────────────────────────────────────────────

def _today_ymd() -> str:
    return datetime.date.today().isoformat()

async def _get_counter(user_id: int, key: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT value, day_ymd FROM passive_counters WHERE user_id=? AND key=?",
                              (str(user_id), key)) as cur:
            row = await cur.fetchone()
    if not row:
        return 0
    value, day = row
    if day != _today_ymd():
        # reset quotidien
        await _set_counter(user_id, key, 0)
        return 0
    return int(value)

async def _set_counter(user_id: int, key: str, value: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO passive_counters(user_id, key, value, day_ymd)
            VALUES(?,?,?,?)
            ON CONFLICT(user_id, key) DO UPDATE SET value=excluded.value, day_ymd=excluded.day_ymd
            """,
            (str(user_id), key, int(value), _today_ymd())
        )
        await db.commit()

async def _inc_counter(user_id: int, key: str, inc: int = 1) -> int:
    cur = await _get_counter(user_id, key)
    cur += inc
    await _set_counter(user_id, key, cur)
    return cur

# ─────────────────────────────────────────────────────────────
# HOOKS UTILISÉS PAR combat.py
# ─────────────────────────────────────────────────────────────

def crit_multiplier_against_defender_code(defender_code: Optional[str]) -> float:
    """
    Multiplie le multiplicateur de crit en fonction du passif du défenseur.
    - Zeyra : crit subis sont divisés par 2 → on renvoie 0.5
    Sinon 1.0
    """
    if defender_code == CODE_ZEYRA:
        return 0.5
    return 1.0

async def get_extra_dodge_chance(user_id: int) -> float:
    """
    Chance d'esquive additionnelle (0..1).
    - Nova Rell : +5%
    - Elira Veska : +10%
    (D’autres passifs peuvent s’ajouter plus tard.)
    """
    code = await get_equipped_code(user_id)
    bonus = 0.0
    if code == CODE_NOVA:
        bonus += 0.05
    if code == CODE_ELIRA:
        bonus += 0.10
    # TODO: Liora Venhal: +3% pendant 24h après chaque attaque reçue (nécessite hook post-défense)
    return min(bonus, 0.95)

async def get_extra_reduction_percent(user_id: int) -> float:
    """
    Réduction en % qui s'applique AVANT PB (et ne s'applique pas aux DOT).
    - Cielya Morn : −25% tant qu'il a des PB > 0
    - Nathaniel Raskov : approx simple −10% passif constant (son vrai passif est un proc 50% moitié dégats + malus attaquant 1h)
    - Veylor Cassian : approx simple −10% passif constant (son vrai passif est −1 à −3 PV flat, ici on l’approxime)
    """
    code = await get_equipped_code(user_id)
    bonus = 0.0
    if code == CODE_CIELYA:
        sh = await get_shield(user_id)
        if sh > 0:
            bonus += 0.25
    if code == CODE_NATHANIEL:
        bonus += 0.10  # approximation
    if code == CODE_VEYLOR:
        bonus += 0.10  # approximation
    # D’autres passifs de réduction peuvent s’ajouter ici
    return min(bonus, 0.90)

async def maybe_preserve_consumable(user_id: int, item_key: str) -> bool:
    """
    True => ne consomme pas l’objet (ex: Marn Velk 5%).
    """
    code = await get_equipped_code(user_id)
    if code == CODE_MARN:
        return random.random() < 0.05
    return False

async def king_execute_ready(attacker_id: int, target_id: int) -> bool:
    """
    'Le Roi' : exécute à 10 PV (ignore défenses). True si condition remplie.
    """
    code = await get_equipped_code(attacker_id)
    if code != CODE_ROI:
        return False
    hp, _ = await get_hp(target_id)
    return hp <= 10

async def valen_reduction_bonus(user_id: int) -> float:
    """
    Valen Drexar : quand < 50% PV, gagne +10% de réduction **par tranche de 10 PV perdue**
    parmi les paliers : 40, 30, 20, 10 — cumulatif. Max 40%.
    """
    code = await get_equipped_code(user_id)
    if code != CODE_VALEN:
        return 0.0
    hp, _ = await get_hp(user_id)
    # hp ∈ [0..100] par ton modèle
    if hp >= 50:
        return 0.0
    tiers = 0
    if hp <= 40: tiers += 1
    if hp <= 30: tiers += 1
    if hp <= 20: tiers += 1
    if hp <= 10: tiers += 1
    return min(0.10 * tiers, 0.40)

async def undying_zeyra_check_and_mark(user_id: int) -> bool:
    """
    Zeyra Kael : ne meurt pas une fois par jour → reste à 1 PV.
    Retourne True si le sauvetage s'applique ET consomme la charge du jour.
    """
    code = await get_equipped_code(user_id)
    if code != CODE_ZEYRA:
        return False
    key = "undying_zeyra"
    used = await _get_counter(user_id, key)
    if used >= 1:
        return False
    await _inc_counter(user_id, key, 1)
    return True

async def on_attack_after(attacker_id: int, target_id: int, item_key: str) -> None:
    """
    Post-attaque : place pour déclencher des effets (loot, vampirisme, etc.).
    ⚠️ Le moteur ne passe pas (encore) le montant de dégâts infligés,
       donc certains passifs (ex: Kael Dris vampirisme 50%) demandent une extension d'API.
    TODO (si tu étends `combat.fight` pour renvoyer les dégâts réels):
      - Kael Dris: heal_user(attacker_id, attacker_id, dealt // 2)
      - Sive Arden: 5% chance +1 coin (côté économie)
      - Neyra Velenis: stacks dodge/+reduc 1h (effects_db custom)
      - Roulette de minuit: table d’effets aléatoires
    """
    return

async def on_heal_after(healer_id: int, target_id: int, item_key: str) -> None:
    """
    Post-soin : déclenchements liés aux soins.
    Exemples à brancher si tu passes 'healed' à ce hook :
      - Tessa Korrin: +1 PV aux soins prodigués (à appliquer plutôt AVANT le heal dans combat.py)
      - Seren Iskar: PB égal aux PV soignés, 2x/j (nécessite un compteur & healed amount)
      - Lysha Varn: quand le porteur soigne quelqu’un, il gagne +1 PB.
    """
    # Exemple simple (Lysha Varn) si tu veux activer tout de suite :
    # code = await get_equipped_code(healer_id)
    # if code == PASSIF_CODE_MAP.get("Champ brouillé 📡"):
    #     from stats_db import add_shield
    #     await add_shield(healer_id, 1)
    return

async def on_use_after(user_id: int, target_id: int, item_key: str) -> None:
    """
    Post-use : pour des effets secondaires après /use si nécessaire.
    Ex: Kieran Vox (box +1) devrait plutôt se gérer au moment d’ouvrir la box.
    """
    return

async def bonus_damage_vs_infected(attacker_id: int) -> int:
    """
    Kevar Rin : +3 dégâts contre les infectés.
    """
    code = await get_equipped_code(attacker_id)
    if code == CODE_KEVAR:
        return 3
    return 0

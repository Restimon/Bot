# passifs.py
from __future__ import annotations
import aiosqlite
import random
import datetime
from typing import Optional, Dict, Any

from stats_db import get_hp, get_shield  # autres import dynamiques in-fn pour éviter les cycles
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

-- Compteurs/flags journaliers (ex: undying Zeyra, Seren 2x/j)
CREATE TABLE IF NOT EXISTS passive_counters(
  user_id TEXT NOT NULL,
  key     TEXT NOT NULL,
  value   INTEGER NOT NULL DEFAULT 0,
  day_ymd TEXT NOT NULL,     -- 'YYYY-MM-DD' pour reset quotidien
  PRIMARY KEY(user_id, key)
);
"""

# ─────────────────────────────────────────────────────────────
# Codes internes (doivent matcher personnage.PASSIF_CODE_MAP)
# ─────────────────────────────────────────────────────────────
_code = PASSIF_CODE_MAP.get

CODE_ROI       = _code("Finisher Royal 👑⚔️") or "execute_a_10pv_ignores_et_heal"
CODE_VALEN     = _code("Domaine de Contrôle Absolu 🧠") or "drastique_reduc_chance_scaling_pb_dr_immune"
CODE_ZEYRA     = _code("Volonté de Fracture 💥") or "undying_1pv_jour_scaling_dmg_half_crit_flat_reduc"
CODE_NOVA      = _code("Réflexes Accélérés 🚗💨") or "bonus_esquive_constant"
CODE_ELIRA     = _code("Clé du Dédale Miroir 🗝️") or "redirect_si_esquive_et_gain_pb"
CODE_CIELYA    = _code("Filtrage actif 🎧") or "reduc_degats_si_pb"
CODE_KEVAR     = _code("Zone propre 🧼") or "bonus_degats_vs_infectes"
CODE_MARN      = _code("Rémanence d’usage ♻️") or "chance_ne_pas_consommer_objet"
CODE_NATHANIEL = _code("Aura d’Autorité Absolue 🏛️") or "chance_reduc_moitie_malus_attaquant_resist_status"
CODE_VEYLOR    = _code("Faveur de l’Hôte 🌙") or "reduc_degats_fixe_et_chance_sup"
CODE_LIOR      = _code("Récompense fantôme 📦") or "daily_double_chance"
CODE_NYRA      = _code("Connexion réinitialisée 🧷") or "daily_cd_halved"
CODE_SILIEN    = _code("Marges invisibles 💰") or "plus_un_coin_sur_gains"
CODE_KIERAN    = _code("Bonus de Coursier 📦") or "box_plus_un_objet"
CODE_LYSS      = _code("Intouchable 🛡") or "anti_vol_total"
CODE_SEREN     = _code("Rétro-projection vitale 🔁") or "pb_egal_soin_limite"
CODE_TESSA     = _code("Injection stabilisante 💉") or "soins_plus_un"
CODE_LYSHA     = _code("Champ brouillé 📡") or "gain_pb_quand_soigne"

# ─────────────────────────────────────────────────────────────
# INIT (lazy)
# ─────────────────────────────────────────────────────────────
_init_done = False

async def init_passifs_db() -> None:
    global _init_done
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(SCHEMA)
        await db.commit()
    _init_done = True

async def _ensure_init():
    global _init_done
    if not _init_done:
        await init_passifs_db()

# ─────────────────────────────────────────────────────────────
# ÉQUIPEMENT — set/get
# ─────────────────────────────────────────────────────────────
async def set_equipped(user_id: int, char_name: str) -> bool:
    """
    Équipe un personnage pour le joueur. Retourne True si ok.
    char_name doit exister dans PERSONNAGES.
    """
    await _ensure_init()
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

async def set_equipped_from_personnage(user_id: int, char_name: str) -> bool:
    """Alias pratique utilisé par le cog : nom exact → équipe."""
    return await set_equipped(user_id, char_name)

async def get_equipped_name(user_id: int) -> Optional[str]:
    await _ensure_init()
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT char_name FROM player_equipment WHERE user_id=?", (str(user_id),)) as cur:
            row = await cur.fetchone()
    return row[0] if row else None

async def get_equipped_code(user_id: int) -> Optional[str]:
    await _ensure_init()
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
    await _ensure_init()
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT value, day_ymd FROM passive_counters WHERE user_id=? AND key=?",
                              (str(user_id), key)) as cur:
            row = await cur.fetchone()
    if not row:
        return 0
    value, day = row
    if day != _today_ymd():
        await _set_counter(user_id, key, 0)  # reset quotidien
        return 0
    return int(value)

async def _set_counter(user_id: int, key: str, value: int) -> None:
    await _ensure_init()
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
# HOOKS UTILISÉS EN COMBAT (helpers)
# ─────────────────────────────────────────────────────────────
def crit_multiplier_against_defender_code(defender_code: Optional[str]) -> float:
    """Zeyra : crit subis divisés par 2 → 0.5, sinon 1.0"""
    if defender_code == CODE_ZEYRA:
        return 0.5
    return 1.0

async def get_extra_dodge_chance(user_id: int) -> float:
    """Chance d'esquive additionnelle (0..1). Nova +5%, Elira +10%."""
    code = await get_equipped_code(user_id)
    bonus = 0.0
    if code == CODE_NOVA:
        bonus += 0.05
    if code == CODE_ELIRA:
        bonus += 0.10
    return min(bonus, 0.95)

async def get_extra_reduction_percent(user_id: int) -> float:
    """
    Réduction en % avant PB (pas pour DOT).
    - Cielya : −25% si PB>0
    - Nathaniel : approx −10% constant
    - Veylor : approx −10% constant
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
    return min(bonus, 0.90)

async def maybe_preserve_consumable(user_id: int, item_key: str) -> bool:
    """Marn Velk 5% → ne pas consommer l’objet."""
    code = await get_equipped_code(user_id)
    if code == CODE_MARN:
        return random.random() < 0.05
    return False

async def king_execute_ready(attacker_id: int, target_id: int) -> bool:
    """Le Roi : exécute à 10 PV (ignore défenses)."""
    code = await get_equipped_code(attacker_id)
    if code != CODE_ROI:
        return False
    hp, _ = await get_hp(target_id)
    return hp <= 10

async def valen_reduction_bonus(user_id: int) -> float:
    """
    Valen : sous 50% PV, +10% de réduction cumulatif aux paliers 40/30/20/10 (max 40%).
    """
    code = await get_equipped_code(user_id)
    if code != CODE_VALEN:
        return 0.0
    hp, _ = await get_hp(user_id)
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
    Zeyra : ne meurt pas une fois par jour → reste à 1 PV.
    True si le sauvetage s'applique et consomme la charge.
    """
    code = await get_equipped_code(user_id)
    if code != CODE_ZEYRA:
        return False
    used = await _get_counter(user_id, "undying_zeyra")
    if used >= 1:
        return False
    await _inc_counter(user_id, "undying_zeyra", 1)
    return True

async def bonus_damage_vs_infected(attacker_id: int) -> int:
    """Kevar Rin : +3 dégâts contre les infectés (à appliquer si la cible est infectée côté moteur)."""
    code = await get_equipped_code(attacker_id)
    if code == CODE_KEVAR:
        return 3
    return 0

# ─────────────────────────────────────────────────────────────
# DISPATCHER D’ÉVÉNEMENTS (utilisé par les cogs)
# trigger(event, **ctx) → dict (selon l’event)
# ─────────────────────────────────────────────────────────────
async def trigger(event: str, **ctx) -> Dict[str, Any]:
    """
    Événements supportés et retour :
      • on_gain_coins(user_id, delta>0) -> {"extra": int}
      • on_daily(user_id, rewards:dict, cooldown:int) -> {"rewards": dict, "cooldown": int}
      • on_box_open(user_id) -> {"extra_items": int}
      • on_theft_attempt(attacker_id, target_id) -> {"blocked": bool, "reason": str}
      • on_attack(attacker_id, target_id, damage_done:int) -> {}
      • on_heal_pre(healer_id, target_id, amount:int) -> {"heal_bonus": int}
      • on_heal(healer_id, target_id, healed:int) -> {}
    """
    # ── Sélection de l’event
    if event == "on_gain_coins":
        user_id = int(ctx.get("user_id"))
        delta   = int(ctx.get("delta", 0))
        if delta <= 0:
            return {}
        code = await get_equipped_code(user_id)
        extra = 0
        if code == CODE_SILIEN:
            extra += 1  # +1 pièce sur tout gain positif
        # (Tu peux ajouter ici d’autres bonus génériques d’argent)
        return {"extra": extra}

    elif event == "on_daily":
        user_id   = int(ctx.get("user_id"))
        rewards   = dict(ctx.get("rewards") or {})  # attendu: {"coins": int, "tickets": int, "items": List[str]}
        cooldown  = int(ctx.get("cooldown", 0))
        code = await get_equipped_code(user_id)

        # Nyra Kell : CD ÷2
        if code == CODE_NYRA and cooldown > 0:
            cooldown = max(0, cooldown // 2)

        # Lior Danen : 5% de chance de doubler les récompenses
        if code == CODE_LIOR and random.random() < 0.05:
            if "coins" in rewards:   rewards["coins"] = int(rewards["coins"]) * 2
            if "tickets" in rewards: rewards["tickets"] = int(rewards["tickets"]) * 2
            if "items" in rewards and isinstance(rewards["items"], list):
                rewards["items"] = rewards["items"] + rewards["items"]  # duplique la liste

        return {"rewards": rewards, "cooldown": cooldown}

    elif event == "on_box_open":
        user_id = int(ctx.get("user_id"))
        code = await get_equipped_code(user_id)
        if code == CODE_KIERAN:
            return {"extra_items": 1}
        return {}

    elif event == "on_theft_attempt":
        """Retourne blocked=True si la cible est intouchable (Lyss)."""
        attacker_id = int(ctx.get("attacker_id"))
        target_id   = int(ctx.get("target_id"))
        # on vérifie le code de la cible
        t_code = await get_equipped_code(target_id)
        if t_code == CODE_LYSS:
            return {"blocked": True, "reason": "La cible est intouchable (anti-vol total)."}
        return {"blocked": False}

    elif event == "on_attack":
        """Kael Dris : vampirisme 50% des dégâts infligés."""
        attacker_id = int(ctx.get("attacker_id"))
        dmg_done    = int(ctx.get("damage_done", 0))
        code = await get_equipped_code(attacker_id)
        if code == _code("Rétribution organique 🩸") or code == "vampirisme_50pct":
            if dmg_done > 0:
                from stats_db import heal_user  # import tardif
                await heal_user(attacker_id, attacker_id, max(1, dmg_done // 2))
        return {}

    elif event == "on_heal_pre":
        """Tessa Korrin : +1 PV aux soins prodigués (avant application)."""
        healer_id = int(ctx.get("healer_id"))
        code = await get_equipped_code(healer_id)
        if code == CODE_TESSA:
            return {"heal_bonus": 1}
        return {"heal_bonus": 0}

    elif event == "on_heal":
        """
        Seren Iskar : PB = PV soignés, 2×/jour.
        Lysha Varn : quand le porteur soigne quelqu’un, il gagne +1 PB.
        """
        healer_id = int(ctx.get("healer_id"))
        target_id = int(ctx.get("target_id"))
        healed    = int(ctx.get("healed", 0))
        code = await get_equipped_code(healer_id)

        # Lysha : +1 PB au soigneur s’il soigne quelqu’un
        if code == CODE_LYSHA:
            from stats_db import add_shield  # import tardif
            await add_shield(healer_id, 1)

        # Seren : 2 fois par jour → PB égal au soin
        if code == CODE_SEREN and healed > 0:
            used = await _get_counter(healer_id, "seren_pb_applied")
            if used < 2:
                from stats_db import add_shield
                await add_shield(target_id, healed)
                await _inc_counter(healer_id, "seren_pb_applied", 1)
        return {}

    # Event inconnu → rien
    return {}

# ─────────────────────────────────────────────────────────────
# Fin du module
# ─────────────────────────────────────────────────────────────

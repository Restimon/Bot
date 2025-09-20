# passifs.py
from __future__ import annotations

import aiosqlite
import random
import datetime
from typing import Optional, Dict, Any, List, Tuple

# Imports "tardifs" (dans les fonctions) pour éviter les cycles:
# - from stats_db import get_hp, get_shield, heal_user, add_shield
# - from effects_db import add_or_refresh_effect, remove_effect, list_effects, has_effect
# - from economy_db import add_balance
# - from inventory_db import add_item, remove_item, get_item_qty
# - from utils import OBJETS

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
# Codes internes (via PASSIF_CODE_MAP) — alias pratiques
# ─────────────────────────────────────────────────────────────
_code = PASSIF_CODE_MAP.get

# Commun (Gouvernement)
CODE_CASSIANE   = _code("Éloquence officielle 🕊️") or "stack_resistance_par_attaque"
CODE_DARIN      = _code("Volonté mal orientée 💼") or "chance_reduc_moitie_degats"
CODE_ELWIN_JARR = _code("Archivage parfait 📑") or "vol_double_chance"
CODE_LIORA      = _code("Protection implicite 👑") or "buff_esquive_apres_coup"
CODE_MAELIS     = _code("Mémoire d'État 📚") or "purge_chance_horaire"

# Commun (Citoyens)
CODE_LIOR       = _code("Récompense fantôme 📦") or "daily_double_chance"
CODE_NAEL       = _code("Écho de Grâce 🎁") or "boost_rarete_prochain_tirage"
CODE_NIV        = _code("Vol opportuniste 🪙") or "double_vol_niv_kress"
CODE_LYSS       = _code("Intouchable 🛡") or "anti_vol_total"
CODE_MIRA       = _code("Éclats recyclés 🔪") or "loot_objet_survie"
CODE_SEL        = _code("Vendeur rusé 💰") or "shop_sell_bonus"

# Commun (GotValis)
CODE_CIELYA     = _code("Filtrage actif 🎧") or "reduc_degats_si_pb"
CODE_KEVAR      = _code("Zone propre 🧼") or "bonus_degats_vs_infectes"
CODE_LYSHA      = _code("Champ brouillé 📡") or "gain_pb_quand_soigne"
CODE_KERIN      = _code("Observation continue 📹") or "chance_self_heal_si_soin_autrui"
CODE_NOVA       = _code("Réflexes Accélérés 🚗💨") or "bonus_esquive_constant"
CODE_RAYA       = _code("Cadence de surcharge 🛡") or "max_pb_25"
CODE_TESSA      = _code("Injection stabilisante 💉") or "soins_plus_un"

# Commun (Hôtel Dormant)
CODE_ALEN       = _code("Bénédiction des Bagages 🧳") or "chance_reduc_moitie_degats"
CODE_VEYLOR     = _code("Faveur de l’Hôte 🌙") or "reduc_degats_fixe_et_chance_sup"

# Commun (La Fracture)
CODE_DARN       = _code("Éclats utiles ⚙️") or "self_heal_on_damage"
CODE_KARA       = _code("Frappe discrète 🗡️") or "bonus_degats_si_cible_<25"
CODE_NEHRA      = _code("Fracture brute 🦴") or "ignore_helmet_33pct"
CODE_LIANE      = _code("Tactique primitive 🔥") or "ignore_helmet_always"
CODE_SIVE       = _code("Trouvaille impromptue 🪙") or "chance_plus1_coin_post_attack"

# Rare (GotValis)
CODE_AELRAN     = _code("Amplificateur vital ⚙️") or "soin_recu_x1_5"
CODE_NYRA       = _code("Connexion réinitialisée 🧷") or "daily_cd_halved"
CODE_KIERAN     = _code("Bonus de Coursier 📦") or "box_plus_un_objet"
CODE_SEREN      = _code("Rétro-projection vitale 🔁") or "pb_egal_soin_limite"

# Rare (Gouvernement)
CODE_SILIEN     = _code("Marges invisibles 💰") or "plus_un_coin_sur_gains"

# Rare (Hôtel Dormant)
CODE_NEYRA_V    = _code("Marque de l’Hôte 📜") or "reduc_degats_perma_et_stacks"
CODE_ROUVEN     = _code("Roulette de minuit 🎲") or "proc_roulette_minuit"

# Rare (Infection)
CODE_ANNA       = _code("Émanation Fétide 🦠") or "infection_buff_source_pas_degats"

# Rare (La Fracture)
CODE_KAEL_DRIS  = _code("Rétribution organique 🩸") or "vampirisme_50pct"
CODE_MARN       = _code("Rémanence d’usage ♻️") or "chance_ne_pas_consommer_objet"
CODE_YANN       = _code("Feu rampant 🔥") or "chance_brule_1h_x3"

# Épique (GotValis)
CODE_ELWIN_KAAS = _code("Interface de Renforcement 🛡️") or "pb_plus_un_par_heure_anti_poison"
CODE_SELINA     = _code("Régénérateur Cellulaire 🌿") or "pv_plus_deux_par_heure_purge_chance"

# Épique (Gouvernement)
CODE_ALPHONSE   = _code("Dividende occulte 🧾") or "chance_double_gain_et_leech"

# Épique (Hôtel Dormant)
CODE_ELIRA      = _code("Clé du Dédale Miroir 🗝️") or "redirect_si_esquive_et_gain_pb"

# Épique (Infection)
CODE_ABOMI      = _code("Abomination Rampante") or "infection_chance_et_bonus_vs_infecte_kill_heal"

# Épique (La Fracture)
CODE_VARKHEL    = _code("Intensification sanglante 🩸") or "bonus_degats_par_10pv_perdus"
CODE_ELYA       = _code("Frénésie chirurgicale ✴️") or "bonus_crit_par_10pv_perdus"

# Légendaires
CODE_ROI        = _code("Finisher Royal 👑⚔️") or "execute_a_10pv_ignores_et_heal"
CODE_VALEN      = _code("Domaine de Contrôle Absolu 🧠") or "drastique_reduc_chance_scaling_pb_dr_immune"
CODE_MAHD       = _code("Règle d’Or de l’Hospitalité 🎩✨") or "annule_ou_contrattaque_resist_esquive_redirect"
CODE_ZEYRA      = _code("Volonté de Fracture 💥") or "undying_1pv_jour_scaling_dmg_half_crit_flat_reduc"

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
# HELPERS DIVERS (compteurs quotidiens)
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
        await _set_counter(user_id, key, 0)
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
# HELPERS UTILISÉS PAR LE MOTEUR (combat/soins/économie)
# ─────────────────────────────────────────────────────────────
def crit_multiplier_against_defender_code(defender_code: Optional[str]) -> float:
    """Zeyra : crit subis ÷2 → 0.5, sinon 1.0."""
    if defender_code == CODE_ZEYRA:
        return 0.5
    return 1.0

async def get_extra_dodge_chance(user_id: int) -> float:
    """Nova +5%, Elira +10% (base); d'autres stacks via effets temporaires (effects_db)."""
    code = await get_equipped_code(user_id)
    bonus = 0.0
    if code == CODE_NOVA:
        bonus += 0.05
    if code == CODE_ELIRA:
        bonus += 0.10
    return min(bonus, 0.95)

async def get_extra_reduction_percent(user_id: int) -> float:
    """
    Réduction en % pré-PB (pas pour DOT).
    Cielya −25% si PB>0 ; Nathaniel −10% approx ; Veylor −10% approx ; Maître d’Hôtel −10% approx ; Valen bonus via valen_reduction_bonus.
    """
    code = await get_equipped_code(user_id)
    bonus = 0.0
    if code in (CODE_NATHANIEL, CODE_VEYLOR):
        bonus += 0.10
    if code == CODE_MAHD:
        bonus += 0.10  # approximation globale en plus de ses procs
    if code == CODE_CIELYA:
        from stats_db import get_shield
        sh = await get_shield(user_id)
        if sh > 0:
            bonus += 0.25
    # Valen : bonus additionnel dynamique (via valen_reduction_bonus)
    bonus += await valen_reduction_bonus(user_id)
    return min(bonus, 0.90)

async def get_heal_received_multiplier(user_id: int) -> float:
    """Dr Aelran Vex : soins reçus ×1.5"""
    code = await get_equipped_code(user_id)
    return 1.5 if code == CODE_AELRAN else 1.0

async def get_max_pb_cap(user_id: int, default_cap: int = 20) -> int:
    """Raya Nys : cap PB = 25."""
    code = await get_equipped_code(user_id)
    if code == CODE_RAYA:
        return max(default_cap, 25)
    return default_cap

async def get_damage_bonus_from_missing_hp(user_id: int) -> int:
    """Varkhel Drayne : +1 dégât / 10 PV manquants."""
    code = await get_equipped_code(user_id)
    if code != CODE_VARKHEL:
        return 0
    from stats_db import get_hp
    hp, _ = await get_hp(user_id)
    missing = max(0, 100 - int(hp))
    return missing // 10

async def get_crit_bonus_from_missing_hp(user_id: int) -> float:
    """Elya Varnis : +2% crit / 10 PV manquants (cap 30%)."""
    code = await get_equipped_code(user_id)
    if code != CODE_ELYA:
        return 0.0
    from stats_db import get_hp
    hp, _ = await get_hp(user_id)
    missing = max(0, 100 - int(hp))
    return min(0.02 * (missing // 10), 0.30)

async def valen_reduction_bonus(user_id: int) -> float:
    """Valen : <50% PV, +10% DR aux paliers 40/30/20/10 (max 40%)."""
    code = await get_equipped_code(user_id)
    if code != CODE_VALEN:
        return 0.0
    from stats_db import get_hp
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
    """Zeyra : 1×/jour, laisse à 1 PV au lieu de mourir."""
    code = await get_equipped_code(user_id)
    if code != CODE_ZEYRA:
        return False
    used = await _get_counter(user_id, "undying_zeyra")
    if used >= 1:
        return False
    await _inc_counter(user_id, "undying_zeyra", 1)
    return True

async def maybe_preserve_consumable(user_id: int, item_key: str) -> bool:
    """Marn Velk 5% : ne pas consommer l’objet utilisé."""
    code = await get_equipped_code(user_id)
    if code == CODE_MARN:
        return random.random() < 0.05
    return False

async def bonus_damage_vs_infected(attacker_id: int) -> int:
    """Kevar Rin : +3 dégâts contre les infectés (si cible est infectée à vérifier côté moteur)."""
    code = await get_equipped_code(attacker_id)
    return 3 if code == CODE_KEVAR else 0

# Immunités/blocks d’effets au moment d’appliquer un statut
async def trigger_on_effect_pre_apply(user_id: int, eff_type: str) -> dict:
    """
    Retourne {"blocked": bool, "reason": str}
    - Dr Elwin Kaas : immunisé poison
    - Valen : immunisé à tous statuts
    - Nathaniel : 5% de résistance aux statuts (block chance)
    """
    code = await get_equipped_code(user_id)
    if code == CODE_ELWIN_KAAS and eff_type == "poison":
        return {"blocked": True, "reason": "Immunisé au poison."}
    if code == CODE_VALEN:
        return {"blocked": True, "reason": "Immunisé aux statuts."}
    if code == CODE_NATHANIEL and random.random() < 0.05:
        return {"blocked": True, "reason": "Résistance aux statuts (5%)."}
    return {"blocked": False}

# Abomination / Anna : infectés mais ne subissent pas les dégâts d’infection
async def should_block_infection_tick_damage(user_id: int) -> bool:
    code = await get_equipped_code(user_id)
    return code in (CODE_ABOMI, CODE_ANNA)

# ─────────────────────────────────────────────────────────────
# DISPATCHER D’ÉVÉNEMENTS
# trigger(event, **ctx) → dict (variables à exploiter par les cogs/moteur)
# ─────────────────────────────────────────────────────────────
async def trigger(event: str, **ctx) -> Dict[str, Any]:
    """
    Événements supportés (retours attendus) :

      • on_gain_coins(user_id, delta>0)
          -> {"extra": int}

      • on_daily(user_id, rewards:dict{"coins","tickets","items"}, cooldown:int)
          -> {"rewards": dict, "cooldown": int}

      • on_box_open(user_id)
          -> {"extra_items": int}

      • on_theft_attempt(attacker_id, target_id)
          -> {"blocked": bool, "reason": str}

      • on_theft_success(attacker_id, target_id)
          -> {"extra_steal": int}     # tenter un vol supplémentaire

      • on_use_item(user_id, item_emoji, item_type)
          -> {"dont_consume": bool}   # pour Marn, ou Rouven (option)

      • on_gacha_roll(user_id, rarity:str in ["Commun","Rare","Épique","Légendaire"])
          -> {"rarity": str}          # possibilité de booster la rareté

      • on_attack_pre(attacker_id, target_id)
          -> {"bonus_damage": int, "ignore_helmet": bool, "ignore_helmet_chance": float, "infect_chance_bonus": float, "vs_infected_bonus_pct": float}

      • on_attack(attacker_id, target_id, damage_done:int, item_emoji:str|None)
          -> {"roulette": dict, ...}  # effets post-dégâts, Kael vampirisme, Yann brûlure, Sive +1 coin

      • on_kill(attacker_id, target_id, damage_last:int)
          -> {}  # soins, etc.

      • on_heal_pre(healer_id, target_id, amount:int)
          -> {"heal_bonus": int, "mult_target": float}

      • on_heal(healer_id, target_id, healed:int)
          -> {}

      • on_any_heal(healer_id, target_id, healed:int)
          -> {}  # pour Kerin (5% self heal)

      • on_effect_pre_apply(user_id, eff_type:str)
          -> {"blocked": bool, "reason": str}

      • on_defense_pre(defender_id, attacker_id, incoming:int)
          -> {"cancel": bool, "half": bool, "flat_reduce": int}

      • on_defense_after(defender_id, attacker_id, final_taken:int, dodged:bool)
          -> {"redirect": bool, "redirect_gain_pb": int}

      • on_hourly_tick(user_id)
          -> {}  # ticks : +PB, +PV, purge chance, etc.

      • on_half_hour_tick(user_id)
          -> {}
    """
    # 1) Argent
    if event == "on_gain_coins":
        user_id = int(ctx.get("user_id"))
        delta   = int(ctx.get("delta", 0))
        if delta <= 0:
            return {}
        code = await get_equipped_code(user_id)
        extra = 0

        # Silien Dorr: +1 pièce
        if code == CODE_SILIEN:
            extra += 1

        # Alphonse Kaedrin: 10% double + +10% bonus
        if code == CODE_ALPHONSE:
            if random.random() < 0.10:
                extra += delta  # double
            # +10% arrondi sup.
            import math
            extra += max(1, math.ceil(delta * 0.10))

        return {"extra": int(extra)}

    # 2) Daily
    elif event == "on_daily":
        user_id   = int(ctx.get("user_id"))
        rewards   = dict(ctx.get("rewards") or {})
        cooldown  = int(ctx.get("cooldown", 0))
        code = await get_equipped_code(user_id)

        # Nyra Kell: CD ÷2
        if code == CODE_NYRA and cooldown > 0:
            cooldown = max(0, cooldown // 2)

        # Lior Danen: 5% double total
        if code == CODE_LIOR and random.random() < 0.05:
            if "coins" in rewards:   rewards["coins"]   = int(rewards["coins"]) * 2
            if "tickets" in rewards: rewards["tickets"] = int(rewards["tickets"]) * 2
            if "items" in rewards and isinstance(rewards["items"], list):
                rewards["items"] = rewards["items"] + rewards["items"]

        return {"rewards": rewards, "cooldown": cooldown}

    # 3) Box open (Kieran +1)
    elif event == "on_box_open":
        user_id = int(ctx.get("user_id"))
        code = await get_equipped_code(user_id)
        return {"extra_items": 1} if code == CODE_KIERAN else {}

    # 4) Vol — tentative (Lyss protège)
    elif event == "on_theft_attempt":
        attacker_id = int(ctx.get("attacker_id"))
        target_id   = int(ctx.get("target_id"))
        t_code = await get_equipped_code(target_id)
        if t_code == CODE_LYSS:
            return {"blocked": True, "reason": "La cible est intouchable (anti-vol total)."}
        return {"blocked": False}

    # 5) Vol — réussite (Elwin Jarr / Niv : vol double 10%)
    elif event == "on_theft_success":
        attacker_id = int(ctx.get("attacker_id"))
        code = await get_equipped_code(attacker_id)
        extra = 0
        if code in (CODE_ELWIN_JARR, CODE_NIV):
            if random.random() < 0.10:
                extra += 1
        return {"extra_steal": extra}

    # 6) Utilisation d’objet (Marn: ne pas consommer)
    elif event == "on_use_item":
        user_id    = int(ctx.get("user_id"))
        item_emoji = str(ctx.get("item_emoji") or "")
        item_type  = str(ctx.get("item_type") or "")
        code = await get_equipped_code(user_id)
        if code == CODE_MARN and random.random() < 0.05:
            return {"dont_consume": True}
        # Rouven "♻️ Ne consomme pas l'objet" peut être géré via on_attack (proc)
        return {"dont_consume": False}

    # 7) Gacha / Invocation (Nael : +1 palier de rareté, 1% de chance)
    elif event == "on_gacha_roll":
        user_id = int(ctx.get("user_id"))
        rarity  = str(ctx.get("rarity") or "Commun")
        code = await get_equipped_code(user_id)
        if code == CODE_NAEL and random.random() < 0.01:
            order = ["Commun", "Rare", "Épique", "Légendaire"]
            try:
                i = order.index(rarity)
                rarity = order[min(i+1, len(order)-1)]
            except ValueError:
                pass
        return {"rarity": rarity}

    # 8) Pré-attaque (bonus/flags avant calcul des dégâts)
    elif event == "on_attack_pre":
        attacker_id = int(ctx.get("attacker_id"))
        target_id   = int(ctx.get("target_id"))
        code = await get_equipped_code(attacker_id)

        bonus_damage = 0
        ignore_helmet = False
        ignore_helmet_chance = 0.0
        infect_chance_bonus = 0.0
        vs_infected_bonus_pct = 0.0

        # Kara Drel : +1 si cible < 25 PV
        if code == CODE_KARA:
            from stats_db import get_hp
            thp, _ = await get_hp(target_id)
            if thp < 25:
                bonus_damage += 1

        # Liane Rekk : ignore casque
        if code == CODE_LIANE:
            ignore_helmet = True

        # Nehra Vask : 33% ignore casque
        if code == CODE_NEHRA:
            ignore_helmet_chance = 0.33

        # Kevar Rin : +3 vs infectés (à ajouter côté moteur si cible a infection)
        if code == CODE_KEVAR:
            vs_infected_bonus_pct = 0.0  # on laisse en "plat" via helper bonus_damage_vs_infected()

        # Abomination : +30% si cible est infectée, +5% chance d'infecter
        if code == CODE_ABOMI:
            vs_infected_bonus_pct = max(vs_infected_bonus_pct, 0.30)
            infect_chance_bonus = 0.05

        return {
            "bonus_damage": int(bonus_damage),
            "ignore_helmet": bool(ignore_helmet),
            "ignore_helmet_chance": float(ignore_helmet_chance),
            "infect_chance_bonus": float(infect_chance_bonus),
            "vs_infected_bonus_pct": float(vs_infected_bonus_pct),
        }

    # 9) Post-attaque (dégâts infligés connus)
    elif event == "on_attack":
        attacker_id = int(ctx.get("attacker_id"))
        target_id   = int(ctx.get("target_id"))
        dealt       = int(ctx.get("damage_done", 0))
        item_emoji  = ctx.get("item_emoji")

        code = await get_equipped_code(attacker_id)

        # Kael Dris : vampirisme 50%
        if code == CODE_KAEL_DRIS and dealt > 0:
            from stats_db import heal_user
            await heal_user(attacker_id, attacker_id, max(1, dealt // 2))

        # Sive Arden : 5% chance +1 coin
        if code == CODE_SIVE and random.random() < 0.05:
            try:
                from economy_db import add_balance
                await add_balance(attacker_id, 1, "sive_proc")
            except Exception:
                pass

        # Darn Kol : 10% chance +1 PV quand il inflige des dégâts
        if code == CODE_DARN and dealt > 0 and random.random() < 0.10:
            try:
                from stats_db import heal_user
                await heal_user(attacker_id, attacker_id, 1)
            except Exception:
                pass

        # Yann Tann : 10% brûlure (1 dmg/h ×3h)
        if code == CODE_YANN and dealt > 0 and random.random() < 0.10:
            try:
                from effects_db import add_or_refresh_effect
                await add_or_refresh_effect(
                    user_id=target_id,
                    eff_type="brulure",
                    value=1,
                    duration=60*60*3,
                    interval=60*60,
                    source_id=attacker_id,
                    meta_json=None
                )
            except Exception:
                pass

        # Rouven Mance : roulette 25%
        roulette = {}
        if code == CODE_ROUVEN and random.random() < 0.25:
            # Choix parmi 7 effets
            choice = random.choice(["+10dmg", "steal", "lifesteal", "+25c", "shield_eq_dmg", "lose_random", "dont_consume"])
            roulette["effect"] = choice

            if choice == "+10dmg":
                roulette["add_damage"] = 10  # à appliquer côté moteur si possible

            elif choice == "steal":
                # Tentative de vol d'un item à la cible (côté moteur: réaliser effectivement le vol)
                roulette["theft_attempt"] = True

            elif choice == "lifesteal":
                if dealt > 0:
                    try:
                        from stats_db import heal_user
                        # la spec disait "❤️ Soigne la cible à hauteur des dégâts infligés" (soin de la cible)
                        await heal_user(target_id, target_id, dealt)
                    except Exception:
                        pass

            elif choice == "+25c":
                try:
                    from economy_db import add_balance
                    await add_balance(attacker_id, 25, "rouven_roulette")
                except Exception:
                    pass

            elif choice == "shield_eq_dmg":
                if dealt > 0:
                    try:
                        from stats_db import add_shield
                        await add_shield(attacker_id, dealt)
                    except Exception:
                        pass

            elif choice == "lose_random":
                # retira 1 objet aléatoire de l'inventaire de l'attaquant
                try:
                    from utils import OBJETS
                    from inventory_db import get_item_qty, remove_item
                    owned = [emo for emo in OBJETS.keys() if (await get_item_qty(attacker_id, emo)) > 0]
                    if owned:
                        emo = random.choice(owned)
                        await remove_item(attacker_id, emo, 1)
                        roulette["lost"] = emo
                except Exception:
                    pass

            elif choice == "dont_consume":
                roulette["dont_consume"] = True  # si le moteur peut, sinon rembourser l'objet utilisé

        return {"roulette": roulette}

    # 10) Kill (fin d’un combat)
    elif event == "on_kill":
        attacker_id = int(ctx.get("attacker_id"))
        damage_last = int(ctx.get("damage_last", 0))
        code = await get_equipped_code(attacker_id)

        # Le Roi : +10 PV si achève
        if code == CODE_ROI:
            try:
                from stats_db import heal_user
                await heal_user(attacker_id, attacker_id, 10)
            except Exception:
                pass

        # Abomination : +3 PV sur kill
        if code == CODE_ABOMI:
            try:
                from stats_db import heal_user
                await heal_user(attacker_id, attacker_id, 3)
            except Exception:
                pass

        return {}

    # 11) Pré-soin (avant d’appliquer le heal)
    elif event == "on_heal_pre":
        healer_id = int(ctx.get("healer_id"))
        target_id = int(ctx.get("target_id"))
        amount    = int(ctx.get("amount", 0))

        code_healer = await get_equipped_code(healer_id)
        mult_target = await get_heal_received_multiplier(target_id)
        heal_bonus = 0

        # Tessa Korrin : +1 aux soins prodigués
        if code_healer == CODE_TESSA:
            heal_bonus += 1

        return {"heal_bonus": heal_bonus, "mult_target": mult_target}

    # 12) Post-soin
    elif event == "on_heal":
        healer_id = int(ctx.get("healer_id"))
        target_id = int(ctx.get("target_id"))
        healed    = int(ctx.get("healed", 0))

        code = await get_equipped_code(healer_id)

        # Lysha : +1 PB au soigneur quand il soigne
        if code == CODE_LYSHA:
            try:
                from stats_db import add_shield
                await add_shield(healer_id, 1)
            except Exception:
                pass

        # Seren : PB = soin, 2×/jour
        if code == CODE_SEREN and healed > 0:
            used = await _get_counter(healer_id, "seren_pb_applied")
            if used < 2:
                try:
                    from stats_db import add_shield
                    await add_shield(target_id, healed)
                    await _inc_counter(healer_id, "seren_pb_applied", 1)
                except Exception:
                    pass

        return {}

    # 13) Heal global (quelqu’un a été soigné) — Kerin (5% self heal)
    elif event == "on_any_heal":
        healer_id = int(ctx.get("healer_id"))
        target_id = int(ctx.get("target_id"))
        healed    = int(ctx.get("healed", 0))

        # Pour tous les joueurs équipés Kerin ? (simple : seulement le soigneur)
        code = await get_equipped_code(healer_id)
        if code == CODE_KERIN and random.random() < 0.05:
            try:
                from stats_db import heal_user
                await heal_user(healer_id, healer_id, 1)
            except Exception:
                pass
        return {}

    # 14) Avant application d’un statut
    elif event == "on_effect_pre_apply":
        user_id = int(ctx.get("user_id"))
        eff     = str(ctx.get("eff_type") or "")
        return await trigger_on_effect_pre_apply(user_id, eff)

    # 15) Pré-défense (procs de réduction/annulation/flat)
    elif event == "on_defense_pre":
        defender_id = int(ctx.get("defender_id"))
        attacker_id = int(ctx.get("attacker_id"))
        incoming    = int(ctx.get("incoming", 0))
        code = await get_equipped_code(defender_id)

        cancel = False
        half   = False
        flat   = 0

        # Alen Drave 5% moitie
        if code == CODE_ALEN and random.random() < 0.05:
            half = True

        # Darin Venhal 10% moitie
        if code == CODE_DARIN and random.random() < 0.10:
            half = True

        # Nathaniel 10% moitie + malus attaquant 1h
        if code == CODE_NATHANIEL and random.random() < 0.10:
            half = True
            try:
                from effects_db import add_or_refresh_effect
                await add_or_refresh_effect(
                    user_id=attacker_id,
                    eff_type="outgoing_penalty",
                    value=0.10,
                    duration=60*60,
                    interval=0,
                    source_id=defender_id,
                    meta_json=None
                )
            except Exception:
                pass

        # Veylor : -1 flat, et 50% chance -2 flat supplémentaires
        if code == CODE_VEYLOR:
            flat += 1
            if random.random() < 0.50:
                flat += 2

        # Maître d'Hôtel : 30% annule, 20% contre (¼)
        if code == CODE_MAHD:
            r = random.random()
            if r < 0.30:
                cancel = True
            elif r < 0.50:
                # demande au moteur de contre-attaquer 25% des dégâts reçus
                # (à implémenter côté combat)
                return {"cancel": False, "half": False, "flat_reduce": 0, "counter_frac": 0.25}

        return {"cancel": cancel, "half": half, "flat_reduce": flat}

    # 16) Post-défense (après calcul final, savoir si esquive)
    elif event == "on_defense_after":
        defender_id = int(ctx.get("defender_id"))
        attacker_id = int(ctx.get("attacker_id"))
        final_taken = int(ctx.get("final_taken", 0))
        dodged      = bool(ctx.get("dodged", False))
        code = await get_equipped_code(defender_id)

        redirect = False
        gain_pb = 0

        # Cassiane : +1% reduction 24h (stack) à chaque attaque subie
        if code == CODE_CASSIANE and final_taken > 0:
            try:
                from effects_db import add_or_refresh_effect
                await add_or_refresh_effect(
                    user_id=defender_id,
                    eff_type="reduction_temp",
                    value=0.01,
                    duration=24*60*60,
                    interval=0, source_id=attacker_id, meta_json=None
                )
            except Exception:
                pass

        # Liora : 25% → +3% esquive 24h
        if code == CODE_LIORA and final_taken > 0 and random.random() < 0.25:
            try:
                from effects_db import add_or_refresh_effect
                await add_or_refresh_effect(
                    user_id=defender_id,
                    eff_type="esquive",
                    value=0.03,
                    duration=24*60*60,
                    interval=0, source_id=attacker_id, meta_json=None
                )
            except Exception:
                pass

        # Neyra Velenis : chaque attaque subie → -5% dégâts reçus +3% esquive pendant 1h (stacks)
        if code == CODE_NEYRA_V and final_taken > 0:
            try:
                from effects_db import add_or_refresh_effect
                await add_or_refresh_effect(defender_id, "reduction_temp", 0.05, 60*60, 0, attacker_id, None)
                await add_or_refresh_effect(defender_id, "esquive",        0.03, 60*60, 0, attacker_id, None)
            except Exception:
                pass

        # Mira Oskra : si survit à l'attaque, 3% chance de générer un item (❄️/🔥/🍀)
        if code == CODE_MIRA and final_taken >= 0:
            try:
                from stats_db import get_hp
                hp, _ = await get_hp(defender_id)
                if hp > 0 and random.random() < 0.03:
                    from inventory_db import add_item
                    emo = random.choice(["❄️", "🔥", "🍀"])
                    await add_item(defender_id, emo, 1)
            except Exception:
                pass

        # Elira Veska : si esquive, redirige + gagne 5 PB
        if code == CODE_ELIRA and dodged:
            redirect = True
            gain_pb = 5
            try:
                from stats_db import add_shield
                await add_shield(defender_id, gain_pb)
            except Exception:
                pass

        return {"redirect": redirect, "redirect_gain_pb": gain_pb}

    # 17) Ticks horaires / demi-heures
    elif event == "on_hourly_tick":
        user_id = int(ctx.get("user_id"))
        code = await get_equipped_code(user_id)

        # Dr Elwin Kaas : +1 PB/h
        if code == CODE_ELWIN_KAAS:
            try:
                from stats_db import add_shield
                await add_shield(user_id, 1)
            except Exception:
                pass

        # Dr Selina Vorne : +2 PV/h
        if code == CODE_SELINA:
            try:
                from stats_db import heal_user
                await heal_user(user_id, user_id, 2)
            except Exception:
                pass

        # Maelis : 1% chance de purger un effet négatif
        if code == CODE_MAELIS and random.random() < 0.01:
            try:
                from effects_db import list_effects, remove_effect
                rows = await list_effects(user_id)
                # simple: on enlève le premier effet "négatif" courant
                negative = ("poison", "virus", "infection", "brulure")
                for eff_type, value, interval, next_ts, end_ts, source_id, meta_json in rows:
                    if eff_type in negative:
                        await remove_effect(user_id, eff_type)
                        break
            except Exception:
                pass

        return {}

    elif event == "on_half_hour_tick":
        user_id = int(ctx.get("user_id"))
        code = await get_equipped_code(user_id)

        # Dr Selina : chance de purge chaque 30 min (≈20%)
        if code == CODE_SELINA and random.random() < 0.20:
            try:
                from effects_db import list_effects, remove_effect
                rows = await list_effects(user_id)
                negative = ("poison", "virus", "infection", "brulure")
                for eff_type, value, interval, next_ts, end_ts, source_id, meta_json in rows:
                    if eff_type in negative:
                        await remove_effect(user_id, eff_type)
                        break
            except Exception:
                pass

        return {}

    # Event inconnu
    return {}

# ─────────────────────────────────────────────────────────────
# Utilitaires "haut niveau" pour l’invocation / infection
# ─────────────────────────────────────────────────────────────
async def modify_infection_application(source_id: int, base_value: int) -> int:
    """
    Si l'attaquant est ANNA (Hôte brisé) et applique 'infection', +1 au DOT.
    """
    code = await get_equipped_code(source_id)
    if code == CODE_ANNA:
        return int(base_value) + 1
    return int(base_value)

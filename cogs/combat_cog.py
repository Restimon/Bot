# cogs/combat_cog.py
from __future__ import annotations

import asyncio
import json
import random
import time
from typing import Dict, Tuple, List, Optional

import discord
from discord.ext import commands
from discord import app_commands

# ── Backends combat/éco/inventaire/effets ───────────────────────────────────
from stats_db import deal_damage, heal_user, get_hp, is_dead, revive_full
try:
    from stats_db import add_shield  # type: ignore
except Exception:
    add_shield = None  # type: ignore

# effects_db (avec stubs robustes)
try:
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
except Exception:
    async def add_or_refresh_effect(**kwargs): return None
    async def remove_effect(*args, **kwargs): return None
    async def has_effect(*args, **kwargs): return False
    async def list_effects(*args, **kwargs): return []
    async def effects_loop(*args, **kwargs): return None
    def  set_broadcaster(*args, **kwargs): return None
    async def transfer_virus_on_attack(*args, **kwargs): return None
    async def get_outgoing_damage_penalty(*args, **kwargs): return 0

# économie / inventaire
from economy_db import add_balance, get_balance
from inventory_db import get_item_qty, remove_item, add_item

# Passifs (import "safe" + stubs si manquant)
try:
    from passifs import trigger
except Exception:
    async def trigger(*args, **kwargs): return {}

try:
    from passifs import get_extra_dodge_chance
except Exception:
    async def get_extra_dodge_chance(*args, **kwargs) -> float: return 0.0

try:
    from passifs import get_extra_reduction_percent
except Exception:
    async def get_extra_reduction_percent(*args, **kwargs) -> float: return 0.0

try:
    from passifs import king_execute_ready
except Exception:
    async def king_execute_ready(*args, **kwargs) -> bool: return False

try:
    from passifs import undying_zeyra_check_and_mark
except Exception:
    async def undying_zeyra_check_and_mark(*args, **kwargs) -> bool: return False

# Objets (emoji -> caractéristiques) + GIFs
try:
    from utils import OBJETS, get_random_item  # type: ignore
    try:
        from utils import FIGHT_GIFS  # préféré si dispo
    except Exception:
        from utils import GIFS as FIGHT_GIFS  # fallback rétro-compat
except Exception:
    OBJETS = {}
    FIGHT_GIFS = {}
    def get_random_item(debug: bool = False):
        return random.choice(["🍀", "❄️", "🧪", "🩹", "💊"])

# GIF critique (uniquement pour attaques critiques)
CRIT_GIF = "https://media4.giphy.com/media/v1.Y2lkPTc5MGI3NjExZmoxOTJ1emRocHJoM2pueGRneGJhdDhjNW81ZzRzOHdxa2ZoazljbiZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/o2TqK6vEzhp96/giphy.gif"

# ─────────────────────────────────────────────────────────────
# MAPPING des salons de ticks : user_id -> (guild_id, channel_id)
# ─────────────────────────────────────────────────────────────
_tick_channels: Dict[int, Tuple[int, int]] = {}

def remember_tick_channel(user_id: int, guild_id: int, channel_id: int) -> None:
    _tick_channels[int(user_id)] = (int(guild_id), int(channel_id))

def get_all_tick_targets() -> List[Tuple[int, int]]:
    seen: set[Tuple[int, int]] = set()
    for pair in _tick_channels.values():
        seen.add(pair)
    return list(seen)

# ─────────────────────────────────────────────────────────────
# Helpers d’affichage & calcul
# ─────────────────────────────────────────────────────────────
def _fmt_parentheses_damage(raw: int, absorbed: int = 0, reduced: int = 0) -> str:
    """
    Construit la parenthèse explicative: (10 PV - 5 🛡 - 3 🪖)
    N’affiche pas les éléments à 0 pour rester compact.
    """
    parts = [f"{raw} PV"]
    if absorbed > 0:
        parts.append(f"- {absorbed} 🛡")
    if reduced > 0:
        parts.append(f"- {reduced} 🪖")
    return "(" + " ".join(parts) + ")"

async def _sum_effect_value(user_id: int, rows: List[tuple], *types_: str) -> float:
    out = 0.0
    wanted = set(types_)
    for eff_type, value, interval, next_ts, end_ts, source_id, meta_json in rows:
        if eff_type in wanted:
            try: out += float(value or 0.0)
            except Exception: pass
    return out

async def _get_active_reduction_factor(user_id: int) -> float:
    """
    Retourne la réduction active (0..0.95) d’après effects_db.list_effects et passifs.
    Additionne les effets de type 'reduction', 'reduction_temp', 'reduction_valen' + bonus passifs.
    """
    try:
        rows = await list_effects(user_id)
    except Exception:
        rows = []
    base = await _sum_effect_value(user_id, rows, "reduction", "reduction_temp", "reduction_valen")
    try:
        extra = float(await get_extra_reduction_percent(user_id) or 0.0)
    except Exception:
        extra = 0.0
    fac = max(0.0, min(0.95, base + extra))
    return fac

# ─────────────────────────────────────────────────────────────
# Broadcaster des ticks (appelé par effects_db)
# ─────────────────────────────────────────────────────────────
async def _effects_broadcaster(bot: commands.Bot, guild_id: int, channel_id: int, payload: Dict):
    """
    Essaie d’afficher les ticks avec la même parenthèse (raw − 🛡 − 🪖) si le payload
    fournit suffisamment d’infos. Sinon, fallback sur payload['lines'].
    """
    target_gid = guild_id
    target_cid = channel_id
    uid = payload.get("user_id")
    if uid is not None and int(uid) in _tick_channels:
        target_gid, target_cid = _tick_channels[int(uid)]
    channel = bot.get_channel(int(target_cid))
    if not channel or not isinstance(channel, (discord.TextChannel, discord.Thread)):
        channel = bot.get_channel(int(channel_id))
        if not channel:
            return

    title = str(payload.get("title", "Action de GotValis"))
    color = int(payload.get("color", 0xE67E22))

    # Tentative de reconstruction "à l’ancienne"
    raw = payload.get("raw")         # dégâts bruts du tick
    absorbed = payload.get("absorbed", 0)
    reduced = payload.get("reduced", 0)
    hp_before = payload.get("hp_before")
    hp_after = payload.get("hp_after")
    mention = payload.get("mention")  # cible sous forme de mention si fournie

    embed = discord.Embed(title=title, color=color)

    if isinstance(raw, int) and isinstance(hp_before, int) and isinstance(hp_after, int):
        paren = _fmt_parentheses_damage(raw, int(absorbed or 0), int(reduced or 0))
        who = str(mention) if mention else "La cible"
        lines = [
            f"{who} subit **{paren}**.",
            f"❤️ **{hp_before} PV** - **{paren}** = ❤️ **{hp_after} PV**",
        ]
        rem = payload.get("remaining_txt")
        if rem:
            lines.append(rem)
        embed.description = "\n".join(lines)
    else:
        # Fallback: lignes brutes passées par l’effet
        lines = payload.get("lines") or []
        if lines:
            embed.description = "\n".join(lines)

    await channel.send(embed=embed)

# ─────────────────────────────────────────────────────────────
# Le COG
# ─────────────────────────────────────────────────────────────
class CombatCog(commands.Cog):
    """Système de combat : /fight (+ tests).  (/heal est dans heal_cog.py)"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        set_broadcaster(lambda gid, cid, pld: asyncio.create_task(_effects_broadcaster(self.bot, gid, cid, pld)))
        self._start_effects_loop_once()

    def _start_effects_loop_once(self):
        if getattr(self.bot, "_effects_loop_started", False):
            return
        self.bot._effects_loop_started = True
        async def runner():
            await effects_loop(get_targets=get_all_tick_targets, interval=30)
        asyncio.create_task(runner())

    # ─────────────────────────────────────────────────────────
    # Helpers inventaire
    # ─────────────────────────────────────────────────────────
    async def _consume_item(self, user_id: int, emoji: str) -> bool:
        try:
            qty = await get_item_qty(user_id, emoji)
            if int(qty or 0) <= 0:
                return False
            await remove_item(user_id, emoji, 1)
            return True
        except Exception:
            return False

    def _obj_info(self, emoji: str) -> Optional[Dict]:
        info = OBJETS.get(emoji)
        return dict(info) if isinstance(info, dict) else None

    async def _maybe_update_leaderboard(self, guild_id: int, reason: str):
        try:
            from cogs.leaderboard_live import schedule_lb_update
            schedule_lb_update(self.bot, guild_id, reason)
        except Exception:
            pass

    async def _compute_dodge_chance(self, user_id: int) -> float:
        try:
            base = float(await get_extra_dodge_chance(user_id) or 0.0)
        except Exception:
            base = 0.0
        try:
            rows = await list_effects(user_id)
        except Exception:
            rows = []
        buffs = await _sum_effect_value(user_id, rows, "esquive", "esquive+")
        return min(base + float(buffs), 0.95)

    async def _calc_outgoing_penalty(self, attacker_id: int, base: int) -> int:
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
    # Pipeline dégâts / soins / effets
    # ─────────────────────────────────────────────────────────
    async def _resolve_hit(
        self,
        inter: discord.Interaction,
        attacker: discord.Member,
        target: discord.Member,
        base_damage: int,
        is_crit_flag: bool,
        note_footer: Optional[str] = None,
    ) -> Dict[str, int | bool | str]:
        """
        Retourne un dict:
        {
          'lost': int,        # PV réellement perdus (après PB)
          'absorbed': int,    # PB consommé
          'reduced': int,     # réduction totale (🪖 + éventuels flats)
          'dodged': bool,
          'ko_txt': str
        }
        """

        # Esquive ?
        dodge = await self._compute_dodge_chance(target.id)
        if random.random() < dodge:
            try:
                await trigger("on_defense_after",
                              defender_id=target.id, attacker_id=attacker.id,
                              final_taken=0, dodged=True)
            except Exception:
                pass
            return {'lost': 0, 'absorbed': 0, 'reduced': 0, 'dodged': True, 'ko_txt': ""}

        # Hooks pré-défense
        try:
            predef = await trigger("on_defense_pre",
                                   defender_id=target.id,
                                   attacker_id=attacker.id,
                                   incoming=int(base_damage)) or {}
        except Exception:
            predef = {}

        cancel = bool(predef.get("cancel"))
        half   = bool(predef.get("half"))
        flat   = int(predef.get("flat_reduce", 0))
        counter_frac = float(predef.get("counter_frac", 0.0) or 0.0)

        # Réduction 🪖 cumulée
        dr_pct = await _get_active_reduction_factor(target.id)

        # Calcul: on part des dégâts "bruts" (post-crit, post-malus sortant)
        if cancel:
            dmg_after_dr_flat = 0
        else:
            step1 = int(round(base_damage * (0.5 if half else 1.0)))
            step2 = int(round(step1 * (1.0 - dr_pct)))
            dmg_after_dr_flat = max(0, step2 - max(0, flat))

        # Partie affichage: total réduit = (base - ce qui reste avant PB)
        reduced_total = max(0, base_damage - dmg_after_dr_flat)

        # Application réelle: PB puis PV
        res = await deal_damage(attacker.id, target.id, int(dmg_after_dr_flat))
        absorbed = int(res.get("absorbed", 0) or 0)
        lost = int(res.get("lost", 0) or 0)

        # Contre-attaque éventuelle
        if counter_frac > 0 and dmg_after_dr_flat > 0:
            try:
                counter = max(1, int(round(dmg_after_dr_flat * counter_frac)))
                await deal_damage(target.id, attacker.id, counter)
            except Exception:
                pass

        # KO / anti-KO
        ko_txt = ""
        if await is_dead(target.id):
            if await undying_zeyra_check_and_mark(target.id):
                # remet à 1 PV
                await heal_user(healer_id=target.id, target_id=target.id, amount=1)
                ko_txt = "\n⭐ **Volonté de Fracture** : survit à 1 PV."
            else:
                await revive_full(target.id)
                ko_txt = "\n💥 **Cible mise KO** (réanimée en PV/PB)."

        try:
            await trigger("on_defense_after",
                          defender_id=target.id, attacker_id=attacker.id,
                          final_taken=lost, dodged=False)
        except Exception:
            pass

        return {'lost': lost, 'absorbed': absorbed, 'reduced': reduced_total, 'dodged': False, 'ko_txt': ko_txt}

    # ========= AFFICHAGE “ANCIEN STYLE” (avec GIF en bas) =========
    def _oldstyle_embed(
        self,
        emoji: str,
        attacker: discord.Member,
        target: discord.Member,
        hp_before: int,
        raw_damage: int,
        lost: int,
        absorbed: int,
        reduced: int,
        hp_after: int,
        ko_txt: str,
        dodged: bool,
        *,
        gif_url: Optional[str] = None
    ) -> discord.Embed:
        title = f"{emoji} Action de GotValis"
        e = discord.Embed(title=title, color=discord.Color.orange())

        if dodged:
            e.description = f"{attacker.mention} tente {emoji} sur {target.mention}…\n🛰️ **Esquive !**{ko_txt}"
        else:
            paren = _fmt_parentheses_damage(raw_damage, absorbed, reduced)
            lines = [
                f"{attacker.mention} inflige {emoji} sur {target.mention} !",
                f"{target.mention} perd **{paren}**",
                f"❤️ **{hp_before} PV** - **{paren}** = ❤️ **{hp_after} PV**"
            ]
            if ko_txt:
                lines.append(ko_txt.strip())
            e.description = "\n".join(lines)

        if isinstance(gif_url, str) and (gif_url.startswith("http://") or gif_url.startswith("https://")):
            e.set_image(url=gif_url)
        return e

    # ========= ACTIONS CONCRÈTES =========
    async def _roll_value(self, info: dict, key_default: int = 5) -> int:
        if isinstance(info, dict):
            if "min" in info and "max" in info:
                try:
                    a = int(info.get("min", 0)); b = int(info.get("max", 0))
                    if a > b: a, b = b, a
                    return random.randint(a, b)
                except Exception:
                    pass
            for k in ("valeur", "value", "amount", "degats", "dmg", "heal"):
                if k in info:
                    try:
                        return int(info[k])
                    except Exception:
                        continue
        return int(key_default)

    async def _apply_attack(
        self,
        inter: discord.Interaction,
        attacker: discord.Member,
        target: discord.Member,
        emoji: str,
        info: dict
    ) -> discord.Embed:
        # Base dégâts
        base = await self._roll_value(info, 5)

        # Critiques (supporte 'crit' ou 'crit_chance')
        crit_chance = float(info.get("crit", info.get("crit_chance", 0.10)) or 0.0)
        crit_mult   = float(info.get("crit_mult", 1.5) or 1.0)
        is_crit = (random.random() < max(0.0, min(crit_chance, 1.0)))
        if is_crit:
            base = int(round(base * max(1.0, crit_mult)))

        # Malus d'attaque
        base = max(0, base - int(await self._calc_outgoing_penalty(attacker.id, base)))

        # Virus : transfert avant le coup
        try:
            await transfer_virus_on_attack(attacker.id, target.id)
        except Exception:
            pass

        # Résolution
        hp_before, _ = await get_hp(target.id)
        result = await self._resolve_hit(inter, attacker, target, base, is_crit, None)
        lost = int(result["lost"])
        absorbed = int(result["absorbed"])
        reduced = int(result["reduced"])
        dodged = bool(result["dodged"])
        ko_txt = str(result["ko_txt"])
        hp_after, _ = await get_hp(target.id)

        # Hook passifs
        try:
            await trigger("on_attack", attacker_id=attacker.id, target_id=target.id, damage_done=lost)
        except Exception:
            pass

        # GIF: critique → CRIT_GIF, sinon GIF spécifique de l’emoji
        gif_normal = None
        try:
            gif_normal = FIGHT_GIFS.get(emoji) or (OBJETS.get(emoji) or {}).get("gif")  # fallback
        except Exception:
            gif_normal = None
        gif_url = CRIT_GIF if (is_crit and not dodged and lost > 0) else gif_normal

        # Embed (parenthèse: base bruts, -PB absorbé, -réduction)
        e = self._oldstyle_embed(
            emoji, attacker, target,
            hp_before,
            base,               # RAW
            lost,
            absorbed,
            reduced,
            hp_after,
            ko_txt,
            dodged,
            gif_url=gif_url
        )
        if is_crit and not dodged and lost > 0:
            e.add_field(name="💥 Critique !", value=f"x{crit_mult:g}", inline=True)
        return e

    async def _apply_chain_attack(
        self,
        inter: discord.Interaction,
        attacker: discord.Member,
        target: discord.Member,
        emoji: str,
        info: dict
    ) -> discord.Embed:
        embed = await self._apply_attack(inter, attacker, target, emoji, info)
        # seconde frappe “chaîne” simplifiée
        try:
            base = await self._roll_value(info, 5)
            base = int(round(base * float(info.get("chain_factor", 0.6) or 0.6)))
            base = max(0, base - int(await self._calc_outgoing_penalty(attacker.id, base)))
            if base > 0:
                await transfer_virus_on_attack(attacker.id, target.id)
                await self._resolve_hit(inter, attacker, target, base, False, None)
        except Exception:
            pass
        return embed

    # ========= Inventaire réel pour l’auto-complétion =========
    async def _list_owned_items(self, uid: int) -> List[Tuple[str, int]]:
        owned: List[Tuple[str, int]] = []
        try:
            from inventory_db import get_all_items  # type: ignore
            rows = await get_all_items(uid)
            if rows:
                if isinstance(rows, list):
                    for r in rows:
                        e = None; q = 0
                        if isinstance(r, (tuple, list)) and len(r) >= 2:
                            e, q = str(r[0]), int(r[1])
                        elif isinstance(r, dict):
                            e = str(r.get("emoji") or r.get("item") or r.get("id") or r.get("key") or "")
                            q = int(r.get("qty") or r.get("quantity") or r.get("count") or r.get("n") or 0)
                        if e and q > 0:
                            owned.append((e, q))
                elif isinstance(rows, dict):
                    for e, q in rows.items():
                        try:
                            q = int(q)
                            if q > 0:
                                owned.append((str(e), q))
                        except Exception:
                            continue
        except Exception:
            pass

        if not owned:
            for emoji in OBJETS.keys():
                try:
                    q = int(await get_item_qty(uid, emoji) or 0)
                    if q > 0:
                        owned.append((emoji, q))
                except Exception:
                    continue

        merged: Dict[str, int] = {}
        for e, q in owned:
            merged[e] = merged.get(e, 0) + int(q)
        return sorted(merged.items(), key=lambda t: t[0])

    # AUTOCOMPLÉTIONS
    async def _ac_items_by_type(self, inter: discord.Interaction, current: str, allowed: Tuple[str, ...]) -> List[app_commands.Choice[str]]:
        uid = inter.user.id
        cur = (current or "").strip().lower()
        owned = await self._list_owned_items(uid)

        out: List[app_commands.Choice[str]] = []
        for emoji, qty in owned:
            info = OBJETS.get(emoji) or {}
            typ = str(info.get("type", ""))
            if typ not in allowed:
                continue
            label = info.get("nom") or info.get("label") or typ
            display = f"{emoji} — {label} (x{qty})"
            if cur and (cur not in emoji and cur not in str(label).lower()):
                continue
            out.append(app_commands.Choice(name=display[:100], value=emoji))
            if len(out) >= 20:
                break
        return out

    async def _ac_items_attack(self, inter: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        return await self._ac_items_by_type(
            inter, current,
            ("attaque", "attaque_chaine", "poison", "infection", "virus", "brulure")
        )

    # ─────────────────────────────────────────────────────────
    # /fight — attaques & DOTs
    # ─────────────────────────────────────────────────────────
    @app_commands.command(name="fight", description="Attaquer un joueur avec un objet d’attaque (ou appliquer un effet offensif).")
    @app_commands.describe(cible="La cible", objet="Choisis un objet d’attaque ou un effet (poison, virus, brûlure...)")
    @app_commands.autocomplete(objet=_ac_items_attack)
    async def fight(self, inter: discord.Interaction, cible: discord.Member, objet: str):
        if inter.user.id == cible.id:
            return await inter.response.send_message("Tu ne peux pas t’attaquer toi-même.", ephemeral=True)

        info = self._obj_info(objet)
        if not info or info.get("type") not in ("attaque", "attaque_chaine", "poison", "infection", "virus", "brulure"):
            return await inter.response.send_message("Objet invalide : il faut un **objet offensif**.", ephemeral=True)

        if not await self._consume_item(inter.user.id, objet):
            return await inter.response.send_message(f"Tu n’as pas **{objet}** dans ton inventaire.", ephemeral=True)

        await inter.response.defer(thinking=True)

        typ = info["type"]
        if typ == "attaque":
            embed = await self._apply_attack(inter, inter.user, cible, objet, info)
        elif typ == "attaque_chaine":
            embed = await self._apply_chain_attack(inter, inter.user, cible, objet, info)
        else:
            # DOTs : on réutilise le pipe des effets
            label = {
                "poison": "🧪 Poison",
                "infection": "🧟 Infection",
                "virus": "🦠 Virus (transfert sur attaque)",
                "brulure": "🔥 Brûlure",
            }[typ]
            # application via effets_db
            val = int(info.get("valeur", info.get("value", info.get("degats", 1))) or 1)
            interval = int(info.get("interval", info.get("tick", 60)) or 60)
            duration = int(info.get("duree", info.get("duration", 300)) or 300)

            remember_tick_channel(cible.id, inter.guild.id, inter.channel.id)

            pre = await trigger("on_effect_pre_apply", user_id=cible.id, eff_type=typ) or {}
            if pre.get("blocked"):
                return await inter.followup.send(f"{label}\n⛔ Effet bloqué : {pre.get('reason','')}")
            ok = await add_or_refresh_effect(
                user_id=cible.id, eff_type=typ, value=float(val),
                duration=duration, interval=interval,
                source_id=inter.user.id, meta_json=json.dumps({"applied_in": inter.channel.id})
            )
            if not ok:
                return await inter.followup.send(f"{label}\n⛔ {cible.mention} est **immunisé(e)**.")
            embed = discord.Embed(
                title=label,
                description=f"{inter.user.mention} applique **{objet}** sur {cible.mention} "
                            f"(val={val}, every {interval}s, dur={duration}s).",
                color=discord.Color.orange()
            )

        await inter.followup.send(embed=embed)
        await self._maybe_update_leaderboard(inter.guild.id, "fight")

async def setup(bot: commands.Bot):
    await bot.add_cog(CombatCog(bot))

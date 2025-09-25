# cogs/combat_cog.py
from __future__ import annotations

import asyncio
import json
import random
from typing import Dict, Tuple, List, Optional

import discord
from discord.ext import commands
from discord import app_commands

# ── Backends combat/éco/inventaire/effets ───────────────────────────────────
from stats_db import deal_damage, heal_user, get_hp, is_dead, revive_full
try:
    from stats_db import get_shield  # pour afficher PB
except Exception:
    async def get_shield(user_id: int) -> int:  # type: ignore
        return 0

try:
    from stats_db import add_shield  # facultatif
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
        explain_damage_modifiers,   # optionnel
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
    async def explain_damage_modifiers(*args, **kwargs): return None

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
# Broadcaster des ticks (appelé par effects_db)
# ─────────────────────────────────────────────────────────────
def _fmt_remain(secs: int) -> str:
    s = max(0, int(secs))
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h} h {m} min"
    if m:
        return f"{m} min"
    return f"{s} s"

async def _effects_broadcaster(bot: commands.Bot, guild_id: int, channel_id: int, payload: Dict):
    """
    Supporte:
      - {type:"shield_broken", user_id, cause:"poison"|"infection"|"brulure"}
      - payload 'générique' avec éventuellement remaining_seconds (ou remaining)
    et redirige vers le salon mémorisé via remember_tick_channel(user_id,...).
    """
    # rediriger vers le salon où la cible a été 'remember'
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

    # 1) Bouclier détruit ?
    if payload.get("type") == "shield_broken" or payload.get("shield_broken"):
        member = None
        try:
            gid_obj = bot.get_guild(int(target_gid))
            if gid_obj and uid:
                member = gid_obj.get_member(int(uid))
        except Exception:
            member = None
        who = member.mention if member else (f"<@{uid}>" if uid else "Quelqu'un")
        cause = str(payload.get("cause") or "").strip().lower()
        cause_txt = ""
        if cause == "poison":
            cause_txt = " sous l'effet du poison."
        elif cause == "infection":
            cause_txt = " sous l'effet de l'infection."
        elif cause == "brulure":
            cause_txt = " sous l'effet de la brûlure."

        emb = discord.Embed(
            title="🛡️ Bouclier détruit",
            description=f"Le bouclier de {who} a été **détruit**{cause_txt}",
            color=discord.Color.blurple()
        )
        await channel.send(embed=emb)
        return

    # 2) Ticks génériques (DoT/HoT)
    title = str(payload.get("title", "GotValis"))
    color = int(payload.get("color", 0x2ecc71))
    lines = list(map(str, payload.get("lines") or []))

    # Ajout d'une ligne en temps lisible si fourni
    remain = payload.get("remaining_seconds")
    if remain is None:
        remain = payload.get("remaining")
    try:
        remain = int(remain)
    except Exception:
        remain = None
    if remain is not None:
        lines.append(f"⏳ Temps restant : **{_fmt_remain(remain)}**")

    embed = discord.Embed(title=title, description="\n".join(lines), color=color)
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
    # Helpers
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

    async def _sum_effect_value(self, user_id: int, *types_: str) -> float:
        out = 0.0
        try:
            rows = await list_effects(user_id)
            wanted = set(types_)
            for eff_type, value, interval, next_ts, end_ts, source_id, meta_json in rows:
                if eff_type in wanted:
                    try: out += float(value)
                    except Exception: pass
        except Exception:
            pass
        return out

    async def _compute_dodge_chance(self, user_id: int) -> float:
        base = await get_extra_dodge_chance(user_id)
        buffs = await self._sum_effect_value(user_id, "esquive", "esquive+")
        return min(base + float(buffs), 0.95)

    async def _compute_reduction_pct(self, user_id: int) -> float:
        base = await get_extra_reduction_percent(user_id)
        buffs = await self._sum_effect_value(user_id, "reduction", "reduction_temp", "reduction_valen")
        return min(base + float(buffs), 0.90)

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
    ) -> Tuple[int, int, bool, str]:

        # esquive
        dodge = await self._compute_dodge_chance(target.id)
        if random.random() < dodge:
            try:
                await trigger("on_defense_after",
                              defender_id=target.id, attacker_id=attacker.id,
                              final_taken=0, dodged=True)
            except Exception:
                pass
            return 0, 0, True, "\n🛰️ **Esquive !**"

        # passifs pré-défense (peuvent half/cancel/flat)
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

        # réduction pourcent (🪖)
        dr_pct = await self._compute_reduction_pct(target.id)

        # calcul final pour stats_db
        if cancel:
            dmg_final = 0
        else:
            dmg_final = int(base_damage * (0.5 if half else 1.0))
            dmg_final = int(dmg_final * (1.0 - dr_pct))
            dmg_final = max(0, dmg_final - flat)

        # applique dégâts (gère PB & KO)
        res = await deal_damage(attacker.id, target.id, int(dmg_final))
        absorbed = int(res.get("absorbed", 0) or 0)

        # contre-attaque ?
        if counter_frac > 0 and dmg_final > 0:
            try:
                counter = max(1, int(round(dmg_final * counter_frac)))
                await deal_damage(target.id, attacker.id, counter)
            except Exception:
                pass

        ko_txt = ""
        if await is_dead(target.id):
            if await undying_zeyra_check_and_mark(target.id):
                await heal_user(target.id, 1)
                ko_txt = "\n⭐ **Volonté de Fracture** : survit à 1 PV."
            else:
                await revive_full(target.id)
                ko_txt = "\n💥 **Cible mise KO** (réanimée en PV/PB)."

        try:
            await trigger("on_defense_after",
                          defender_id=target.id, attacker_id=attacker.id,
                          final_taken=dmg_final, dodged=False)
        except Exception:
            pass

        return int(dmg_final), absorbed, False, ko_txt

    # ========= FORMAT/EMBED =========
    def _format_loss_breakdown(
        self,
        hp_before: int,
        shield_before: int,
        base_raw: int,
        lost_hp: int,
        lost_shield: int,
        explained: Optional[Dict[str, int]] = None,
    ) -> Tuple[str, str]:
        """
        Construit:
          - line2 (perte détaillée)
          - line3 (équation)
        Cache la partie PB si elle est nulle.
        """
        total_reduction = max(0, base_raw - lost_hp - lost_shield)
        hel = 0
        p_hp = 0
        p_sh = 0

        if explained and isinstance(explained, dict):
            hel = int(explained.get("helmet_reduction", 0) or 0)
            p_hp = int(explained.get("poison_reduce_hp", 0) or 0)
            p_sh = int(explained.get("poison_reduce_shield", 0) or 0)
            if hel + p_hp + p_sh > total_reduction:
                extra = (hel + p_hp + p_sh) - total_reduction
                trim_hel = min(hel, extra); hel -= trim_hel; extra -= trim_hel
                if extra > 0:
                    trim_php = min(p_hp, extra); p_hp -= trim_php; extra -= trim_php
                if extra > 0:
                    p_sh = max(0, p_sh - extra)
        else:
            hel = total_reduction

        heart_chunk = f"{max(0, lost_hp)} ❤️"
        if hel > 0:
            heart_chunk += f" - {hel} 🪖"
        if p_hp > 0:
            heart_chunk += f" - {p_hp} 🧪"

        if shield_before == 0 and lost_shield == 0:
            # Sans PB
            line2 = f"@Cible perd **({heart_chunk})**"
            after_hp = max(0, hp_before - lost_hp)
            line3 = f"**{hp_before} ❤️** - **({heart_chunk})** = **{after_hp} ❤️**"
        else:
            shield_chunk = f"{max(0, lost_shield)} 🛡"
            if p_sh > 0:
                shield_chunk += f" - {p_sh} 🧪"
            line2 = f"@Cible perd **({heart_chunk} | {shield_chunk})**"
            after_hp = max(0, hp_before - lost_hp)
            line3 = (
                f"**{hp_before} ❤️ | {shield_before} 🛡** - "
                f"**({heart_chunk} | {shield_chunk})** = "
                f"**{after_hp} ❤️**"
            )
        return line2, line3

    def _attack_embed(
        self,
        emoji: str,
        attacker: discord.Member,
        target: discord.Member,
        base_raw: int,
        lost_hp: int,
        lost_shield: int,
        hp_before: int,
        shield_before: int,
        ko_txt: str,
        dodged: bool,
        *,
        is_crit: bool = False,
        gif_url: Optional[str] = None,
        explained: Optional[Dict[str, int]] = None,
    ) -> discord.Embed:
        e = discord.Embed(title=f"{emoji} Action de GotValis", color=discord.Color.orange())

        if dodged:
            e.description = f"{attacker.mention} tente {emoji} sur {target.mention}…\n🛰️ **Esquive !**{ko_txt}"
            if gif_url:
                e.set_image(url=gif_url)
            return e

        # 1re ligne : final puis (bruts)
        line1 = (
            f"{attacker.mention} inflige **{lost_hp}** (*{base_raw} bruts*) "
            f"dégâts à {target.mention} avec {emoji} !"
        )

        line2, line3 = self._format_loss_breakdown(
            hp_before, shield_before, base_raw, lost_hp, lost_shield, explained=explained
        )

        parts = [line1, line2, line3]
        if ko_txt:
            parts.append(ko_txt.strip())
        if is_crit and lost_hp > 0:
            parts.append("💥 **Coup critique !**")

        e.description = "\n".join(parts)
        if gif_url:
            e.set_image(url=gif_url)
        return e

    # ========= ACTIONS CONCRÈTES =========
    async def _roll_value(self, info: dict, key_default: int = 1) -> int:
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

        # Critiques (x2 demandé)
        crit_chance = float(info.get("crit_chance", 0.10) or 0.0)
        crit_mult   = float(info.get("crit_mult", 2.0) or 2.0)  # ← x2 par défaut
        is_crit = (random.random() < max(0.0, min(crit_chance, 1.0)))
        if is_crit:
            base = int(round(base * max(1.0, crit_mult)))

        # Malus d'attaque (ex: affaiblissements attaquant)
        attacker_pen = int(await self._calc_outgoing_penalty(attacker.id, base))
        base_after_pen = max(0, base - attacker_pen)

        # Virus : transfert avant le coup
        try:
            await transfer_virus_on_attack(attacker.id, target.id)
        except Exception:
            pass

        # Etats avant
        hp_before, _mx = await get_hp(target.id)
        shield_before = await get_shield(target.id)

        # Résolution
        dmg_final, absorbed, dodged, ko_txt = await self._resolve_hit(
            inter, attacker, target, base_after_pen, is_crit, None
        )

        # Hook passifs
        try:
            await trigger("on_attack", attacker_id=attacker.id, target_id=target.id, damage_done=dmg_final)
        except Exception:
            pass

        # Décomposition explicable (si backend l'offre)
        explained: Optional[Dict[str, int]] = None
        try:
            exp = await explain_damage_modifiers(attacker.id, target.id, base_after_pen)
            if isinstance(exp, dict):
                explained = {
                    "helmet_reduction": int(exp.get("helmet_reduction", 0) or 0),
                    "poison_reduce_hp": int(exp.get("poison_reduce_hp", 0) or 0),
                    "poison_reduce_shield": int(exp.get("poison_reduce_shield", 0) or 0),
                }
        except Exception:
            explained = None

        # GIF: critique → CRIT_GIF, sinon GIF spécifique de l’emoji
        try:
            gif_normal = FIGHT_GIFS.get(emoji)
        except Exception:
            gif_normal = None
        gif_url = CRIT_GIF if (is_crit and not dodged and dmg_final > 0) else gif_normal

        # Embed combat
        e = self._attack_embed(
            emoji=emoji,
            attacker=attacker,
            target=target,
            base_raw=base,                # (affichage “bruts”)
            lost_hp=dmg_final,
            lost_shield=absorbed,
            hp_before=hp_before,
            shield_before=shield_before,
            ko_txt=ko_txt,
            dodged=dodged,
            gif_url=gif_url,
            explained=explained,
            is_crit=is_crit,
        )

        # Envoi principal
        await inter.followup.send(embed=e)

        # Après envoi: si le bouclier vient d’être détruit par CE coup, annoncer
        try:
            shield_after = await get_shield(target.id)
        except Exception:
            shield_after = 0
        if shield_before > 0 and shield_after == 0:
            emb = discord.Embed(
                title="🛡️ Bouclier détruit",
                description=f"Le bouclier de {target.mention} a été **détruit**.",
                color=discord.Color.blurple()
            )
            await inter.followup.send(embed=emb)

        return e

    async def _apply_chain_attack(
        self,
        inter: discord.Interaction,
        attacker: discord.Member,
        target: discord.Member,
        emoji: str,
        info: dict
    ) -> discord.Embed:
        # on laisse _apply_attack poster l'embed principal
        embed = await self._apply_attack(inter, attacker, target, emoji, info)
        try:
            base = await self._roll_value(info, 5)
            base = int(round(base * float(info.get("chain_factor", 0.6) or 0.6)))
            attacker_pen = int(await self._calc_outgoing_penalty(attacker.id, base))
            base = max(0, base - attacker_pen)
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
            await self._apply_attack(inter, inter.user, cible, objet, info)
        elif typ == "attaque_chaine":
            await self._apply_chain_attack(inter, inter.user, cible, objet, info)
        else:
            # DOTs
            label = {
                "poison": "🧪 Poison",
                "infection": "🧟 Infection",
                "virus": "🦠 Virus (transfert sur attaque)",
                "brulure": "🔥 Brûlure",
            }[typ]
            val = int(info.get("valeur", info.get("value", 1)) or 1)
            interval = int(info.get("interval", info.get("tick", 60)) or 60)
            duration = int(info.get("duree", info.get("duration", 300)) or 300)

            # mémoriser le salon pour les ticks
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

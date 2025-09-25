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
    from stats_db import get_shield  # pour l'affichage PB
except Exception:
    async def get_shield(user_id: int) -> int:  # type: ignore
        return 0

try:
    from stats_db import add_shield  # optionnel
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

# (OPTIONNEL) explications chiffrées (casque/poison)
try:
    from effects_db import explain_damage_modifiers  # type: ignore
except Exception:
    explain_damage_modifiers = None  # type: ignore

# économie / inventaire
from inventory_db import get_item_qty, remove_item
from economy_db import add_balance

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
    # liste unique (guild_id, channel_id) pour démarrer la boucle
    seen: set[Tuple[int, int]] = set()
    for pair in _tick_channels.values():
        seen.add(pair)
    return list(seen)

# ─────────────────────────────────────────────────────────────
# Helpers visuels
# ─────────────────────────────────────────────────────────────
_EFF_NAME = {
    "poison": "Poison",
    "infection": "Infection",
    "virus": "Virus",
    "brulure": "Brûlure",
    "regen": "Régénération",
}
_EFF_EMOJI = {
    "poison": "💊",
    "infection": "🧟",
    "virus": "🦠",
    "brulure": "🔥",
    "regen": "💕",
}

def _mins_left(remaining_seconds: Optional[int]) -> Optional[int]:
    if remaining_seconds is None:
        return None
    try:
        m = max(0, int(round(remaining_seconds / 60)))
        return m
    except Exception:
        return None

# ─────────────────────────────────────────────────────────────
# Broadcaster des ticks (appelé par effects_db)
# ─────────────────────────────────────────────────────────────
async def _effects_broadcaster(bot: commands.Bot, guild_id: int, channel_id: int, payload: Dict):
    """
    Formate les ticks *comme sur tes captures* :
      • "@Cible subit X dégâts (Poison)."
      • Ligne calcul avec PV/PB
      • "Temps restant : N min"

    Le payload idéal contient :
      kind: "tick", effect: "poison|infection|virus|brulure|regen",
      user_id, amount (int, dmg>0 / heal>0),
      hp_before, hp_after, shield_before, shield_after,
      remaining_s (secs)
    Fallback : on utilise 'title' + 'lines'.
    """
    # choisit le bon salon (souvent celui mémorisé à l’application)
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

    # 1) Bouclier détruit (signal dédié)
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
        if cause in ("poison","infection","brulure"):
            cause_txt = {
                "poison": " sous l'effet du poison.",
                "infection": " sous l'effet de l'infection.",
                "brulure": " sous l'effet de la brûlure.",
            }[cause]
        emb = discord.Embed(
            title="🛡️ Bouclier détruit",
            description=f"Le bouclier de {who} a été **détruit**{cause_txt}",
            color=discord.Color.blurple()
        )
        await channel.send(embed=emb)
        return

    kind = str(payload.get("kind") or "")
    eff = str(payload.get("effect") or payload.get("eff_type") or "").lower()
    amount = payload.get("amount")  # dégâts bruts d’un tick (côté effet)
    hp_before = payload.get("hp_before"); hp_after = payload.get("hp_after")
    sh_before = payload.get("shield_before"); sh_after = payload.get("shield_after")
    remaining_s = payload.get("remaining_s", payload.get("remaining"))

    # 2) Tick structuré
    if (kind and "tick" in kind) or (amount is not None and hp_before is not None and hp_after is not None):
        # chercher la cible pour mention
        member = None
        try:
            gid_obj = bot.get_guild(int(target_gid))
            if gid_obj and uid:
                member = gid_obj.get_member(int(uid))
        except Exception:
            member = None
        who = member.mention if member else (f"<@{uid}>" if uid else "Quelqu'un")

        emj = _EFF_EMOJI.get(eff, "⏳")
        name = _EFF_NAME.get(eff, eff.capitalize() if eff else "Effet")

        # dmg or heal
        dmg = None; heal = None
        try:
            v = int(amount)
            if eff == "regen" or v < 0:
                heal = abs(v)
            else:
                dmg = v
        except Exception:
            pass

        # header
        if dmg is not None:
            title = f"{emj} {who} subit **{dmg}** dégâts ({name})."
        elif heal is not None:
            title = f"{emj} {who} récupère **{heal} PV** ({name})."
        else:
            title = f"{emj} Effets en cours"

        e = discord.Embed(title=title, color=discord.Color.green())

        # ligne calcul
        try:
            hb = int(hp_before); ha = int(hp_after)
            sb = int(sh_before or 0); sa = int(sh_after or 0)
            lost_hp = max(0, hb - ha)
            lost_sh = max(0, sb - sa)
            if dmg is not None:
                # on n'affiche que ce qui bouge (comme ta 3e capture)
                if lost_hp > 0 and lost_sh == 0:
                    calc = f"❤️ {hb} - {lost_hp} PV = ❤️ {ha}"
                elif lost_sh > 0 and lost_hp == 0:
                    calc = f"🛡 {sb} - {lost_sh} PB = ❤️ {ha} / 🛡 {sa}"
                else:
                    # les deux bougent : on affiche PV et PB séparés
                    calc = f"❤️ {hb} - {lost_hp} PV, 🛡 {sb} - {lost_sh} PB = ❤️ {ha} / 🛡 {sa}"
                e.description = calc
            elif heal is not None:
                gain = max(0, ha - hb)
                calc = f"❤️ {hb} + {gain} PV = ❤️ {ha}"
                e.description = calc
        except Exception:
            pass

        # minutes restantes
        mins = _mins_left(remaining_s)
        if mins is not None:
            e.add_field(name="⏳ Temps restant", value=f"{mins} min", inline=False)

        await channel.send(embed=e)

        # annonce "bouclier détruit" si ce tick l’a cassé
        try:
            if int(sh_before or 0) > 0 and int(sh_after or 0) == 0 and int(hp_before) == int(hp_after):
                emb = discord.Embed(
                    title="🛡️ Bouclier détruit",
                    description=f"Le bouclier de {who} a été **détruit**.",
                    color=discord.Color.blurple()
                )
                await channel.send(embed=emb)
        except Exception:
            pass
        return

    # 3) Fallback: on affiche ce qu’on reçoit
    embed = discord.Embed(
        title=str(payload.get("title", "GotValis")),
        color=int(payload.get("color", discord.Color.blurple().value))
    )
    lines = payload.get("lines") or []
    if lines:
        embed.description = "\n".join(str(x) for x in lines)
    await channel.send(embed=embed)

# ─────────────────────────────────────────────────────────────
# Le COG
# ─────────────────────────────────────────────────────────────
class CombatCog(commands.Cog):
    """Système de combat : /fight (les soins/boucliers sont dans heal_cog.py)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # expose la fonction pour les autres cogs (heal) afin qu’ils mémorisent le salon
        self.bot.gv_remember_tick_channel = remember_tick_channel  # type: ignore[attr-defined]
        # Broadcaster central (ne pas laisser d’autres cogs le remplacer)
        set_broadcaster(lambda gid, cid, pld: asyncio.create_task(_effects_broadcaster(self.bot, gid, cid, pld)))
        self.bot._gv_broadcaster_from_combat = True  # flag vu par d'autres cogs
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
    # Pipeline dégâts
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

        # Esquive
        dodge = await self._compute_dodge_chance(target.id)
        if random.random() < dodge:
            try:
                await trigger("on_defense_after",
                              defender_id=target.id, attacker_id=attacker.id,
                              final_taken=0, dodged=True)
            except Exception:
                pass
            return 0, 0, True, "\n🛰️ **Esquive !**"

        # Pré-défense (passifs)
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

        # Réduction pourcent (🪖)
        dr_pct = await self._compute_reduction_pct(target.id)

        # Calcul final (côté PV; PB absorbé géré dans stats_db)
        if cancel:
            dmg_final = 0
        else:
            dmg_final = int(base_damage * (0.5 if half else 1.0))
            dmg_final = int(dmg_final * (1.0 - dr_pct))
            dmg_final = max(0, dmg_final - flat)

        # Appliquer (deal_damage renvoie absorbed PB)
        res = await deal_damage(attacker.id, target.id, int(dmg_final))
        absorbed = int(res.get("absorbed", 0) or 0)

        # Contre
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
        gif_url: Optional[str] = None,
        explained: Optional[Dict[str, int]] = None,
        crit: bool = False,
    ) -> discord.Embed:
        e = discord.Embed(title=f"{emoji} Action de GotValis", color=discord.Color.orange())

        if dodged:
            e.description = f"{attacker.mention} tente {emoji} sur {target.mention}…\n🛰️ **Esquive !**{ko_txt}"
            if gif_url:
                e.set_image(url=gif_url)
            return e

        line1 = (
            f"{attacker.mention} inflige **{lost_hp}** (*{base_raw} bruts*) "
            f"dégâts à {target.mention} avec {emoji} !"
        )
        if crit and lost_hp > 0:
            line1 += "  💥 **Coup critique !**"

        line2, line3 = self._format_loss_breakdown(
            hp_before, shield_before, base_raw, lost_hp, lost_shield, explained=explained
        )
        e.description = "\n".join([line1, line2, line3] + ([ko_txt.strip()] if ko_txt else []))
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
    ) -> None:
        # Base dégâts
        base = await self._roll_value(info, 5)

        # Critiques (×2 demandé)
        crit_chance = float(info.get("crit_chance", 0.10) or 0.0)
        crit_mult   = float(info.get("crit_mult", 2.0) or 2.0)
        is_crit = (random.random() < max(0.0, min(crit_chance, 1.0)))
        base_for_display = base
        if is_crit:
            base = int(round(base * max(1.0, crit_mult)))

        # Malus d'attaque
        attacker_pen = int(await self._calc_outgoing_penalty(attacker.id, base))
        base_after_pen = max(0, base - attacker_pen)

        # Virus : transfert avant le coup
        try:
            await transfer_virus_on_attack(attacker.id, target.id)
        except Exception:
            pass

        # États avant
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

        # Décomposition explicable
        explained: Optional[Dict[str, int]] = None
        if explain_damage_modifiers:
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

        # GIF
        gif_normal = None
        try:
            gif_normal = FIGHT_GIFS.get(emoji)
        except Exception:
            gif_normal = None
        gif_url = CRIT_GIF if (is_crit and not dodged and dmg_final > 0) else gif_normal

        # Embed
        e = self._attack_embed(
            emoji=emoji,
            attacker=attacker,
            target=target,
            base_raw=base_for_display,
            lost_hp=dmg_final,
            lost_shield=absorbed,
            hp_before=hp_before,
            shield_before=shield_before,
            ko_txt=ko_txt,
            dodged=dodged,
            gif_url=gif_url,
            explained=explained,
            crit=is_crit,
        )
        await inter.followup.send(embed=e)

        # Annonce bouclier détruit par CE coup
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

    # Affichage d’application d’un DOT + fiche info
    async def _announce_dot_apply(self, inter: discord.Interaction, applier: discord.Member,
                                  target: discord.Member, typ: str, obj_emoji: str, val: int,
                                  interval: int, duration: int) -> None:
        emj = _EFF_EMOJI.get(typ, obj_emoji)
        name = _EFF_NAME.get(typ, typ.capitalize())

        # “Action de GotValis”
        e1 = discord.Embed(
            title=f"{emj} Action de GotValis",
            description=f"{applier.mention} a appliqué **{name.lower()}** sur {target.mention} avec {obj_emoji}.",
            color=discord.Color.orange()
        )
        gif = None
        try:
            gif = FIGHT_GIFS.get(obj_emoji)
        except Exception:
            gif = None
        if gif:
            e1.set_image(url=gif)
        await inter.followup.send(embed=e1)

        # Fiche info (texte à la 2e capture)
        mins = max(1, int(round(interval/60))) if interval else 1
        total_mins = max(1, int(round(duration/60))) if duration else 1
        hours = total_mins // 60
        dur_txt = f"{hours} heures" if hours >= 1 and total_mins % 60 == 0 else f"{total_mins} minutes"
        if typ == "poison":
            title = "🧪 Contamination toxique"
            desc = f"Le poison infligera **{val} PV** toutes les **{mins} minutes** pendant **{dur_txt}**."
        elif typ == "infection":
            title = "🧟 Infection active"
            desc = f"L'infection infligera **{val} PV** toutes les **{mins} minutes** pendant **{dur_txt}**."
        elif typ == "brulure":
            title = "🔥 Brûlure persistante"
            desc = f"La brûlure infligera **{val} PV** toutes les **{mins} minutes** pendant **{dur_txt}**."
        else:  # virus
            title = "🦠 Virus"
            desc = f"Le virus infligera **{val} PV** toutes les **{mins} minutes** pendant **{dur_txt}**.\n⚠️ Se **transmet sur attaque**."

        e2 = discord.Embed(title=title, description=desc, color=discord.Color.dark_green())
        await inter.followup.send(embed=e2)

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
            # 1er coup + coup en chaîne discret
            await self._apply_attack(inter, inter.user, cible, objet, info)
            try:
                base = await self._roll_value(info, 5)
                base = int(round(base * float(info.get("chain_factor", 0.6) or 0.6)))
                attacker_pen = int(await self._calc_outgoing_penalty(inter.user.id, base))
                base = max(0, base - attacker_pen)
                if base > 0:
                    await transfer_virus_on_attack(inter.user.id, cible.id)
                    await self._resolve_hit(inter, inter.user, cible, base, False, None)
            except Exception:
                pass
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
            duration = int(info.get("duree", info.get("duration", 10800)) or 10800)  # 3h par défaut

            # router les ticks ici
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
                # Style “immunisé(e)”
                e = discord.Embed(
                    title=_EFF_EMOJI.get(typ, "") + f" { _EFF_NAME.get(typ, typ.capitalize()) }",
                    description=f"⛔ {cible.mention} est **immunisé(e)**.",
                    color=discord.Color.red()
                )
                return await inter.followup.send(embed=e)

            # Annonces comme tes captures
            await self._announce_dot_apply(inter, inter.user, cible, typ, objet, val, interval, duration)

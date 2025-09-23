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
# >>> FIX: import robuste. On tente FIGHT_GIFS, sinon GIFS (alias).
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
async def _effects_broadcaster(bot: commands.Bot, guild_id: int, channel_id: int, payload: Dict):
    target_gid = guild_id
    target_cid = channel_id
    uid = payload.get("user_id")
    if uid is not None and int(uid) in _tick_channels:
        target_gid, target_cid = _tick_channels[int(uid)]
    channel = bot.get_channel(int(target_cid))
    if not channel or not isinstance(channel, (discord.TextChannel, discord.Thread)):
        channel = bot.get_channel(int(channel_id))
        if not channel: return
    embed = discord.Embed(title=str(payload.get("title", "GotValis")), color=payload.get("color", 0x2ecc71))
    lines = payload.get("lines") or []
    if lines: embed.description = "\n".join(lines)
    await channel.send(embed=embed)

# ─────────────────────────────────────────────────────────────
# Le COG
# ─────────────────────────────────────────────────────────────
class CombatCog(commands.Cog):
    """Système de combat : /fight /heal /use + commandes de test."""

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

        dodge = await self._compute_dodge_chance(target.id)
        if random.random() < dodge:
            try:
                await trigger("on_defense_after",
                              defender_id=target.id, attacker_id=attacker.id,
                              final_taken=0, dodged=True)
            except Exception:
                pass
            return 0, 0, True, "\n🛰️ **Esquive !**"

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

        dr_pct = await self._compute_reduction_pct(target.id)

        if cancel:
            dmg_final = 0
        else:
            dmg_final = int(base_damage * (0.5 if half else 1.0))
            dmg_final = int(dmg_final * (1.0 - dr_pct))
            dmg_final = max(0, dmg_final - flat)

        res = await deal_damage(attacker.id, target.id, int(dmg_final))
        absorbed = int(res.get("absorbed", 0) or 0)

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

    # ========= AFFICHAGE “ANCIEN STYLE” (avec GIF en bas) =========
    def _oldstyle_embed(
        self,
        emoji: str,
        attacker: discord.Member,
        target: discord.Member,
        hp_before: int,
        pv_lost: int,
        hp_after: int,
        ko_txt: str,
        dodged: bool
    ) -> discord.Embed:
        title = f"{emoji} Action de GotValis"
        e = discord.Embed(title=title, color=discord.Color.orange())
        if dodged:
            e.description = f"{attacker.mention} tente {emoji} sur {target.mention}…\n🛰️ **Esquive !**{ko_txt}"
        else:
            lines = [
                f"{attacker.mention} inflige **{pv_lost}** dégâts à {target.mention} avec {emoji} !",
                f"{target.mention} perd (**{pv_lost} PV**)",
                f"❤️ **{hp_before} PV** - (**{pv_lost} PV**) = ❤️ **{hp_after} PV**"
            ]
            if ko_txt:
                lines.append(ko_txt.strip())
            e.description = "\n".join(lines)
        gif = FIGHT_GIFS.get(emoji) if isinstance(FIGHT_GIFS, dict) else None
        if isinstance(gif, str) and (gif.startswith("http://") or gif.startswith("https://")):
            e.set_image(url=gif)
        return e
        
    # ========= ACTIONS CONCRÈTES (manquantes) =========
    async def _roll_value(self, info: dict, key_default: int = 1) -> int:
        """
        Lit une valeur dans info:
        - si 'min'/'max' → random entre min et max
        - sinon 'valeur' ou clé par défaut
        """
        import random
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
        import random
        # Base dégâts
        base = await self._roll_value(info, 5)
        # Critiques (facultatif dans OBJETS)
        crit_chance = float(info.get("crit_chance", 0.10) or 0.0)
        crit_mult   = float(info.get("crit_mult", 1.5) or 1.0)
        is_crit = (random.random() < max(0.0, min(crit_chance, 1.0)))
        if is_crit:
            base = int(round(base * max(1.0, crit_mult)))

        # Malus d'attaque provenant des effets (ex: poison) ou passifs
        base -= int(await self._calc_outgoing_penalty(attacker.id, base))
        base = max(0, base)

        # Virus : transfert avant le coup
        try:
            await transfer_virus_on_attack(attacker.id, target.id)
        except Exception:
            pass

        # Résolution du coup
        hp_before, _ = await get_hp(target.id)
        dmg_final, absorbed, dodged, ko_txt = await self._resolve_hit(
            inter, attacker, target, base, is_crit, None
        )
        hp_after, _ = await get_hp(target.id)

        # Hook passifs (best effort)
        try:
            await trigger("on_attack", attacker_id=attacker.id, target_id=target.id, damage_done=dmg_final)
        except Exception:
            pass

        # Embed
        e = self._oldstyle_embed(
            emoji, attacker, target, hp_before, dmg_final, hp_after, ko_txt, dodged
        )
        if is_crit and not dodged and dmg_final > 0:
            e.add_field(name="💥 Critique !", value=f"x{crit_mult:g}", inline=True)
        if absorbed > 0 and not dodged:
            e.add_field(name="🛡 Bouclier", value=f"-{absorbed} absorbés", inline=True)
        return e

    async def _apply_chain_attack(
        self,
        inter: discord.Interaction,
        attacker: discord.Member,
        target: discord.Member,
        emoji: str,
        info: dict
    ) -> discord.Embed:
        """
        Version simple : on applique un coup principal, puis un 'rebond' à 60%.
        (Tu pourras remplacer par une vraie chaîne multi-cibles si tu veux.)
        """
        # Coup principal
        embed = await self._apply_attack(inter, attacker, target, emoji, info)

        # Rebond atténué
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

    async def _apply_dot(
        self,
        inter: discord.Interaction,
        user: discord.Member,
        cible: discord.Member,
        emoji: str,
        info: dict,
        *,
        eff_type: str,
        label: str
    ) -> discord.Embed:
        # Paramètres du DOT/HoT
        val = await self._roll_value(info, 1)
        interval = int(info.get("interval", info.get("tick", 60)) or 60)
        duration = int(info.get("duree", info.get("duration", 300)) or 300)

        remember_tick_channel(cible.id, inter.guild.id, inter.channel.id)

        # Hook passifs (blocage possible)
        try:
            pre = await trigger("on_effect_pre_apply", user_id=cible.id, eff_type=eff_type) or {}
            if pre.get("blocked"):
                return discord.Embed(
                    title=f"{label}",
                    description=f"⛔ Effet bloqué sur {cible.mention} : {pre.get('reason','')}",
                    color=discord.Color.red()
                )
        except Exception:
            pass

        ok = await add_or_refresh_effect(
            user_id=cible.id, eff_type=eff_type, value=float(val),
            duration=duration, interval=interval,
            source_id=user.id, meta_json=json.dumps({"applied_in": inter.channel.id})
        )
        if not ok:
            return discord.Embed(
                title=f"{label}",
                description=f"⛔ {cible.mention} est **immunisé(e)**.",
                color=discord.Color.red()
            )

        e = discord.Embed(
            title=f"{label}",
            description=f"{user.mention} applique **{emoji}** sur {cible.mention} "
                        f"(val={val}, every {interval}s, dur={duration}s).",
            color=discord.Color.orange()
        )
        return e

    async def _apply_heal(
        self,
        inter: discord.Interaction,
        user: discord.Member,
        emoji: str,
        info: dict,
        cible: Optional[discord.Member]
    ) -> discord.Embed:
        target = cible or user
        amount = await self._roll_value(info, 10)

        # Soin avec attribution (crédite l'éco du lanceur)
        healed = await heal_user(user.id, target.id, amount)

        hp_before, mx = await get_hp(target.id)
        # hp_before est déjà à jour si heal_user a écrit ? On relit pour être sûr :
        hp_after, mx = await get_hp(target.id)

        e = discord.Embed(title="💊 Soin", color=discord.Color.green())
        if healed <= 0:
            e.description = f"{user.mention} tente de soigner {target.mention} avec {emoji}, " \
                            f"mais les PV sont déjà au max."
        else:
            e.description = (
                f"{user.mention} rend **{healed} PV** à {target.mention} avec {emoji}.\n"
                f"❤️ **{hp_after-healed}/{mx}** + (**{healed}**) = ❤️ **{hp_after}/{mx}**"
            )
        return e

    async def _apply_regen(
        self,
        inter: discord.Interaction,
        user: discord.Member,
        emoji: str,
        info: dict,
        cible: Optional[discord.Member]
    ) -> discord.Embed:
        target = cible or user
        val = await self._roll_value(info, 2)
        interval = int(info.get("interval", 60) or 60)
        duration = int(info.get("duree", 300) or 300)

        remember_tick_channel(target.id, inter.guild.id, inter.channel.id)

        pre = {}
        try:
            pre = await trigger("on_effect_pre_apply", user_id=target.id, eff_type="regen") or {}
        except Exception:
            pass
        if pre.get("blocked"):
            return discord.Embed(
                title="💕 Régénération",
                description=f"⛔ Effet bloqué : {pre.get('reason','')}",
                color=discord.Color.red()
            )

        await add_or_refresh_effect(
            user_id=target.id, eff_type="regen", value=float(val),
            duration=duration, interval=interval, source_id=user.id,
            meta_json=json.dumps({"applied_in": inter.channel.id})
        )
        return discord.Embed(
            title="💕 Régénération",
            description=f"{user.mention} applique **{emoji}** sur {target.mention} "
                        f"(+{val} PV / {interval}s pendant {duration}s).",
            color=discord.Color.teal()
        )

    async def _apply_vaccin(
        self,
        inter: discord.Interaction,
        user: discord.Member,
        info: dict,
        cible: Optional[discord.Member]
    ) -> discord.Embed:
        target = cible or user

        # Cleanse de base
        for t in ("poison", "infection", "virus", "brulure"):
            try:
                await remove_effect(target.id, t)  # type: ignore[attr-defined]
            except Exception:
                try:
                    from effects_db import remove_effect as _rem
                    await _rem(target.id, t)
                except Exception:
                    pass

        # Immunité temporaire (facultatif selon OBJETS)
        dur = int(info.get("duree", info.get("duration", 180)) or 180)
        val = int(info.get("valeur", 1) or 1)
        remember_tick_channel(target.id, inter.guild.id, inter.channel.id)
        try:
            await add_or_refresh_effect(
                user_id=target.id, eff_type="immunite", value=float(val),
                duration=dur, interval=0, source_id=user.id,
                meta_json=json.dumps({"applied_in": inter.channel.id, "source": "vaccin"})
            )
        except Exception:
            pass

        return discord.Embed(
            title="🧬 Vaccin",
            description=f"{user.mention} immunise {target.mention} et retire les altérations.",
            color=discord.Color.blue()
        )

    async def _apply_bouclier(
        self,
        inter: discord.Interaction,
        user: discord.Member,
        info: dict,
        cible: Optional[discord.Member]
    ) -> discord.Embed:
        target = cible or user
        val = await self._roll_value(info, 5)

        applied = 0
        # Priorité au module shields_db s'il existe
        try:
            from shields_db import add_shield as _add_shield, get_shield as _get_shield, get_max_shield as _get_max
            before = await _get_shield(target.id)
            applied = await _add_shield(target.id, val, cap_to_max=True)
            after = await _get_shield(target.id)
            cap = await _get_max(target.id)
            desc = f"🛡 {target.mention} gagne **{max(0, after-before)} PB** (cap {cap})."
        except Exception:
            # Fallback: stocke dans stats_db.shield
            try:
                from stats_db import get_shield as _get, set_shield as _set
                before = int(await _get(target.id))
                after = max(0, before + int(val))
                await _set(target.id, after)
                desc = f"🛡 {target.mention} gagne **{val} PB**."
            except Exception:
                desc = f"🛡 {target.mention} gagne un bouclier."

        return discord.Embed(title="🛡 Bouclier", description=desc, color=discord.Color.brand_teal())

    # ========= Inventaire réel pour l’auto-complétion =========
    async def _list_owned_items(self, uid: int) -> List[Tuple[str, int]]:
        owned: List[Tuple[str, int]] = []

        # 1) Tentative via get_all_items (toutes formes tolérées)
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

        # 2) Fallback forcé si rien trouvé: interroge chaque emoji
        if not owned:
            for emoji in OBJETS.keys():
                try:
                    q = int(await get_item_qty(uid, emoji) or 0)
                    if q > 0:
                        owned.append((emoji, q))
                except Exception:
                    continue

        # 3) Merge & tri
        merged: Dict[str, int] = {}
        for e, q in owned:
            merged[e] = merged.get(e, 0) + int(q)
        return sorted(merged.items(), key=lambda t: t[0])

    # ─────────────────────────────────────────────────────────
    # AUTOCOMPLÉTIONS — items possédés (sélection par type)
    # ─────────────────────────────────────────────────────────
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
        return out  # pas de fallback: on ne montre que ce que tu possèdes

    async def _ac_items_attack(self, inter: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        return await self._ac_items_by_type(
            inter, current,
            ("attaque", "attaque_chaine", "poison", "infection", "virus", "brulure")
        )

    async def _ac_items_heal(self, inter: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        return await self._ac_items_by_type(inter, current, ("soin", "regen"))

    async def _ac_items_any(self, inter: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        return await self._ac_items_by_type(
            inter, current,
            ("attaque", "attaque_chaine", "soin", "regen",
             "vaccin", "bouclier", "mysterybox", "vol", "esquive+", "reduction", "immunite")
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
            label = {
                "poison": "🧪 Poison",
                "infection": "🧟 Infection",
                "virus": "🦠 Virus (transfert sur attaque)",
                "brulure": "🔥 Brûlure",
            }[typ]
            embed = await self._apply_dot(inter, inter.user, cible, objet, info, eff_type=typ, label=label)

        await inter.followup.send(embed=embed)
        await self._maybe_update_leaderboard(inter.guild.id, "fight")

    # ─────────────────────────────────────────────────────────
    # /heal — soin
    # ─────────────────────────────────────────────────────────
    @app_commands.command(name="heal", description="Soigner un joueur avec un objet de soin.")
    @app_commands.describe(objet="Choisis un objet de soin", cible="Cible (par défaut: toi)")
    @app_commands.autocomplete(objet=_ac_items_heal)
    async def heal(self, inter: discord.Interaction, objet: str, cible: Optional[discord.Member] = None):
        info = self._obj_info(objet)
        if not info or info.get("type") not in ("soin", "regen"):
            return await inter.response.send_message("Objet invalide : il faut un objet **de soin**.", ephemeral=True)

        if not await self._consume_item(inter.user.id, objet):
            return await inter.response.send_message(f"Tu n’as pas **{objet}** dans ton inventaire.", ephemeral=True)

        await inter.response.defer(thinking=True)

        try:
            if info["type"] == "soin":
                embed = await self._apply_heal(inter, inter.user, objet, info, cible)
            else:
                embed = await self._apply_regen(inter, inter.user, objet, info, cible)
        except Exception as e:
            embed = discord.Embed(
                title="❗ Erreur pendant le soin",
                description=f"Une erreur est survenue: `{type(e).__name__}`. L’action a été annulée.",
                color=discord.Color.red()
            )

        await inter.followup.send(embed=embed)
        await self._maybe_update_leaderboard(inter.guild.id, "heal")

    # ─────────────────────────────────────────────────────────
    # /use — utilitaires (DOTs retirés)
    # ─────────────────────────────────────────────────────────
    @app_commands.command(name="use", description="Utiliser un objet de ton inventaire.")
    @app_commands.describe(objet="Choisis un objet", cible="Cible (selon l'objet)")
    @app_commands.autocomplete(objet=_ac_items_any)
    async def use(self, inter: discord.Interaction, objet: str, cible: Optional[discord.Member] = None):
        info = self._obj_info(objet)
        if not info:
            return await inter.response.send_message("Objet inconnu.", ephemeral=True)

        if not await self._consume_item(inter.user.id, objet):
            return await inter.response.send_message(f"Tu n’as pas **{objet}** dans ton inventaire.", ephemeral=True)

        await inter.response.defer(thinking=True)

        typ = info.get("type")
        embed: Optional[discord.Embed] = None

        if typ == "attaque":
            if not isinstance(cible, discord.Member):
                return await inter.followup.send("Il faut une **cible** pour attaquer.")
            embed = await self._apply_attack(inter, inter.user, cible, objet, info)

        elif typ == "attaque_chaine":
            if not isinstance(cible, discord.Member):
                return await inter.followup.send("Il faut une **cible** pour attaquer.")
            embed = await self._apply_chain_attack(inter, inter.user, cible, objet, info)

        elif typ == "soin":
            embed = await self._apply_heal(inter, inter.user, objet, info, cible)

        elif typ == "regen":
            embed = await self._apply_regen(inter, inter.user, objet, info, cible)

        elif typ == "vaccin":
            embed = await self._apply_vaccin(inter, inter.user, info, cible)

        elif typ == "bouclier":
            embed = await self._apply_bouclier(inter, inter.user, info, cible)

        elif typ == "mysterybox":
            got = get_random_item(debug=False)
            await add_item(inter.user.id, got, 1)
            embed = discord.Embed(title="📦 Box ouverte", description=f"{inter.user.mention} obtient **{got}** !", color=discord.Color.gold())
            try:
                post = await trigger("on_box_open", user_id=inter.user.id) or {}
            except Exception:
                post = {}
            if int(post.get("extra_items", 0)) > 0:
                extra = get_random_item(debug=False)
                await add_item(inter.user.id, extra, 1)
                embed.description += f"\n🎁 Bonus: **{extra}**"

        elif typ == "vol":
            if isinstance(cible, discord.Member):
                try:
                    res = await trigger("on_theft_attempt", attacker_id=inter.user.id, target_id=cible.id) or {}
                except Exception:
                    res = {}
                if res.get("blocked"):
                    return await inter.followup.send(f"🛡 {cible.mention} est **intouchable** (anti-vol).")
            success = (random.random() < 0.25)
            if success:
                got = get_random_item(debug=False)
                await add_item(inter.user.id, got, 1)
                desc = f"🕵️ Vol réussi ! Tu obtiens **{got}**."
            else:
                desc = "🕵️ Vol raté..."
            embed = discord.Embed(title="Vol", description=desc, color=discord.Color.dark_grey())

        elif typ in ("esquive+", "reduction", "immunite"):
            who = cible or inter.user
            remember_tick_channel(who.id, inter.guild.id, inter.channel.id)
            val = int(info.get("valeur", 0) or 0)
            dur = int(info.get("duree", 3600) or 3600)
            block = await trigger("on_effect_pre_apply", user_id=who.id, eff_type=str(typ)) or {}
            if block.get("blocked"):
                return await inter.followup.send(f"⚠️ Effet bloqué: {block.get('reason','')}")
            await add_or_refresh_effect(
                user_id=who.id, eff_type=str(typ), value=val,
                duration=dur, interval=0,
                source_id=inter.user.id, meta_json=json.dumps({"applied_in": inter.channel.id})
            )
            labels = {"esquive+": "👟 Esquive+", "reduction": "🪖 Réduction de dégâts", "immunite": "⭐️ Immunité"}
            embed = discord.Embed(
                title=labels.get(typ, "Buff"),
                description=f"{inter.user.mention} applique **{objet}** sur {who.mention}.",
                color=discord.Color.blurple()
            )
        else:
            embed = discord.Embed(
                title="Objet non géré",
                description=f"{objet} ({typ}) n’a pas de logique dédiée pour le moment.",
                color=discord.Color.dark_grey()
            )

        try:
            post = await trigger("on_use_item", user_id=inter.user.id, item_emoji=objet, item_type=str(typ)) or {}
        except Exception:
            post = {}
        if post.get("dont_consume"):
            try: await add_item(inter.user.id, objet, 1)
            except Exception: pass

        await inter.followup.send(embed=embed)
        await self._maybe_update_leaderboard(inter.guild.id, "use")

    # ─────────────────────────────────────────────────────────
    # Commandes de test
    # ─────────────────────────────────────────────────────────
    @app_commands.command(name="hit", description="(test) Inflige des dégâts directs à une cible.")
    @app_commands.describe(target="Cible", amount="Dégâts directs")
    async def hit(self, inter: discord.Interaction, target: discord.Member, amount: int):
        if amount <= 0:
            return await inter.response.send_message("Le montant doit être > 0.", ephemeral=True)
        await inter.response.defer(thinking=True)
        base = int(amount)
        if await king_execute_ready(inter.user.id, target.id):
            base = max(base, 10_000_000)
        base -= int(await self._calc_outgoing_penalty(inter.user.id, base))
        base = max(0, base)
        await transfer_virus_on_attack(inter.user.id, target.id)
        hp_before, _ = await get_hp(target.id)
        dmg_final, absorbed, dodged, ko_txt = await self._resolve_hit(inter, inter.user, target, base, False, None)
        hp_after, _ = await get_hp(target.id)
        try:
            await trigger("on_attack", attacker_id=inter.user.id, target_id=target.id, damage_done=dmg_final)
        except Exception:
            pass
        embed = self._oldstyle_embed("⚔️", inter.user, target, hp_before, dmg_final, hp_after, ko_txt, dodged)
        await inter.followup.send(embed=embed)
        await self._maybe_update_leaderboard(inter.guild.id, "hit")

    @app_commands.command(name="poison", description="(test) Applique un poison à une cible.")
    @app_commands.describe(target="Cible")
    async def cmd_poison(self, inter: discord.Interaction, target: discord.Member):
        await inter.response.defer(thinking=True)
        remember_tick_channel(target.id, inter.guild.id, inter.channel.id)
        cfg = {"value": 2, "interval": 60, "duration": 600}
        block = await trigger("on_effect_pre_apply", user_id=target.id, eff_type="poison") or {}
        if block.get("blocked"):
            return await inter.followup.send(f"🧪 Bloqué: {block.get('reason','')}")
        await add_or_refresh_effect(
            user_id=target.id, eff_type="poison", value=cfg["value"], duration=cfg["duration"], interval=cfg["interval"],
            source_id=inter.user.id, meta_json=json.dumps({"applied_in": inter.channel.id})
        )
        await inter.followup.send(f"🧪 {target.mention} est **empoisonné**.")

    @app_commands.command(name="virus", description="(test) Applique un virus (transfert sur attaque).")
    @app_commands.describe(target="Cible")
    async def cmd_virus(self, inter: discord.Interaction, target: discord.Member):
        await inter.response.defer(thinking=True)
        remember_tick_channel(target.id, inter.guild.id, inter.channel.id)
        cfg = {"value": 0, "interval": 60, "duration": 600}
        await add_or_refresh_effect(
            user_id=target.id, eff_type="virus", value=cfg["value"], duration=cfg["duration"], interval=cfg["interval"],
            source_id=inter.user.id, meta_json=json.dumps({"applied_in": inter.channel.id})
        )
        await inter.followup.send(f"🦠 {target.mention} est **infecté par un virus** (transfert sur attaque).")

    @app_commands.command(name="infection", description="(test) Applique une infection (DOT).")
    @app_commands.describe(target="Cible")
    async def cmd_infection(self, inter: discord.Interaction, target: discord.Member):
        await inter.response.defer(thinking=True)
        remember_tick_channel(target.id, inter.guild.id, inter.channel.id)
        cfg = {"value": 2, "interval": 60, "duration": 600}
        block = await trigger("on_effect_pre_apply", user_id=target.id, eff_type="infection") or {}
        if block.get("blocked"):
            return await inter.followup.send(f"🧟 Bloqué: {block.get('reason','')}")
        await add_or_refresh_effect(
            user_id=target.id, eff_type="infection", value=cfg["value"], duration=cfg["duration"], interval=cfg["interval"],
            source_id=inter.user.id, meta_json=json.dumps({"applied_in": inter.channel.id})
        )
        await inter.followup.send(f"🧟 {target.mention} est **infecté**.")

    @app_commands.command(name="brulure", description="(test) Applique une brûlure (DOT).")
    @app_commands.describe(target="Cible")
    async def cmd_brulure(self, inter: discord.Interaction, target: discord.Member):
        await inter.response.defer(thinking=True)
        remember_tick_channel(target.id, inter.guild.id, inter.channel.id)
        cfg = {"value": 1, "interval": 60, "duration": 300}
        await add_or_refresh_effect(
            user_id=target.id, eff_type="brulure", value=cfg["value"], duration=cfg["duration"], interval=cfg["interval"],
            source_id=inter.user.id, meta_json=json.dumps({"applied_in": inter.channel.id})
        )
        await inter.followup.send(f"🔥 {target.mention} est **brûlé**.")

    @app_commands.command(name="regen", description="(test) Applique une régénération (HoT).")
    @app_commands.describe(target="Cible")
    async def cmd_regen(self, inter: discord.Interaction, target: discord.Member):
        await inter.response.defer(thinking=True)
        remember_tick_channel(target.id, inter.guild.id, inter.channel.id)
        cfg = {"value": 2, "interval": 60, "duration": 300}
        block = await trigger("on_effect_pre_apply", user_id=target.id, eff_type="regen") or {}
        if block.get("blocked"):
            return await inter.followup.send(f"💕 Bloqué: {block.get('reason','')}")
        await add_or_refresh_effect(
            user_id=target.id, eff_type="regen", value=cfg["value"], duration=cfg["duration"], interval=cfg["interval"],
            source_id=inter.user.id, meta_json=json.dumps({"applied_in": inter.channel.id})
        )
        await inter.followup.send(f"💕 {target.mention} bénéficie d’une **régénération**.")

    @app_commands.command(name="hp", description="(test) Affiche tes PV / PV de la cible.")
    @app_commands.describe(target="Cible (optionnel)")
    async def hp(self, inter: discord.Interaction, target: Optional[discord.Member] = None):
        target = target or inter.user
        hp, mx = await get_hp(target.id)
        await inter.response.send_message(f"❤️ {target.mention}: **{hp}/{mx}** PV")

async def setup(bot: commands.Bot):
    await bot.add_cog(CombatCog(bot))

# cogs/combat_cog.py
from __future__ import annotations

import asyncio
import json
import random
from typing import Dict, Tuple, List, Optional

import discord
from discord.ext import commands
from discord import app_commands

# ───────────────────────── Backends PV/PB ─────────────────────────
from stats_db import deal_damage, heal_user, get_hp, is_dead, revive_full
try:
    from stats_db import add_shield  # optionnel
except Exception:
    add_shield = None  # type: ignore

# ───────────────────────── Effets (DOT/HoT/buffs) ─────────────────────────
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
    async def add_or_refresh_effect(**kwargs): return None  # type: ignore
    async def remove_effect(*args, **kwargs): return None  # type: ignore
    async def has_effect(*args, **kwargs): return False  # type: ignore
    async def list_effects(*args, **kwargs): return []  # type: ignore
    async def effects_loop(*args, **kwargs): return None  # type: ignore
    def  set_broadcaster(*args, **kwargs): return None  # type: ignore
    async def transfer_virus_on_attack(*args, **kwargs): return None  # type: ignore
    async def get_outgoing_damage_penalty(*args, **kwargs): return 0  # type: ignore

# ───────────────────────── Économie / Inventaire ─────────────────────────
from economy_db import add_balance, get_balance  # (utilisable si besoin)
from inventory_db import get_item_qty, remove_item, add_item

# ───────────────────────── Passifs (avec stubs robustes) ─────────────────────────
try:
    from passifs import trigger  # routeur d’évènements
except Exception:
    async def trigger(*args, **kwargs):
        return {}

try:
    from passifs import get_extra_dodge_chance
except Exception:
    async def get_extra_dodge_chance(*args, **kwargs) -> float:
        return 0.0

try:
    from passifs import get_extra_reduction_percent
except Exception:
    async def get_extra_reduction_percent(*args, **kwargs) -> float:
        return 0.0

try:
    from passifs import king_execute_ready
except Exception:
    async def king_execute_ready(*args, **kwargs) -> bool:
        return False

try:
    from passifs import undying_zeyra_check_and_mark
except Exception:
    async def undying_zeyra_check_and_mark(*args, **kwargs) -> bool:
        return False

try:
    from passifs import modify_infection_application
except Exception:
    async def modify_infection_application(*args, **kwargs) -> int:
        # pas d’ajustement si non dispo
        return int(args[-1]) if args else 0

# ───────────────────────── Objets (emoji -> data) ─────────────────────────
try:
    from utils import OBJETS, get_random_item  # type: ignore
except Exception:
    OBJETS = {}
    def get_random_item(debug: bool = False):
        return random.choice(["🍀", "❄️", "🧪", "🩹", "💊"])

# ───────────────────────── Mapping salons pour ticks ─────────────────────────
_tick_channels: Dict[int, Tuple[int, int]] = {}

def remember_tick_channel(user_id: int, guild_id: int, channel_id: int) -> None:
    _tick_channels[int(user_id)] = (int(guild_id), int(channel_id))

def get_all_tick_targets() -> List[Tuple[int, int]]:
    seen: set[Tuple[int, int]] = set()
    for pair in _tick_channels.values():
        seen.add(pair)
    return list(seen)

# ───────────────────────── Broadcaster appelé par effects_db ─────────────────────────
async def _effects_broadcaster(bot: commands.Bot, guild_id: int, channel_id: int, payload: Dict):
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

    embed = discord.Embed(title=str(payload.get("title", "GotValis")),
                          color=payload.get("color", 0x2ecc71))
    lines = payload.get("lines") or []
    if lines:
        embed.description = "\n".join(lines)
    await channel.send(embed=embed)

# ════════════════════════════════════════ COG ════════════════════════════════════════

class CombatCog(commands.Cog):
    """Système de combat : /fight /heal /use + commandes de test."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # branche le broadcaster des ticks
        set_broadcaster(lambda gid, cid, pld: asyncio.create_task(
            _effects_broadcaster(self.bot, gid, cid, pld)
        ))
        # lance la boucle des effets (scan) si pas déjà en cours
        self._start_effects_loop_once()

    def _start_effects_loop_once(self):
        if getattr(self.bot, "_effects_loop_started", False):
            return
        self.bot._effects_loop_started = True

        async def runner():
            await effects_loop(get_targets=get_all_tick_targets, interval=30)

        asyncio.create_task(runner())

    # ───────────────────────── Helpers ─────────────────────────
    async def _consume_item(self, user_id: int, emoji: str) -> bool:
        """Consomme 1 exemplaire si dispo. Retourne True si ok."""
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

    def _set_media(self, embed: discord.Embed, info: Dict) -> None:
        """Ajoute GIF/IMAGE si fourni dans l’objet (champ 'gif' ou 'image')."""
        url = str(info.get("gif") or info.get("image") or "").strip()
        if url.startswith("http://") or url.startswith("https://"):
            embed.set_image(url=url)

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
                    try:
                        out += float(value)
                    except Exception:
                        pass
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
        """
        Compat adapter pour get_outgoing_damage_penalty :
        - get_outgoing_damage_penalty(uid, base)
        - get_outgoing_damage_penalty(uid, base=base)
        - get_outgoing_damage_penalty(uid) -> int | {"flat":x,"percent":y}
        """
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
                pct = float(res.get("percent", 0.0) or 0.0)
                return max(0, int(flat + round(base * pct)))
            return max(0, int(res or 0))
        except Exception:
            return 0

    # ───────────────────────── Pipeline dégâts / soins ─────────────────────────
    async def _resolve_hit(
        self,
        inter: discord.Interaction,
        attacker: discord.Member,
        target: discord.Member,
        base_damage: int,
        is_crit_flag: bool,
        note_footer: Optional[str] = None,
    ) -> Tuple[int, int, bool, str]:

        # 0) Esquive
        dodge = await self._compute_dodge_chance(target.id)
        if random.random() < dodge:
            try:
                await trigger("on_defense_after",
                              defender_id=target.id, attacker_id=attacker.id,
                              final_taken=0, dodged=True)
            except Exception:
                pass
            return 0, 0, True, "\n🛰️ **Esquive !**"

        # 1) Pré-défense (contre/annulation/réduction fixe)
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

        # 2) Réduction %
        dr_pct = await self._compute_reduction_pct(target.id)

        # 3) Calcul final
        if cancel:
            dmg_final = 0
        else:
            dmg_final = int(base_damage * (0.5 if half else 1.0))
            dmg_final = int(dmg_final * (1.0 - dr_pct))
            dmg_final = max(0, dmg_final - flat)

        # 4) Application PV/PB
        res = await deal_damage(attacker.id, target.id, int(dmg_final))
        absorbed = int(res.get("absorbed", 0) or 0)

        # 5) Contre-attaque éventuelle
        if counter_frac > 0 and dmg_final > 0:
            try:
                counter = max(1, int(round(dmg_final * counter_frac)))
                await deal_damage(target.id, attacker.id, counter)
            except Exception:
                pass

        # 6) Undying / KO
        ko_txt = ""
        if await is_dead(target.id):
            if await undying_zeyra_check_and_mark(target.id):
                await heal_user(target.id, target.id, 1)
                ko_txt = "\n⭐ **Volonté de Fracture** : survit à 1 PV."
            else:
                await revive_full(target.id)
                ko_txt = "\n💥 **Cible mise KO** (réanimée PV/PB)."

        # 7) Post-défense
        try:
            await trigger("on_defense_after",
                          defender_id=target.id, attacker_id=attacker.id,
                          final_taken=dmg_final, dodged=False)
        except Exception:
            pass

        return int(dmg_final), absorbed, False, ko_txt

    async def _apply_attack(self, inter: discord.Interaction, attacker: discord.Member, target: discord.Member, emoji: str, info: Dict) -> discord.Embed:
        base = int(info.get("degats", 0) or 0)

        # Finisher (Roi)
        if await king_execute_ready(attacker.id, target.id):
            base = max(base, 10_000_000)

        # Malus de sortie (anti-spam, etc.)
        penalty = await self._calc_outgoing_penalty(attacker.id, base)
        base = max(0, base - int(penalty))

        # Critique
        crit_chance = float(info.get("crit", 0.0) or 0.0)
        is_crit = (random.random() < crit_chance)
        base = int(base * (2.0 if is_crit else 1.0))

        # Virus transfert
        await transfer_virus_on_attack(attacker.id, target.id)

        # Résolution
        dmg_final, absorbed, dodged, ko_txt = await self._resolve_hit(inter, attacker, target, base, is_crit, None)
        hp, _ = await get_hp(target.id)

        # Hooks post-attaque
        try:
            await trigger("on_attack", attacker_id=attacker.id, target_id=target.id, damage_done=dmg_final)
        except Exception:
            pass

        if dodged:
            desc = f"{attacker.mention} tente {emoji} sur {target.mention}.{ko_txt}"
        else:
            desc = (f"{attacker.mention} utilise {emoji} sur {target.mention}.\n"
                    f"🎯 Dégâts: **{dmg_final}** {'(**CRIT!**)' if is_crit else ''} • "
                    f"🛡 Absorbés: {absorbed} • ❤️ PV restants: **{hp}**{ko_txt}")
        e = discord.Embed(title="⚔️ Attaque", description=desc, color=discord.Color.red())
        self._set_media(e, info)
        return e

    async def _apply_chain_attack(self, inter: discord.Interaction, attacker: discord.Member, target: discord.Member, emoji: str, info: Dict) -> discord.Embed:
        d1 = int(info.get("degats_principal", 0) or 0)
        d2 = int(info.get("degats_secondaire", 0) or 0)
        base = d1 + d2

        if await king_execute_ready(attacker.id, target.id):
            base = max(base, 10_000_000)

        penalty = await self._calc_outgoing_penalty(attacker.id, base)
        base = max(0, base - int(penalty))

        await transfer_virus_on_attack(attacker.id, target.id)

        dmg_final, absorbed, dodged, ko_txt = await self._resolve_hit(inter, attacker, target, base, False, None)
        hp, _ = await get_hp(target.id)
        try:
            await trigger("on_attack", attacker_id=attacker.id, target_id=target.id, damage_done=dmg_final)
        except Exception:
            pass

        if dodged:
            desc = f"{attacker.mention} tente {emoji} sur {target.mention}.{ko_txt}"
        else:
            desc = (f"{attacker.mention} utilise {emoji} sur {target.mention}.\n"
                    f"🎯 Dégâts totaux: **{dmg_final}** • 🛡 Absorbés: {absorbed} • ❤️ PV restants: **{hp}**{ko_txt}")
        e = discord.Embed(title="⚔️ Attaque en chaîne", description=desc, color=discord.Color.red())
        self._set_media(e, info)
        return e

    async def _apply_heal(self, inter: discord.Interaction, user: discord.Member, emoji: str, info: Dict, target: Optional[discord.Member] = None) -> discord.Embed:
        heal_amount = int(info.get("soin", 0) or 0)
        who = target or user

        try:
            pre = await trigger("on_heal_pre", healer_id=user.id, target_id=who.id, amount=heal_amount) or {}
        except Exception:
            pre = {}
        heal_amount += int(pre.get("heal_bonus", 0))
        mult = float(pre.get("mult_target", 1.0))
        heal_amount = max(0, int(round(heal_amount * mult)))

        real = await heal_user(who.id, heal_amount)
        hp, mx = await get_hp(who.id)

        try:
            await trigger("on_heal", healer_id=user.id, target_id=who.id, healed=real)
        except Exception:
            pass
        try:
            await trigger("on_any_heal", healer_id=user.id, target_id=who.id, healed=real)
        except Exception:
            pass

        e = discord.Embed(
            title="❤️ Soin",
            description=f"{user.mention} utilise {emoji} sur {who.mention}.\n➕ PV rendus: **{real}** → ❤️ **{hp}/{mx}**",
            color=discord.Color.green()
        )
        self._set_media(e, info)
        return e

    async def _apply_regen(self, inter: discord.Interaction, user: discord.Member, emoji: str, info: Dict, target: Optional[discord.Member] = None) -> discord.Embed:
        who = target or user
        remember_tick_channel(who.id, inter.guild.id, inter.channel.id)
        val = int(info.get("valeur", 0) or 0)
        interval = int(info.get("intervalle", 60) or 60)
        duration = int(info.get("duree", 3600) or 3600)

        block = await trigger("on_effect_pre_apply", user_id=who.id, eff_type="regen") or {}
        if block.get("blocked"):
            return discord.Embed(
                title="🌿 Régénération",
                description=f"{user.mention} tente {emoji} sur {who.mention}.\n⚠️ {block.get('reason','Effet bloqué.')}",
                color=discord.Color.orange()
            )

        await add_or_refresh_effect(
            user_id=who.id, eff_type="regen", value=val,
            duration=duration, interval=interval,
            source_id=user.id, meta_json=json.dumps({"applied_in": inter.channel.id})
        )
        e = discord.Embed(
            title="🌿 Régénération",
            description=f"{user.mention} applique {emoji} sur {who.mention}.\n"
                        f"➕ **{val} PV** toutes les **{max(1,interval)//60} min** pendant **{max(1,duration)//3600} h**.",
            color=discord.Color.green()
        )
        self._set_media(e, info)
        return e

    async def _apply_dot(self, inter: discord.Interaction, user: discord.Member, target: discord.Member, emoji: str, info: Dict, eff_type: str, label: str) -> discord.Embed:
        remember_tick_channel(target.id, inter.guild.id, inter.channel.id)
        val = int(info.get("degats", 0) or 0)
        interval = int(info.get("intervalle", 60) or 60)
        duration = int(info.get("duree", 3600) or 3600)

        block = await trigger("on_effect_pre_apply", user_id=target.id, eff_type=eff_type) or {}
        if block.get("blocked"):
            return discord.Embed(
                title=label,
                description=f"{user.mention} tente {emoji} sur {target.mention}.\n⚠️ {block.get('reason','Effet bloqué.')}",
                color=discord.Color.orange()
            )

        # Buff de source sur l'infection
        if eff_type == "infection":
            try:
                val = await modify_infection_application(user.id, val)
            except Exception:
                pass

        await add_or_refresh_effect(
            user_id=target.id, eff_type=eff_type, value=val,
            duration=duration, interval=interval,
            source_id=user.id, meta_json=json.dumps({"applied_in": inter.channel.id})
        )
        e = discord.Embed(
            title=f"{label}",
            description=f"{user.mention} applique {emoji} sur {target.mention}.\n"
                        f"⏳ Effet: **{val}** toutes les **{max(1,interval)//60} min** pendant **{max(1,duration)//3600} h**.",
            color=discord.Color.orange()
        )
        self._set_media(e, info)
        return e

    async def _apply_vaccin(self, inter: discord.Interaction, user: discord.Member, info: Dict, target: Optional[discord.Member] = None) -> discord.Embed:
        who = target or user
        for t in ("poison", "infection", "virus", "brulure"):
            try: await remove_effect(who.id, t)
            except Exception: pass
        e = discord.Embed(
            title="💉 Vaccin",
            description=f"{user.mention} purge les statuts négatifs de {who.mention}.",
            color=discord.Color.blurple()
        )
        self._set_media(e, info)
        return e

    async def _apply_bouclier(self, inter: discord.Interaction, user: discord.Member, info: Dict, target: Optional[discord.Member] = None) -> discord.Embed:
        who = target or user
        val = int(info.get("valeur", 0) or 0)
        ok = False
        if callable(add_shield):
            try:
                await add_shield(who.id, val)  # type: ignore
                ok = True
            except Exception:
                ok = False
        if not ok:
            try:
                remember_tick_channel(who.id, inter.guild.id, inter.channel.id)
                await add_or_refresh_effect(
                    user_id=who.id, eff_type="pb", value=val,
                    duration=int(info.get("duree", 3600) or 3600), interval=0,
                    source_id=user.id, meta_json=json.dumps({"applied_in": inter.channel.id})
                )
                ok = True
            except Exception:
                ok = False

        e = discord.Embed(
            title="🛡 Bouclier",
            description=f"{user.mention} confère **{val} PB** à {who.mention}." + ("" if ok else "\n⚠️ (Fallback, nécessite intégration PB)"),
            color=discord.Color.teal()
        )
        self._set_media(e, info)
        return e

    # ───────────────────────── AUTOCOMPLÉTIONS ─────────────────────────
    async def _ac_items_by_type(self, inter: discord.Interaction, current: str, allowed: Tuple[str, ...]) -> List[app_commands.Choice[str]]:
        uid = inter.user.id
        cur = (current or "").strip().lower()
        out: List[app_commands.Choice[str]] = []
        for emoji, info in OBJETS.items():
            try:
                typ = str(info.get("type", ""))
                if typ not in allowed:
                    continue
                qty = await get_item_qty(uid, emoji)
                if int(qty or 0) <= 0:
                    continue  # n’affiche que si possédé
                label = info.get("nom") or info.get("label") or typ
                disp = f"{emoji} — {label} (x{qty})"
                if cur and (cur not in emoji and cur not in str(label).lower()):
                    continue
                out.append(app_commands.Choice(name=disp[:100], value=emoji))
                if len(out) >= 20:
                    break
            except Exception:
                continue
        return out

    async def _ac_items_attack(self, inter: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        return await self._ac_items_by_type(
            inter, current,
            ("attaque", "attaque_chaine", "virus", "poison", "infection", "brulure")
        )

    async def _ac_items_heal(self, inter: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        return await self._ac_items_by_type(inter, current, ("soin", "regen"))

    async def _ac_items_any(self, inter: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        return await self._ac_items_by_type(
            inter, current,
            ("attaque", "attaque_chaine", "soin", "regen", "poison", "infection", "virus", "brulure",
             "vaccin", "bouclier", "mysterybox", "vol", "esquive+", "reduction", "immunite")
        )

    # ───────────────────────── /fight — attaque ─────────────────────────
    @app_commands.command(
        name="fight",
        description="Attaquer un joueur avec un objet d’attaque ou un statut offensif."
    )
    @app_commands.describe(cible="La cible", objet="Choisis un objet d’attaque ou un statut (virus, poison, …)")
    @app_commands.autocomplete(objet=_ac_items_attack)
    async def fight(self, inter: discord.Interaction, cible: discord.Member, objet: str):
        if inter.user.id == cible.id:
            return await inter.response.send_message("Tu ne peux pas t’attaquer toi-même.", ephemeral=True)

        info = self._obj_info(objet)
        ALLOWED = ("attaque", "attaque_chaine", "virus", "poison", "infection", "brulure")
        if not info or info.get("type") not in ALLOWED:
            return await inter.response.send_message(
                "Objet invalide : il faut un objet **d’attaque** ou un **statut offensif**.",
                ephemeral=True
            )

        if not await self._consume_item(inter.user.id, objet):
            return await inter.response.send_message(f"Tu n’as pas **{objet}** dans ton inventaire.", ephemeral=True)

        await inter.response.defer(thinking=True)

        typ = info["type"]
        if typ == "attaque":
            embed = await self._apply_attack(inter, inter.user, cible, objet, info)
        elif typ == "attaque_chaine":
            embed = await self._apply_chain_attack(inter, inter.user, cible, objet, info)
        else:
            labels = {
                "virus": "🦠 Virus (transfert sur attaque)",
                "poison": "🧪 Poison",
                "infection": "🧟 Infection",
                "brulure": "🔥 Brûlure",
            }
            embed = await self._apply_dot(inter, inter.user, cible, objet, info, eff_type=typ, label=labels.get(typ, "Effet"))

        await inter.followup.send(embed=embed)
        await self._maybe_update_leaderboard(inter.guild.id, "fight")

    # ───────────────────────── /heal — soin ─────────────────────────
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

    # ───────────────────────── /use — tout objet ─────────────────────────
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

        elif typ in ("poison", "infection"):
            if not isinstance(cible, discord.Member):
                return await inter.followup.send("Il faut une **cible**.")
            label = "🧪 Poison" if typ == "poison" else "🧟 Infection"
            embed = await self._apply_dot(inter, inter.user, cible, objet, info, eff_type=typ, label=label)

        elif typ == "virus":
            if not isinstance(cible, discord.Member):
                return await inter.followup.send("Il faut une **cible**.")
            embed = await self._apply_dot(inter, inter.user, cible, objet, info, eff_type="virus", label="🦠 Virus (transfert sur attaque)")

        elif typ == "brulure":
            if not isinstance(cible, discord.Member):
                return await inter.followup.send("Il faut une **cible**.")
            embed = await self._apply_dot(inter, inter.user, cible, objet, info, eff_type="brulure", label="🔥 Brûlure")

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
            embed = discord.Embed(
                title="📦 Box ouverte",
                description=f"{inter.user.mention} obtient **{got}** !",
                color=discord.Color.gold()
            )
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

        # Post-hook générique (ex. ne pas consommer)
        try:
            post = await trigger("on_use_item", user_id=inter.user.id, item_emoji=objet, item_type=str(typ)) or {}
        except Exception:
            post = {}
        if post.get("dont_consume"):
            try:
                await add_item(inter.user.id, objet, 1)
            except Exception:
                pass

        await inter.followup.send(embed=embed)
        await self._maybe_update_leaderboard(inter.guild.id, "use")

    # ───────────────────────── Commandes de test ─────────────────────────
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

        dmg_final, absorbed, dodged, ko_txt = await self._resolve_hit(inter, inter.user, target, base, False, None)
        hp, _ = await get_hp(target.id)
        try:
            await trigger("on_attack", attacker_id=inter.user.id, target_id=target.id, damage_done=dmg_final)
        except Exception:
            pass

        if dodged:
            desc = f"{inter.user.mention} tente un coup sur {target.mention}.{ko_txt}"
        else:
            desc = (f"{inter.user.mention} inflige **{dmg_final}** à {target.mention}.\n"
                    f"🛡 Absorbé: {absorbed} | ❤️ PV restants: **{hp}**{ko_txt}")

        embed = discord.Embed(title="GotValis : impact confirmé", description=desc, color=discord.Color.red())
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

    @app_commands.command(name="hp", description="(test) Affiche tes PV / PV de la cible.")
    @app_commands.describe(target="Cible (optionnel)")
    async def hp(self, inter: discord.Interaction, target: Optional[discord.Member] = None):
        target = target or inter.user
        hp, mx = await get_hp(target.id)
        await inter.response.send_message(f"❤️ {target.mention}: **{hp}/{mx}** PV")

async def setup(bot: commands.Bot):
    await bot.add_cog(CombatCog(bot))

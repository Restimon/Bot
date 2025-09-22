# cogs/combat_cog.py
from __future__ import annotations

import asyncio
import json
import random
from typing import Dict, Tuple, List, Optional

import discord
from discord.ext import commands
from discord import app_commands

# ── Backends combat/éco/inventaire/effets
from stats_db import deal_damage, heal_user, get_hp, is_dead, revive_full
try:
    # si ta DB expose add_shield, on l’utilise (sinon fallback via effects)
    from stats_db import add_shield  # type: ignore
except Exception:
    add_shield = None  # type: ignore

from effects_db import (
    add_or_refresh_effect,
    remove_effect,
    has_effect,
    list_effects,
    effects_loop,
    set_broadcaster,
    transfer_virus_on_attack,
    get_outgoing_damage_penalty,   # gère flat + % (avec base)
)

# monnaie / inventaire
from economy_db import add_balance, get_balance
from inventory_db import get_item_qty, remove_item, add_item

# Passifs (routeur d’événements + helpers)
from passifs import (
    trigger,
    get_extra_dodge_chance,
    get_extra_reduction_percent,
)
# `king_execute_ready` peut être absent : on fait un fallback local robuste
try:
    from passifs import king_execute_ready as _king_execute_ready_ext  # type: ignore
except Exception:
    _king_execute_ready_ext = None  # type: ignore

# Objets (emoji -> caractéristiques)
try:
    from utils import OBJETS, get_random_item  # type: ignore
except Exception:
    OBJETS = {}
    def get_random_item(debug: bool = False):
        return random.choice(["🍀", "❄️", "🧪", "🩹", "💊"])


# ─────────────────────────────────────────────────────────────
# Helpers KING (fallback si la fonction n’existe pas côté passifs)
# ─────────────────────────────────────────────────────────────
async def king_execute_ready(attacker_id: int, target_id: int) -> bool:
    """
    Si `passifs.king_execute_ready(attacker_id, target_id)` existe, on l’utilise.
    Sinon, fallback : exécute quand la cible a ≤ 10 PV (classique du Roi).
    """
    if callable(_king_execute_ready_ext):
        try:
            return bool(await _king_execute_ready_ext(attacker_id, target_id))  # type: ignore
        except Exception:
            pass
    try:
        hp, _ = await get_hp(target_id)
        return hp <= 10
    except Exception:
        return False


# ─────────────────────────────────────────────────────────────
# MAPPING des salons de ticks : user_id -> (guild_id, channel_id)
# ─────────────────────────────────────────────────────────────
_tick_channels: Dict[int, Tuple[int, int]] = {}

def remember_tick_channel(user_id: int, guild_id: int, channel_id: int) -> None:
    _tick_channels[int(user_id)] = (int(guild_id), int(channel_id))

def get_all_tick_targets() -> List[Tuple[int, int]]:
    """Liste unique (guild_id, channel_id) pour la boucle effects_loop."""
    seen: set[Tuple[int, int]] = set()
    for pair in _tick_channels.values():
        seen.add(pair)
    return list(seen)

# ─────────────────────────────────────────────────────────────
# Broadcaster des ticks (appelé par effects_db)
# payload: {"title": str, "lines": List[str], "color": int, "user_id": Optional[int]}
# ─────────────────────────────────────────────────────────────
async def _effects_broadcaster(bot: commands.Bot, guild_id: int, channel_id: int, payload: Dict):
    # Router par joueur si on a mémorisé un salon
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

    embed = discord.Embed(title=str(payload.get("title", "GotValis")), color=payload.get("color", 0x2ecc71))
    lines = payload.get("lines") or []
    if lines:
        embed.description = "\n".join(lines)
    await channel.send(embed=embed)


# ─────────────────────────────────────────────────────────────
# AUTOCOMPLÉTIONS OBJETS (filtrées par inventaire + type)
# ─────────────────────────────────────────────────────────────
async def _ac_items_generic(interaction: discord.Interaction, current: str, allowed_types: Optional[set] = None) -> List[app_commands.Choice[str]]:
    """
    Retourne jusqu’à 20 emojis d’objets que l’utilisateur POSSEDE,
    filtrés par type autorisé et par le texte saisi.
    """
    if not interaction or not interaction.user:
        return []
    cur = (current or "").strip().lower()
    uid = interaction.user.id

    def match_text(emoji: str, label: str) -> bool:
        if not cur:
            return True
        return (cur in emoji.lower()) or (cur in label.lower())

    out: List[app_commands.Choice[str]] = []
    for emoji, info in OBJETS.items():
        try:
            typ = str(info.get("type", "")).lower()
        except Exception:
            typ = ""
        if allowed_types and typ not in allowed_types:
            continue
        qty = 0
        try:
            qty = int(await get_item_qty(uid, emoji) or 0)
        except Exception:
            qty = 0
        if qty <= 0:
            continue

        # petit label lisible
        label = ""
        try:
            if typ == "attaque":
                d = int(info.get("degats", 0) or 0)
                if d: label = f"attaque {d}"
            elif typ == "attaque_chaine":
                d1 = int(info.get("degats_principal", 0) or 0)
                d2 = int(info.get("degats_secondaire", 0) or 0)
                label = f"attaque {d1}+{d2}"
            elif typ == "soin":
                s = int(info.get("soin", 0) or 0)
                label = f"soin {s}" if s else "soin"
            elif typ == "regen":
                v = int(info.get("valeur", 0) or 0)
                itv = int(info.get("intervalle", 60) or 60)
                label = f"regen +{v}/{max(1,itv)//60}m"
            elif typ in ("poison", "infection", "brulure", "virus"):
                d = int(info.get("degats", 0) or 0)
                itv = int(info.get("intervalle", 60) or 60)
                label = f"{typ} {d}/{max(1,itv)//60}m"
            elif typ == "bouclier":
                val = int(info.get("valeur", 0) or 0)
                label = f"bouclier {val}"
            else:
                label = typ or "objet"
        except Exception:
            label = "objet"

        if match_text(emoji, label):
            name = f"{emoji} • {label} (x{qty})"
            out.append(app_commands.Choice(name=name, value=emoji))
            if len(out) >= 20:
                break
    return out

# Spécifiques pour chaque commande
async def ac_items_attack(interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
    return await _ac_items_generic(interaction, current, {"attaque", "attaque_chaine"})

async def ac_items_heal(interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
    return await _ac_items_generic(interaction, current, {"soin", "regen"})

async def ac_items_any(interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
    # tout ce qui est référencé dans OBJETS
    return await _ac_items_generic(interaction, current, None)


# ─────────────────────────────────────────────────────────────
# Le COG
# ─────────────────────────────────────────────────────────────
class CombatCog(commands.Cog):
    """Système de combat : /fight /heal /use + commandes de test (poison, virus, etc.)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # branche le broadcaster des ticks
        set_broadcaster(lambda gid, cid, pld: asyncio.create_task(_effects_broadcaster(self.bot, gid, cid, pld)))
        # lance la boucle des effets (scan) si pas déjà en cours
        self._start_effects_loop_once()

    # ── Lancement unique de la boucle des effets
    def _start_effects_loop_once(self):
        if getattr(self.bot, "_effects_loop_started", False):
            return
        self.bot._effects_loop_started = True

        async def runner():
            await effects_loop(get_targets=get_all_tick_targets, interval=30)

        asyncio.create_task(runner())

    # ─────────────────────────────────────────────────────────
    # Helpers internes
    # ─────────────────────────────────────────────────────────
    async def _consume_item(self, user_id: int, emoji: str) -> bool:
        """Retire 1 item (si présent) de l'inventaire DB."""
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
        """Somme les 'value' des effets donnés."""
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
        """Esquive = passif (Nova/Elira/...) + effets 'esquive' cumulés. Cap 95%."""
        base = await get_extra_dodge_chance(user_id)
        buffs = await self._sum_effect_value(user_id, "esquive")
        return min(base + float(buffs), 0.95)

    async def _compute_reduction_pct(self, user_id: int) -> float:
        """DR% = passif (Cielya/Nathaniel/Veylor/Valen) + effets 'reduction*' cumulés. Cap 90%."""
        base = await get_extra_reduction_percent(user_id)
        buffs = await self._sum_effect_value(user_id, "reduction", "reduction_temp", "reduction_valen")
        return min(base + float(buffs), 0.90)

    # ─────────────────────────────────────────────────────────
    # Application des objets (effets et dégâts)
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
        """
        Calcule tout le pipeline: esquive, pre-defense, DR, flat, deal_damage, undying.
        Retourne (final_damage, absorbed, dodged, ko_suffix_text)
        """
        # 0) esquive
        dodge = await self._compute_dodge_chance(target.id)
        if random.random() < dodge:
            # post-défense (esquive)
            await trigger("on_defense_after",
                          defender_id=target.id, attacker_id=attacker.id,
                          final_taken=0, dodged=True)
            # Elira: le redirect & PB est géré côté passifs.trigger
            return 0, 0, True, "\n🛰️ **Esquive !**"

        # 1) pre-defense procs
        predef = await trigger("on_defense_pre",
                               defender_id=target.id,
                               attacker_id=attacker.id,
                               incoming=int(base_damage)) or {}
        cancel = bool(predef.get("cancel"))
        half   = bool(predef.get("half"))
        flat   = int(predef.get("flat_reduce", 0))
        counter_frac = float(predef.get("counter_frac", 0.0) or 0.0)

        # 2) DR %
        dr_pct = await self._compute_reduction_pct(target.id)

        # 3) appliquer annulations / moitiés / DR / flat
        if cancel:
            dmg_final = 0
        else:
            dmg_final = int(base_damage * (0.5 if half else 1.0))
            dmg_final = int(dmg_final * (1.0 - dr_pct))  # DR pré-PB
            dmg_final = max(0, dmg_final - flat)

        # 4) appliquer les dégâts
        res = await deal_damage(attacker.id, target.id, int(dmg_final))
        absorbed = int(res.get("absorbed", 0) or 0)

        # 5) contre-attaque (Maître d’Hôtel)
        if counter_frac > 0 and dmg_final > 0:
            try:
                counter = max(1, int(round(dmg_final * counter_frac)))
                await deal_damage(target.id, attacker.id, counter)
            except Exception:
                pass

        # 6) undying Zeyra
        ko_txt = ""
        if await is_dead(target.id):
            from passifs import undying_zeyra_check_and_mark as _undying  # lazy import
            try:
                if await _undying(target.id):
                    await heal_user(target.id, target.id, 1)
                    ko_txt = "\n⭐ **Volonté de Fracture** : survit à 1 PV."
                else:
                    await revive_full(target.id)
                    ko_txt = "\n💥 **Cible mise KO** (réanimée en PV/PB)."
            except Exception:
                await revive_full(target.id)
                ko_txt = "\n💥 **Cible mise KO** (réanimée)."

        # 7) post-défense
        await trigger("on_defense_after",
                      defender_id=target.id, attacker_id=attacker.id,
                      final_taken=dmg_final, dodged=False)

        return int(dmg_final), absorbed, False, ko_txt

    async def _apply_attack(self, inter: discord.Interaction, attacker: discord.Member, target: discord.Member, emoji: str, info: Dict) -> discord.Embed:
        """Attaque avec un objet de type 'attaque'."""
        base = int(info.get("degats", 0) or 0)

        # 0) execute du Roi
        if await king_execute_ready(attacker.id, target.id):
            base = max(base, 10_000_000)

        # 1) malus d’attaque (poison etc.) — % + flat
        penalty = await get_outgoing_damage_penalty(attacker.id, base=base)
        base = max(0, base - int(penalty))

        # 2) critique (x2 par défaut)
        crit_chance = float(info.get("crit", 0.0) or 0.0)
        is_crit = (random.random() < crit_chance)
        crit_mul = 2.0 if is_crit else 1.0
        base = int(base * crit_mul)

        # 3) transfert de virus (si l’attaquant le porte)
        await transfer_virus_on_attack(attacker.id, target.id)

        # 4) pipeline complet
        dmg_final, absorbed, dodged, ko_txt = await self._resolve_hit(
            inter, attacker, target, base, is_crit, None
        )

        hp, _ = await get_hp(target.id)

        # Passifs (post-attaque) — fournir attacker_id/target_id (pas user_id)
        await trigger("on_attack", attacker_id=attacker.id, target_id=target.id, damage_done=dmg_final)

        if dodged:
            desc = f"{attacker.mention} tente {emoji} sur {target.mention}.{ko_txt}"
        else:
            desc = (f"{attacker.mention} utilise {emoji} sur {target.mention}.\n"
                    f"🎯 Dégâts: **{dmg_final}** {'(**CRIT!**)' if is_crit else ''} • "
                    f"🛡 Absorbés: {absorbed} • ❤️ PV restants: **{hp}**{ko_txt}")

        e = discord.Embed(title="⚔️ Attaque", description=desc, color=discord.Color.red())
        return e

    async def _apply_chain_attack(self, inter: discord.Interaction, attacker: discord.Member, target: discord.Member, emoji: str, info: Dict) -> discord.Embed:
        """Attaque à deux composantes (on somme, plus simple/clair)."""
        d1 = int(info.get("degats_principal", 0) or 0)
        d2 = int(info.get("degats_secondaire", 0) or 0)
        base = d1 + d2

        # 0) execute du Roi
        if await king_execute_ready(attacker.id, target.id):
            base = max(base, 10_000_000)

        # 1) malus d’attaque
        penalty = await get_outgoing_damage_penalty(attacker.id, base=base)
        base = max(0, base - int(penalty))

        # 2) pas de crit spécifique (ou ajoute si l’objet a sa propre logique)
        # 3) transfert de virus
        await transfer_virus_on_attack(attacker.id, target.id)

        # 4) pipeline
        dmg_final, absorbed, dodged, ko_txt = await self._resolve_hit(
            inter, attacker, target, base, False, None
        )

        hp, _ = await get_hp(target.id)
        await trigger("on_attack", attacker_id=attacker.id, target_id=target.id, damage_done=dmg_final)

        if dodged:
            desc = f"{attacker.mention} tente {emoji} sur {target.mention}.{ko_txt}"
        else:
            desc = (f"{attacker.mention} utilise {emoji} sur {target.mention}.\n"
                    f"🎯 Dégâts totaux: **{dmg_final}** • 🛡 Absorbés: {absorbed} • "
                    f"❤️ PV restants: **{hp}**{ko_txt}")

        return discord.Embed(title="⚔️ Attaque en chaîne", description=desc, color=discord.Color.red())

    async def _apply_heal(self, inter: discord.Interaction, user: discord.Member, emoji: str, info: Dict, target: Optional[discord.Member] = None) -> discord.Embed:
        """Soin direct (+ hooks passifs)."""
        heal = int(info.get("soin", 0) or 0)
        who = target or user

        # hook pré-soin (Tessa +1, mult. Aelran, etc.)
        try:
            pre = await trigger("on_heal_pre", healer_id=user.id, target_id=who.id, amount=heal) or {}
        except Exception:
            pre = {}
        heal += int(pre.get("heal_bonus", 0))
        mult = float(pre.get("mult_target", 1.0))
        heal = max(0, int(round(heal * mult)))

        await heal_user(who.id, heal)
        hp, mx = await get_hp(who.id)

        # hooks post-soin
        await trigger("on_heal", healer_id=user.id, target_id=who.id, healed=heal)
        await trigger("on_any_heal", healer_id=user.id, target_id=who.id, healed=heal)

        e = discord.Embed(
            title="❤️ Soin",
            description=f"{user.mention} utilise {emoji} sur {who.mention}.\n➕ PV rendus: **{heal}** → ❤️ **{hp}/{mx}**",
            color=discord.Color.green()
        )
        return e

    async def _apply_regen(self, inter: discord.Interaction, user: discord.Member, emoji: str, info: Dict, target: Optional[discord.Member] = None) -> discord.Embed:
        """Régénération (HoT)."""
        who = target or user
        remember_tick_channel(who.id, inter.guild.id, inter.channel.id)
        val = int(info.get("valeur", 0) or 0)
        interval = int(info.get("intervalle", 60) or 60)
        duration = int(info.get("duree", 3600) or 3600)

        # blocage d’effets ? (immunité Valen, etc.)
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
        return e

    async def _apply_dot(self, inter: discord.Interaction, user: discord.Member, target: discord.Member, emoji: str, info: Dict, eff_type: str, label: str) -> discord.Embed:
        """Poison / Infection / Virus."""
        remember_tick_channel(target.id, inter.guild.id, inter.channel.id)
        val = int(info.get("degats", 0) or 0)
        interval = int(info.get("intervalle", 60) or 60)
        duration = int(info.get("duree", 3600) or 3600)

        # blocage d’effets ? (Valen immunités, Dr Elwin contre poison, Nathaniel 5%…)
        block = await trigger("on_effect_pre_apply", user_id=target.id, eff_type=eff_type) or {}
        if block.get("blocked"):
            return discord.Embed(
                title=label,
                description=f"{user.mention} tente {emoji} sur {target.mention}.\n⚠️ {block.get('reason','Effet bloqué.')}",
                color=discord.Color.orange()
            )

        # petit bonus Anna: +1 infection (si tu l’utilises)
        if eff_type == "infection":
            try:
                from passifs import modify_infection_application
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
        return e

    async def _apply_vaccin(self, inter: discord.Interaction, user: discord.Member, info: Dict, target: Optional[discord.Member] = None) -> discord.Embed:
        who = target or user
        # Purge d’effets “classiques”
        for t in ("poison", "infection", "virus", "brulure"):
            try:
                await remove_effect(who.id, t)
            except Exception:
                pass
        e = discord.Embed(
            title="💉 Vaccin",
            description=f"{user.mention} purge les statuts négatifs de {who.mention}.",
            color=discord.Color.blurple()
        )
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
            # fallback: effet “pb” (visuel)
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
        return e

    # ─────────────────────────────────────────────────────────
    # /fight — attaque (nécessite un objet d’attaque)
    # ─────────────────────────────────────────────────────────
    @app_commands.command(name="fight", description="Attaquer un joueur avec un objet d’attaque.")
    @app_commands.describe(cible="La cible", objet="Emoji de l'objet (ex: 🔫, 🔥, 🪓, ❄️...)")
    @app_commands.autocomplete(objet=ac_items_attack)
    async def fight(self, inter: discord.Interaction, cible: discord.Member, objet: str):
        if inter.user.id == cible.id:
            return await inter.response.send_message("Tu ne peux pas t’attaquer toi-même.", ephemeral=True)

        info = self._obj_info(objet)
        if not info or info.get("type") not in ("attaque", "attaque_chaine"):
            return await inter.response.send_message("Objet invalide : il faut un objet **d’attaque**.", ephemeral=True)

        # vérif & conso inventaire
        if not await self._consume_item(inter.user.id, objet):
            return await inter.response.send_message(f"Tu n’as pas **{objet}** dans ton inventaire.", ephemeral=True)

        await inter.response.defer(thinking=True)

        if info["type"] == "attaque":
            embed = await self._apply_attack(inter, inter.user, cible, objet, info)
        else:
            embed = await self._apply_chain_attack(inter, inter.user, cible, objet, info)

        await inter.followup.send(embed=embed)
        await self._maybe_update_leaderboard(inter.guild.id, "fight")

    # ─────────────────────────────────────────────────────────
    # /heal — soin (objet de soin direct ou régénération)
    # ─────────────────────────────────────────────────────────
    @app_commands.command(name="heal", description="Soigner un joueur avec un objet de soin.")
    @app_commands.describe(objet="Emoji de l'objet (ex: 🍀, 🩹, 💊, 💕)", cible="Cible (par défaut: toi)")
    @app_commands.autocomplete(objet=ac_items_heal)
    async def heal(self, inter: discord.Interaction, objet: str, cible: Optional[discord.Member] = None):
        info = self._obj_info(objet)
        if not info or info.get("type") not in ("soin", "regen"):
            return await inter.response.send_message("Objet invalide : il faut un objet **de soin**.", ephemeral=True)

        # vérif & conso inventaire
        if not await self._consume_item(inter.user.id, objet):
            return await inter.response.send_message(f"Tu n’as pas **{objet}** dans ton inventaire.", ephemeral=True)

        await inter.response.defer(thinking=True)

        if info["type"] == "soin":
            embed = await self._apply_heal(inter, inter.user, objet, info, cible)
        else:
            embed = await self._apply_regen(inter, inter.user, objet, info, cible)

        await inter.followup.send(embed=embed)
        await self._maybe_update_leaderboard(inter.guild.id, "heal")

    # ─────────────────────────────────────────────────────────
    # /use — utiliser un objet quelconque (attaque/dot/soin/bouclier/etc.)
    # ─────────────────────────────────────────────────────────
    @app_commands.command(name="use", description="Utiliser un objet de ton inventaire.")
    @app_commands.describe(objet="Emoji de l'objet (ex: 🧪, 🧟, 🛡, 💉, 📦, ...)", cible="Cible (selon l'objet)")
    @app_commands.autocomplete(objet=ac_items_any)
    async def use(self, inter: discord.Interaction, objet: str, cible: Optional[discord.Member] = None):
        info = self._obj_info(objet)
        if not info:
            return await inter.response.send_message("Objet inconnu.", ephemeral=True)

        # vérif & conso inventaire (remboursement possible post-use via passif/roulette)
        if not await self._consume_item(inter.user.id, objet):
            return await inter.response.send_message(f"Tu n’as pas **{objet}** dans ton inventaire.", ephemeral=True)

        await inter.response.defer(thinking=True)

        typ = info.get("type")
        embed: Optional[discord.Embed] = None

        # offensifs directs
        if typ == "attaque":
            if not isinstance(cible, discord.Member):
                return await inter.followup.send("Il faut une **cible** pour attaquer.")
            embed = await self._apply_attack(inter, inter.user, cible, objet, info)

        elif typ == "attaque_chaine":
            if not isinstance(cible, discord.Member):
                return await inter.followup.send("Il faut une **cible** pour attaquer.")
            embed = await self._apply_chain_attack(inter, inter.user, cible, objet, info)

        # DoT / statuts
        elif typ in ("poison", "infection"):
            if not isinstance(cible, discord.Member):
                return await inter.followup.send("Il faut une **cible**.")
            label = "🧪 Poison" if typ == "poison" else "🧟 Infection"
            embed = await self._apply_dot(inter, inter.user, cible, objet, info, eff_type=typ, label=label)

        elif typ == "virus":
            if not isinstance(cible, discord.Member):
                return await inter.followup.send("Il faut une **cible**.")
            embed = await self._apply_dot(inter, inter.user, cible, objet, info, eff_type="virus", label="🦠 Virus (transfert sur attaque)")

        # soins
        elif typ == "soin":
            embed = await self._apply_heal(inter, inter.user, objet, info, cible)

        elif typ == "regen":
            embed = await self._apply_regen(inter, inter.user, objet, info, cible)

        # utilitaires
        elif typ == "vaccin":
            embed = await self._apply_vaccin(inter, inter.user, info, cible)

        elif typ == "bouclier":
            embed = await self._apply_bouclier(inter, inter.user, info, cible)

        elif typ == "mysterybox":
            # ouvre une box → ajoute un item random
            got = get_random_item(debug=False)
            await add_item(inter.user.id, got, 1)
            embed = discord.Embed(
                title="📦 Box ouverte",
                description=f"{inter.user.mention} obtient **{got}** !",
                color=discord.Color.gold()
            )
            # Hook passif "box_plus_un_objet"
            res = await trigger("on_box_open", user_id=inter.user.id)
            if int(res.get("extra_items", 0)) > 0:
                extra = get_random_item(debug=False)
                await add_item(inter.user.id, extra, 1)
                embed.description += f"\n🎁 Bonus: **{extra}**"

        elif typ == "vol":
            # version simple: 25% d’avoir un item aléatoire (sans cible)
            if isinstance(cible, discord.Member):
                # anti-vol (Lyss Tenra) si cible fournie
                res = await trigger("on_theft_attempt", attacker_id=inter.user.id, target_id=cible.id)
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
            # on applique un effet “buff” générique
            who = cible or inter.user
            remember_tick_channel(who.id, inter.guild.id, inter.channel.id)
            val = int(info.get("valeur", 0) or 0)
            dur = int(info.get("duree", 3600) or 3600)

            # blocage ?
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

        # Hook post-conso (ex: Marn Velk — ne pas consommer → refund)
        try:
            post = await trigger("on_use_item", user_id=inter.user.id, item_emoji=objet, item_type=str(typ)) or {}
        except Exception:
            post = {}
        if post.get("dont_consume"):
            try:
                await add_item(inter.user.id, objet, 1)
            except Exception:
                pass  # silencieux si inventaire indispo

        await inter.followup.send(embed=embed)
        await self._maybe_update_leaderboard(inter.guild.id, "use")

    # ─────────────────────────────────────────────────────────
    # Commandes de test (gardées)
    # ─────────────────────────────────────────────────────────
    @app_commands.command(name="hit", description="(test) Inflige des dégâts directs à une cible.")
    @app_commands.describe(target="Cible", amount="Dégâts directs (appliquent esquive/DR/PB/PV)")
    async def hit(self, inter: discord.Interaction, target: discord.Member, amount: int):
        if amount <= 0:
            return await inter.response.send_message("Le montant doit être > 0.", ephemeral=True)

        await inter.response.defer(thinking=True)
        # execute du Roi sur hit?
        base = int(amount)
        if await king_execute_ready(inter.user.id, target.id):
            base = max(base, 10_000_000)

        # malus d’attaque
        base -= int(await get_outgoing_damage_penalty(inter.user.id, base=base))
        base = max(0, base)

        # transfert virus
        await transfer_virus_on_attack(inter.user.id, target.id)

        dmg_final, absorbed, dodged, ko_txt = await self._resolve_hit(
            inter, inter.user, target, base, False, None
        )

        hp, _ = await get_hp(target.id)
        await trigger("on_attack", attacker_id=inter.user.id, target_id=target.id, damage_done=dmg_final)

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
            user_id=target.id,
            eff_type="poison",
            value=cfg["value"],
            duration=cfg["duration"],
            interval=cfg["interval"],
            source_id=inter.user.id,
            meta_json=json.dumps({"applied_in": inter.channel.id})
        )
        await inter.followup.send(f"🧪 {target.mention} est **empoisonné**.")

    @app_commands.command(name="virus", description="(test) Applique un virus à une cible (transfert sur attaque).")
    @app_commands.describe(target="Cible")
    async def cmd_virus(self, inter: discord.Interaction, target: discord.Member):
        await inter.response.defer(thinking=True)
        remember_tick_channel(target.id, inter.guild.id, inter.channel.id)
        cfg = {"value": 0, "interval": 60, "duration": 600}
        await add_or_refresh_effect(
            user_id=target.id,
            eff_type="virus",
            value=cfg["value"],
            duration=cfg["duration"],
            interval=cfg["interval"],
            source_id=inter.user.id,
            meta_json=json.dumps({"applied_in": inter.channel.id})
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
            user_id=target.id,
            eff_type="infection",
            value=cfg["value"],
            duration=cfg["duration"],
            interval=cfg["interval"],
            source_id=inter.user.id,
            meta_json=json.dumps({"applied_in": inter.channel.id})
        )
        await inter.followup.send(f"🧟 {target.mention} est **infecté**.")

    @app_commands.command(name="brulure", description="(test) Applique une brûlure (DOT).")
    @app_commands.describe(target="Cible")
    async def cmd_brulure(self, inter: discord.Interaction, target: discord.Member):
        await inter.response.defer(thinking=True)
        remember_tick_channel(target.id, inter.guild.id, inter.channel.id)
        cfg = {"value": 1, "interval": 60, "duration": 300}
        await add_or_refresh_effect(
            user_id=target.id,
            eff_type="brulure",
            value=cfg["value"],
            duration=cfg["duration"],
            interval=cfg["interval"],
            source_id=inter.user.id,
            meta_json=json.dumps({"applied_in": inter.channel.id})
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
            user_id=target.id,
            eff_type="regen",
            value=cfg["value"],
            duration=cfg["duration"],
            interval=cfg["interval"],
            source_id=inter.user.id,
            meta_json=json.dumps({"applied_in": inter.channel.id})
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

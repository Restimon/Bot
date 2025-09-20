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
    effects_loop,
    set_broadcaster,
    transfer_virus_on_attack,
    get_outgoing_damage_penalty,
)

from economy_db import add_balance, get_balance
from inventory_db import get_item_qty, remove_item, add_item

# Passifs (routeur d’événements)
from passifs import trigger

# Objets (emoji -> caractéristiques)
try:
    from utils import OBJETS, get_random_item  # type: ignore
except Exception:
    OBJETS = {}
    def get_random_item(debug: bool = False):
        return random.choice(["🍀", "❄️", "🧪", "🩹", "💊"])

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

    # ─────────────────────────────────────────────────────────
    # Application des objets (effets et dégâts)
    # ─────────────────────────────────────────────────────────
    async def _apply_attack(self, inter: discord.Interaction, attacker: discord.Member, target: discord.Member, emoji: str, info: Dict) -> discord.Embed:
        """Attaque avec un objet de type 'attaque'."""
        base = int(info.get("degats", 0) or 0)

        # malus d’attaque (ex: poison)
        penalty = await get_outgoing_damage_penalty(attacker.id)
        base_after_penalty = max(0, base - penalty)

        # critique (x2 par défaut)
        crit_chance = float(info.get("crit", 0.0) or 0.0)
        is_crit = (random.random() < crit_chance)
        crit_mul = 2.0 if is_crit else 1.0

        # Hook passifs OPTIONNEL avant les dégâts (exécuté, bonus, crit mult…)
        try:
            pre = await trigger(
                "before_damage",
                attacker_id=attacker.id,
                target_id=target.id,
                base_damage=base_after_penalty,
                is_crit=is_crit,
                crit_multiplier=crit_mul,
                emoji=emoji,
                meta=info,
            ) or {}
        except Exception:
            pre = {}

        # mise à jour du multiplicateur de crit si fourni
        try:
            cm = float(pre.get("crit_multiplier", crit_mul))
            crit_mul = max(0.0, cm)
        except Exception:
            pass

        # dommage final (peut être override)
        dmg = int(base_after_penalty * crit_mul)
        if "damage" in pre:
            try:
                dmg = max(0, int(pre["damage"]))
            except Exception:
                pass

        # “execute” (ex: Le Roi) → on force un gros dégât brut
        if pre.get("execute"):
            dmg = max(dmg, 10_000_000)

        # transfert de virus éventuel (si l’attaquant le porte)
        await transfer_virus_on_attack(attacker.id, target.id)

        res = await deal_damage(attacker.id, target.id, dmg)
        absorbed = int(res.get("absorbed", 0) or 0)

        # KO → revive full (règle interne)
        ko_txt = ""
        if await is_dead(target.id):
            await revive_full(target.id)
            ko_txt = "\n💥 **Cible mise KO** (réanimée en PV/PB)."

        hp, _ = await get_hp(target.id)

        # Passifs (post-attaque)
        await trigger("on_attack", user_id=attacker.id, target_id=target.id, damage_done=dmg)

        e = discord.Embed(
            title="⚔️ Attaque",
            description=(
                f"{attacker.mention} utilise {emoji} sur {target.mention}.\n"
                f"🎯 Dégâts: **{dmg}** {'(**CRIT!**)' if is_crit else ''} • 🛡 Absorbés: {absorbed} • ❤️ PV restants: **{hp}**"
                f"{ko_txt}"
            ),
            color=discord.Color.red()
        )
        # petite note retour des passifs si besoin
        if isinstance(pre.get("note"), str) and pre["note"]:
            e.set_footer(text=str(pre["note"])[:200])
        return e

    async def _apply_chain_attack(self, inter: discord.Interaction, attacker: discord.Member, target: discord.Member, emoji: str, info: Dict) -> discord.Embed:
        """Attaque à deux composantes (principal + secondaire sur la même cible pour simplifier)."""
        d1 = int(info.get("degats_principal", 0) or 0)
        d2 = int(info.get("degats_secondaire", 0) or 0)

        penalty = await get_outgoing_damage_penalty(attacker.id)
        d1 = max(0, d1 - penalty)
        d2 = max(0, d2 - penalty)

        # Hook optionnel global pour la chaîne (tu peux affiner côté passifs)
        try:
            pre = await trigger(
                "before_damage",
                attacker_id=attacker.id,
                target_id=target.id,
                base_damage=d1 + d2,
                is_crit=False,
                crit_multiplier=1.0,
                emoji=emoji,
                meta=info,
            ) or {}
        except Exception:
            pre = {}

        tot = d1 + d2
        if "damage" in pre:
            try:
                tot = max(0, int(pre["damage"]))
            except Exception:
                pass
        if pre.get("execute"):
            tot = max(tot, 10_000_000)

        await transfer_virus_on_attack(attacker.id, target.id)
        r1 = await deal_damage(attacker.id, target.id, tot)
        absorbed = int(r1.get("absorbed", 0) or 0)

        # KO → revive full
        ko_txt = ""
        if await is_dead(target.id):
            await revive_full(target.id)
            ko_txt = "\n💥 **Cible mise KO** (réanimée en PV/PB)."

        hp, _ = await get_hp(target.id)

        # Passifs
        await trigger("on_attack", user_id=attacker.id, target_id=target.id, damage_done=tot)

        e = discord.Embed(
            title="⚔️ Attaque en chaîne",
            description=(
                f"{attacker.mention} utilise {emoji} sur {target.mention}.\n"
                f"🎯 Dégâts totaux: **{tot}** • 🛡 Absorbés: {absorbed} • "
                f"❤️ PV restants: **{hp}**{ko_txt}"
            ),
            color=discord.Color.red()
        )
        if isinstance(pre.get("note"), str) and pre["note"]:
            e.set_footer(text=str(pre["note"])[:200])
        return e

    async def _apply_heal(self, inter: discord.Interaction, user: discord.Member, emoji: str, info: Dict, target: Optional[discord.Member] = None) -> discord.Embed:
        """Soin direct."""
        heal = int(info.get("soin", 0) or 0)
        who = target or user

        # Hook optionnel avant heal (Tessa +1, multiplicateurs, caps…)
        try:
            pre = await trigger(
                "before_heal",
                user_id=user.id,
                target_id=who.id,
                base_heal=heal,
                emoji=emoji,
                meta=info,
            ) or {}
        except Exception:
            pre = {}
        if "heal" in pre:
            try:
                heal = max(0, int(pre["heal"]))
            except Exception:
                pass

        await heal_user(who.id, heal)
        hp, mx = await get_hp(who.id)

        # Passifs (ex: PB=soin 2x/j…)
        await trigger("on_heal", user_id=user.id, target_id=who.id, healed=heal)

        e = discord.Embed(
            title="❤️ Soin",
            description=f"{user.mention} utilise {emoji} sur {who.mention}.\n➕ PV rendus: **{heal}** → ❤️ **{hp}/{mx}**",
            color=discord.Color.green()
        )
        if isinstance(pre.get("note"), str) and pre["note"]:
            e.set_footer(text=str(pre["note"])[:200])
        return e

    async def _apply_regen(self, inter: discord.Interaction, user: discord.Member, emoji: str, info: Dict, target: Optional[discord.Member] = None) -> discord.Embed:
        """Régénération (HoT)."""
        who = target or user
        remember_tick_channel(who.id, inter.guild.id, inter.channel.id)
        val = int(info.get("valeur", 0) or 0)
        interval = int(info.get("intervalle", 60) or 60)
        duration = int(info.get("duree", 3600) or 3600)

        # Hook optionnel sur l’application d’effet
        try:
            mod = await trigger(
                "before_apply_effect",
                applier_id=user.id, target_id=who.id,
                effect_type="regen", value=val, interval=interval, duration=duration,
                emoji=emoji, meta=info
            ) or {}
        except Exception:
            mod = {}
        val = int(mod.get("value", val))
        interval = int(mod.get("interval", interval))
        duration = int(mod.get("duration", duration))

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

        # Hook optionnel (ex: Anna +1 sur infection)
        try:
            mod = await trigger(
                "before_apply_effect",
                applier_id=user.id, target_id=target.id,
                effect_type=eff_type, value=val, interval=interval, duration=duration,
                emoji=emoji, meta=info
            ) or {}
        except Exception:
            mod = {}
        val = int(mod.get("value", val))
        interval = int(mod.get("interval", interval))
        duration = int(mod.get("duration", duration))

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
            # fallback: effet “pb” qui devra être interprété côté moteur (sinon visuel seulement)
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
    async def use(self, inter: discord.Interaction, objet: str, cible: Optional[discord.Member] = None):
        info = self._obj_info(objet)
        if not info:
            return await inter.response.send_message("Objet inconnu.", ephemeral=True)

        # vérif & conso inventaire (remboursement possible post-use via passif)
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
            res = await trigger("on_box_open", user_id=inter.user.id, items_added=[got])
            if res.get("extra_item"):
                extra = str(res["extra_item"])
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
            # on applique un effet “buff” générique avec la durée/valeur
            who = cible or inter.user
            remember_tick_channel(who.id, inter.guild.id, inter.channel.id)
            val = int(info.get("valeur", 0) or 0)
            dur = int(info.get("duree", 3600) or 3600)

            # Hook optionnel
            try:
                mod = await trigger(
                    "before_apply_effect",
                    applier_id=inter.user.id, target_id=who.id,
                    effect_type=str(typ), value=val, interval=0, duration=dur,
                    emoji=objet, meta=info
                ) or {}
            except Exception:
                mod = {}
            val = int(mod.get("value", val))
            dur = int(mod.get("duration", dur))

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
            post = await trigger("on_use_after", user_id=inter.user.id, emoji=objet) or {}
        except Exception:
            post = {}
        if post.get("refund"):
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
    @app_commands.describe(target="Cible", amount="Dégâts directs (appliquent réduc/bouclier/PV)")
    async def hit(self, inter: discord.Interaction, target: discord.Member, amount: int):
        if amount <= 0:
            return await inter.response.send_message("Le montant doit être > 0.", ephemeral=True)

        await inter.response.defer(thinking=True)
        penalty = await get_outgoing_damage_penalty(inter.user.id)
        base_after_penalty = max(0, int(amount) - penalty)

        # Hook optionnel
        try:
            pre = await trigger(
                "before_damage",
                attacker_id=inter.user.id,
                target_id=target.id,
                base_damage=base_after_penalty,
                is_crit=False,
                crit_multiplier=1.0,
                emoji="(hit)",
                meta={"type":"test"}
            ) or {}
        except Exception:
            pre = {}

        dmg = base_after_penalty
        if "damage" in pre:
            try:
                dmg = max(0, int(pre["damage"]))
            except Exception:
                pass
        if pre.get("execute"):
            dmg = max(dmg, 10_000_000)

        await transfer_virus_on_attack(inter.user.id, target.id)
        res = await deal_damage(inter.user.id, target.id, dmg)

        if await is_dead(target.id):
            await revive_full(target.id)

        hp, _ = await get_hp(target.id)

        # passifs
        await trigger("on_attack", user_id=inter.user.id, target_id=target.id, damage_done=dmg)

        embed = discord.Embed(
            title="GotValis : impact confirmé",
            description=f"{inter.user.mention} inflige **{dmg}** à {target.mention}.\n"
                        f"🛡 Absorbé: {res.get('absorbed', 0)} | ❤️ PV restants: **{hp}**",
            color=discord.Color.red()
        )
        await inter.followup.send(embed=embed)
        await self._maybe_update_leaderboard(inter.guild.id, "hit")

    @app_commands.command(name="poison", description="(test) Applique un poison à une cible.")
    @app_commands.describe(target="Cible")
    async def cmd_poison(self, inter: discord.Interaction, target: discord.Member):
        await inter.response.defer(thinking=True)
        remember_tick_channel(target.id, inter.guild.id, inter.channel.id)
        cfg = {"value": 2, "interval": 60, "duration": 600}

        # Hook optionnel
        try:
            mod = await trigger(
                "before_apply_effect",
                applier_id=inter.user.id, target_id=target.id,
                effect_type="poison", value=cfg["value"], interval=cfg["interval"], duration=cfg["duration"],
                emoji="🧪", meta={"type":"test"}
            ) or {}
        except Exception:
            mod = {}
        v = int(mod.get("value", cfg["value"]))
        itv = int(mod.get("interval", cfg["interval"]))
        dur = int(mod.get("duration", cfg["duration"]))

        await add_or_refresh_effect(
            user_id=target.id,
            eff_type="poison",
            value=v,
            duration=dur,
            interval=itv,
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

        # Hook optionnel (Anna +1)
        try:
            mod = await trigger(
                "before_apply_effect",
                applier_id=inter.user.id, target_id=target.id,
                effect_type="infection", value=cfg["value"], interval=cfg["interval"], duration=cfg["duration"],
                emoji="🧟", meta={"type":"test"}
            ) or {}
        except Exception:
            mod = {}
        v = int(mod.get("value", cfg["value"]))
        itv = int(mod.get("interval", cfg["interval"]))
        dur = int(mod.get("duration", cfg["duration"]))

        await add_or_refresh_effect(
            user_id=target.id,
            eff_type="infection",
            value=v,
            duration=dur,
            interval=itv,
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

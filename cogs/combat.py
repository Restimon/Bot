# cogs/combat.py
from __future__ import annotations
import asyncio
import random
import time
from typing import Dict, Optional, Tuple, List, Any, Callable

import discord
from discord import app_commands, Interaction, Embed, Colour
from discord.ext import commands

# Données & inventaire
from data.items import OBJETS, GIFS
from inventory import get_item_qty, remove_item, add_item, get_all_items

# Stats & économie
from stats_db import (
    deal_damage, heal_user,
    get_profile, get_hp, get_shield, set_shield,
    is_dead, revive_full,
)

# Effets (DOT, buffs) + loop de ticks
from effects_db import (
    init_effects_db, set_broadcaster, effects_loop,
    add_or_refresh_effect, remove_effect, purge_by_types, list_effects, has_effect,
    get_outgoing_damage_penalty, transfer_virus_on_attack,
)

# ─────────────────────────────────────────────────────────────
# Hooks passifs (facultatif) — fallback no-op si passifs.py absent
# ─────────────────────────────────────────────────────────────
try:
    # signatures suggérées :
    # before_damage(attacker_id, target_id, damage, ctx) -> dict overrides ex: {"damage": int, "ignore_shield": bool, "multiplier": float}
    # after_damage(attacker_id, target_id, summary_dict) -> None
    # on_heal(healer_id, target_id, healed, ctx) -> Optional[int] (pour ajuster le heal renvoyé)
    # on_status_apply(source_id, target_id, eff_type, value, duration, ctx) -> dict overrides (value/duration) ou {} 
    # on_kill(attacker_id, target_id, ctx) -> None
    # on_death(target_id, attacker_id, ctx) -> None
    # modify_shield_cap(user_id, default_cap) -> int
    from passifs import (
        before_damage, after_damage, on_heal, on_status_apply, on_kill, on_death, modify_shield_cap
    )
except Exception:
    async def before_damage(attacker_id: int, target_id: int, damage: int, ctx: Dict[str, Any]) -> Dict[str, Any]:
        return {}
    async def after_damage(attacker_id: int, target_id: int, summary: Dict[str, Any]) -> None:
        return None
    async def on_heal(healer_id: int, target_id: int, healed: int, ctx: Dict[str, Any]) -> Optional[int]:
        return None
    async def on_status_apply(source_id: int, target_id: int, eff_type: str, value: float, duration: int, ctx: Dict[str, Any]) -> Dict[str, Any]:
        return {}
    async def on_kill(attacker_id: int, target_id: int, ctx: Dict[str, Any]) -> None:
        return None
    async def on_death(target_id: int, attacker_id: int, ctx: Dict[str, Any]) -> None:
        return None
    def modify_shield_cap(user_id: int, default_cap: int) -> int:
        return default_cap

# ─────────────────────────────────────────────────────────────
ATTACK_COOLDOWN = 5               # CD global sur /fight (en secondes)
DEFAULT_SHIELD_CAP = 20           # Cap PB par défaut (peut être modifié par passif)

# ─────────────────────────────────────────────────────────────

class Combat(commands.Cog):
    """Système de combat complet: /fight, /heal, /use + DOTs, passifs, ticks & embeds."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._last_attack_ts: Dict[int, float] = {}       # user_id -> ts (cooldown)
        self._last_combat_channel: Dict[int, int] = {}    # guild_id -> channel_id (où poster les ticks)
        self._effects_task: Optional[asyncio.Task] = None

    # ------------------------- lifecycle ------------------------------------
    async def cog_load(self):
        await init_effects_db()

        # Broadcaster pour les ticks : on transforme @<id> en mention <@id>
        async def _bcast(guild_id: int, channel_id: int, payload: Dict):
            guild = self.bot.get_guild(guild_id)
            if not guild:
                return
            ch = guild.get_channel(channel_id)
            if not isinstance(ch, discord.TextChannel):
                return

            def _mentionize(s: str) -> str:
                return self._mentionize_ids(s)

            title = payload.get("title", "")
            lines = payload.get("lines", [])
            colour = payload.get("color", 0x2ecc71)

            emb = Embed(title=_mentionize(f" {title}"), colour=colour)
            if lines:
                emb.description = "\n".join(_mentionize(line) for line in lines)
            await ch.send(embed=emb)

        set_broadcaster(_bcast)
        # 30s scan; les effets tickent à leur propre intervalle
        self._effects_task = asyncio.create_task(
            effects_loop(self._tick_targets, interval=30)
        )

    async def cog_unload(self):
        if self._effects_task:
            self._effects_task.cancel()

    def _tick_targets(self) -> List[Tuple[int, int]]:
        """Liste (guild_id, channel_id) pour poster les ticks DOT/regen."""
        return [(gid, cid) for gid, cid in self._last_combat_channel.items() if cid]

    # ------------------------- helpers --------------------------------------
    def _can_attack(self, user_id: int) -> Tuple[bool, int]:
        now = time.time()
        last = self._last_attack_ts.get(user_id, 0.0)
        remain = ATTACK_COOLDOWN - int(now - last)
        return (remain <= 0, max(0, remain))

    def _record_attack(self, user_id: int):
        self._last_attack_ts[user_id] = time.time()

    def _gif_for(self, emoji: str) -> Optional[str]:
        return GIFS.get(emoji)

    def _mentionize_ids(self, text: str) -> str:
        # remplace @123456789 -> <@123456789>
        out = []
        i = 0
        while i < len(text):
            ch = text[i]
            if ch == "@" and i + 1 < len(text) and text[i + 1].isdigit():
                j = i + 1
                while j < len(text) and text[j].isdigit():
                    j += 1
                uid = text[i + 1 : j]
                out.append(f"<@{uid}>")
                i = j
                continue
            out.append(ch)
            i += 1
        return "".join(out)

    async def _has_immunite(self, user_id: int) -> bool:
        return await has_effect(user_id, "immunite")

    async def _get_reduction(self, user_id: int) -> float:
        # renvoie 0..1 (ex: 0.5 pour -50%)
        for et, val, *_ in await list_effects(user_id):
            if et == "reduction":
                try:
                    return float(val)
                except Exception:
                    return 0.0
        return 0.0

    async def _roll_esquive(self, user_id: int) -> bool:
        # chance d'esquiver les attaques (pas les ticks DOT, ni les buffs/heals)
        for et, val, *_ in await list_effects(user_id):
            if et == "esquive":
                try:
                    chance = float(val)
                except Exception:
                    chance = 0.0
                return random.random() < max(0.0, min(1.0, chance))
        return False

    def _fmt_gain_loss_pv(self, before: int, delta: int, after: int, *, sign: str = "−") -> str:
        return f"❤️ {before} PV {sign} ({abs(delta)} PV) = ❤️ {after} PV"

    async def _shield_cap_for(self, user_id: int) -> int:
        # Cap PB dynamique via passif (ex: 25)
        return int(max(1, modify_shield_cap(user_id, DEFAULT_SHIELD_CAP)))

    # ------------------------- /fight ---------------------------------------
    @app_commands.command(name="fight", description="Attaquer une cible avec un objet d’attaque (dégâts ou DOT).")
    @app_commands.describe(cible="La cible", objet="Émoji de l’objet d’attaque (ex: ⚡, 🔥, 🧪, 🦠, 🧟, ☠️)")
    async def fight(self, itx: Interaction, cible: discord.User, objet: str):
        await itx.response.defer()

        if not itx.guild:
            return await itx.followup.send("❌ Cette commande ne peut être utilisée qu’en serveur.", ephemeral=True)
        if cible.bot:
            return await itx.followup.send("🤖 Pas sur les bots.", ephemeral=True)

        # Mémorise le salon pour les ticks
        self._last_combat_channel[itx.guild.id] = itx.channel_id

        # Vérifs objet
        data = OBJETS.get(objet)
        if not data:
            return await itx.followup.send("❌ Objet inconnu.", ephemeral=True)
        if data.get("type") not in ("attaque", "attaque_chaine", "poison", "virus", "infection"):
            return await itx.followup.send("❌ Cet objet n’est pas une attaque.", ephemeral=True)

        # Cooldown
        ok, remain = self._can_attack(itx.user.id)
        if not ok:
            return await itx.followup.send(f"⏳ Cooldown: **{remain}s**.", ephemeral=True)

        # Stock
        if await get_item_qty(itx.user.id, objet) <= 0:
            return await itx.followup.send("❌ Tu n’en as pas.", ephemeral=True)

        # Esquive (sur l'APPLICATION ; pas les ticks)
        if await self._roll_esquive(cible.id):
            # consomme quand même l’objet
            await remove_item(itx.user.id, objet, 1)
            self._record_attack(itx.user.id)
            emb = Embed(title="🌀 Action de GotValis", colour=Colour.blue())
            emb.description = f"{cible.mention} **esquive habilement** l’attaque de {itx.user.mention} !"
            dodge_gif = self._gif_for("👟")
            if dodge_gif:
                emb.set_image(url=dodge_gif)
            return await itx.followup.send(embed=emb)

        immu = await self._has_immunite(cible.id)  # bloque tous dégâts directs (et DOT ticks, mais n’empêche pas l’application)

        title_emoji = objet
        lines: List[str] = []
        killed = False

        ctx_base = {"guild_id": itx.guild.id, "channel_id": itx.channel_id, "emoji": objet, "type": data["type"]}

        # -------------------- attaques directes ------------------------------
        if data["type"] in ("attaque", "attaque_chaine"):
            # Base dégâts (coup principal)
            deg = int(data.get("degats", 0))
            # Hook passif avant : peut modifier damage, etc.
            pre = await before_damage(itx.user.id, cible.id, deg, ctx_base)
            if "damage" in pre:
                deg = int(max(0, pre["damage"]))
            mult = float(pre.get("multiplier", 1.0) or 1.0)
            if mult != 1.0:
                deg = max(0, int(round(deg * mult)))

            # Crit direct (x2) — sur le coup principal
            if data.get("crit") and random.random() < float(data["crit"]):
                deg *= 2
                lines.append("🎯 **Coup critique !**")

            # 🧪 Pénalité poison sur l'ATTAQUANT : −1 dégât (min 0)
            poison_penalty = await get_outgoing_damage_penalty(itx.user.id)
            if poison_penalty > 0:
                before = deg
                deg = max(0, deg - poison_penalty)
                if before != deg:
                    lines.append("🧪 **Poison** : −1 dégât appliqué à l’attaque.")

            # Réduction % côté CIBLE (multiplicatif), puis PB, puis PV
            reduc = await self._get_reduction(cible.id)
            if reduc > 0:
                deg = max(0, int(round(deg * (1 - reduc))))

            # Immunité : annule les dégâts directs
            if immu:
                deg = 0

            # Applique
            hp_before, _ = await get_hp(cible.id)
            res = await deal_damage(itx.user.id, cible.id, deg)
            killed = killed or res["killed"]
            hp_after, _ = await get_hp(cible.id)
            # Récap
            lines.append(self._fmt_gain_loss_pv(hp_before, deg, hp_after, sign="−"))
            if res["absorbed"] > 0:
                lines.append(f"🛡 **{res['absorbed']} PB** absorbés.")

            # Hook passif après
            await after_damage(itx.user.id, cible.id, {
                "emoji": objet,
                "type": data["type"],
                "damage": deg,
                "absorbed": res["absorbed"],
                "target_hp": hp_after,
                "target_shield": res["target_shield"],
                "killed": killed
            })

            # Attaque en chaîne : dégâts secondaires (pas de crit additionnel)
            if data["type"] == "attaque_chaine" and not immu:
                sec = int(data.get("degats_secondaire", 0))
                # Réduction s’applique aussi
                if reduc > 0:
                    sec = max(0, int(round(sec * (1 - reduc))))
                if sec > 0:
                    hp_before2, _ = await get_hp(cible.id)
                    res2 = await deal_damage(itx.user.id, cible.id, sec)
                    killed = killed or res2["killed"]
                    hp_after2, _ = await get_hp(cible.id)
                    lines.append(f"☠️ **Dégâts en chaîne** : {sec} PV.")
                    lines.append(self._fmt_gain_loss_pv(hp_before2, sec, hp_after2, sign="−"))
                    if res2["absorbed"] > 0:
                        lines.append(f"🛡 +{res2['absorbed']} PB absorbés.")
                    await after_damage(itx.user.id, cible.id, {
                        "emoji": objet,
                        "type": "attaque_chaine_sec",
                        "damage": sec,
                        "absorbed": res2["absorbed"],
                        "target_hp": hp_after2,
                        "target_shield": res2["target_shield"],
                        "killed": res2["killed"]
                    })

            # Contagion si l'ATTAQUANT est infecté (25 %)
            await self._maybe_spread_infection(itx, itx.user.id, cible.id)

        # -------------------- DOTs (poison/virus/infection) ------------------
        else:
            dur = int(data.get("duree", 0))
            intervalle = int(data.get("intervalle", 1800))
            dmg = int(data.get("degats", 0))

            # Hook passif sur application de statut (peut modifier value/duration)
            overrides = await on_status_apply(itx.user.id, cible.id, data["type"], dmg, dur, ctx_base)
            if "value" in overrides:
                dmg = int(max(0, overrides["value"]))
            if "duration" in overrides:
                dur = int(max(0, overrides["duration"]))

            await add_or_refresh_effect(
                cible.id, data["type"], dmg, dur, interval=intervalle, source_id=itx.user.id
            )
            lines.append(f"{cible.mention} est affecté par **{data['type']}**.")

            # Si l'attaquant est infecté, tente la contagion (25 %)
            await self._maybe_spread_infection(itx, itx.user.id, cible.id)

        # Consomme l’objet et enregistre le CD
        await remove_item(itx.user.id, objet, 1)
        self._record_attack(itx.user.id)

        # Transfert du **virus** à l'attaque (2×5 dégâts + timer conservé)
        transferred = await transfer_virus_on_attack(itx.user.id, cible.id)
        if transferred:
            lines.append("🦠 **Le virus se propage** : 5 PV à l’ancien porteur et 5 PV à la cible. Le timer continue.")

        # KO ? (quelle que soit la source, direct ou via coups successifs)
        if await is_dead(cible.id):
            await revive_full(cible.id)       # 100 PV
            await purge_by_types(cible.id, ["poison", "virus", "infection", "regen", "reduction", "esquive", "immunite"])
            lines.append("☠️ **KO !** La cible est **réanimée à 100 PV** et **clean de tous les statuts**.")
            # Hooks kill/death
            await on_kill(itx.user.id, cible.id, ctx_base)
            await on_death(cible.id, itx.user.id, ctx_base)

        # Embed final
        verb = {
            "attaque": "inflige",
            "attaque_chaine": "inflige",
            "poison": "empoisonne",
            "virus": "contamine",
            "infection": "infecte",
        }[data["type"]]
        emb = Embed(
            title=f"{title_emoji} Action de GotValis",
            colour=Colour.orange() if data["type"] in ("attaque", "attaque_chaine") else Colour.blurple(),
        )
        emb.description = f"{itx.user.mention} **{verb}** {cible.mention} avec {objet}.\n" + "\n".join(lines)
        gif = self._gif_for(objet)
        if gif:
            emb.set_image(url=gif)

        await itx.followup.send(embed=emb)

    # ------------------------- /heal (soins) --------------------------------
    @app_commands.command(name="heal", description="Soigner (PV instantané) ou lancer une régénération.")
    @app_commands.describe(objet="Émoji de soin (🍀, 🩸, 🩹, 💊, 💕)", cible="La cible (par défaut: toi)")
    async def heal(self, itx: Interaction, objet: str, cible: Optional[discord.User] = None):
        await itx.response.defer()

        if not itx.guild:
            return await itx.followup.send("❌ En serveur uniquement.", ephemeral=True)

        target = cible or itx.user
        self._last_combat_channel[itx.guild.id] = itx.channel_id

        data = OBJETS.get(objet)
        if not data:
            return await itx.followup.send("❌ Objet inconnu.", ephemeral=True)

        t = data.get("type")
        if t not in ("soin", "regen"):
            return await itx.followup.send("❌ Cet objet n’est pas un **soin**.", ephemeral=True)

        if await get_item_qty(itx.user.id, objet) <= 0:
            return await itx.followup.send("❌ Tu n’en as pas.", ephemeral=True)

        lines: List[str] = []
        ctx_base = {"guild_id": itx.guild.id, "channel_id": itx.channel_id, "emoji": objet, "type": t}

        if t == "soin":
            amount = int(data.get("soin", 0))
            healed = await heal_user(itx.user.id, target.id, amount)
            # Hook passif heal
            adj = await on_heal(itx.user.id, target.id, healed, ctx_base)
            if isinstance(adj, int):
                healed = max(0, adj)
            lines.append(f"{target.mention} récupère **{healed} PV**.")

        elif t == "regen":
            await add_or_refresh_effect(
                target.id, "regen", float(data["valeur"]), int(data["duree"]), interval=int(data["intervalle"]), source_id=itx.user.id
            )
            lines.append(f"{target.mention} gagne une **régénération** sur la durée.")

        await remove_item(itx.user.id, objet, 1)

        emb = Embed(title="💖 Soin de GotValis", colour=Colour.green())
        emb.description = "\n".join(lines)
        gif = self._gif_for(objet)
        if gif:
            emb.set_image(url=gif)
        await itx.followup.send(embed=emb)

    # ------------------------- /use (utilitaires) ----------------------------
    @app_commands.command(name="use", description="Utiliser un objet de soutien/utilitaire.")
    @app_commands.describe(objet="🛡 🪖 👟 ⭐️ 💉 🔍 📦", cible="Cible si nécessaire (ex: 💉, 🛡, 🪖, 👟, ⭐️ peuvent être sur autrui)")
    async def use(self, itx: Interaction, objet: str, cible: Optional[discord.User] = None):
        await itx.response.defer()

        if not itx.guild:
            return await itx.followup.send("❌ En serveur uniquement.", ephemeral=True)

        target = cible or itx.user
        self._last_combat_channel[itx.guild.id] = itx.channel_id

        data = OBJETS.get(objet)
        if not data:
            return await itx.followup.send("❌ Objet inconnu.", ephemeral=True)

        t = data.get("type")
        if t not in ("bouclier", "reduction", "esquive+", "immunite", "vaccin", "vol", "mysterybox"):
            return await itx.followup.send("❌ Cet objet n’est pas un **utilitaire**.", ephemeral=True)

        if await get_item_qty(itx.user.id, objet) <= 0:
            return await itx.followup.send("❌ Tu n’en as pas.", ephemeral=True)

        lines: List[str] = []
        ctx_base = {"guild_id": itx.guild.id, "channel_id": itx.channel_id, "emoji": objet, "type": t}

        if t == "bouclier":
            cur = await get_shield(target.id)
            add = int(data.get("valeur", 0))
            cap = await self._shield_cap_for(target.id)
            new_val = min(cap, cur + add)
            await set_shield(target.id, new_val)
            lines.append(f"{target.mention} gagne un **bouclier** → 🛡 **{new_val} PB**.")

        elif t == "reduction":
            await add_or_refresh_effect(target.id, "reduction", float(data["valeur"]), int(data["duree"]))
            lines.append(f"{target.mention} bénéficie d’une **réduction de dégâts**.")

        elif t == "esquive+":
            await add_or_refresh_effect(target.id, "esquive", float(data["valeur"]), int(data["duree"]))
            lines.append(f"{target.mention} bénéficie d’une **chance d’esquive**.")

        elif t == "immunite":
            await add_or_refresh_effect(target.id, "immunite", 1.0, int(data["duree"]))
            lines.append(f"{target.mention} est **immunisé** aux dégâts (directs & DOT).")

        elif t == "vaccin":
            await purge_by_types(target.id, ["poison", "virus", "infection"])
            lines.append(f"{target.mention} est **vacciné** : poison, virus et infection retirés.")

        elif t == "vol":
            ok, txt = await self._vol_simple(itx, itx.user.id, target.id)
            lines.append(txt)

        elif t == "mysterybox":
            # 15% ticket, sinon 1 objet pondéré (rarete inverse)
            if random.random() < 0.15:
                await add_item(itx.user.id, "🎟️", 1)
                lines.append(f"{itx.user.mention} obtient **1 ticket** 🎟️ !")
            else:
                em = self._pick_weighted_item()
                await add_item(itx.user.id, em, 1)
                lines.append(f"{itx.user.mention} obtient {em} × **1**.")

        await remove_item(itx.user.id, objet, 1)

        emb = Embed(title="🛠️ Utilitaire de GotValis", colour=Colour.dark_teal())
        emb.description = "\n".join(lines)
        gif = self._gif_for(objet)
        if gif:
            emb.set_image(url=gif)
        await itx.followup.send(embed=emb)

    # ------------------------- utils internes --------------------------------
    async def _vol_simple(self, itx: Interaction, thief_id: int, target_id: int) -> Tuple[bool, str]:
        """Vole 1 item aléatoire à la cible (sauf tickets 🎟️)."""
        items = await get_all_items(target_id)
        pool = [(k, q) for k, q in items if q > 0 and k != "🎟️"]
        if not pool:
            return False, f"{itx.user.mention} tente de voler… mais **rien** à prendre."

        item, _ = random.choice(pool)
        ok = await remove_item(target_id, item, 1)
        if not ok:
            return False, f"Le vol a échoué."
        await add_item(thief_id, item, 1)
        return True, f"{itx.user.mention} **vole** {item} à <@{target_id}> !"

    def _pick_weighted_item(self) -> str:
        # Pondération inverse par 'rarete' (plus rare = moins probable)
        emojis, weights = [], []
        for e, d in OBJETS.items():
            if e == "🎟️":  # pas dans la mystery pondérée
                continue
            r = int(d.get("rarete", 1)) or 1
            emojis.append(e)
            weights.append(1.0 / r)
        return random.choices(emojis, weights=weights, k=1)[0]

    async def _maybe_spread_infection(self, itx: Interaction, attacker_id: int, target_id: int):
        """
        Si l'ATTAQUANT est infecté → 25% de chance de transmettre l'infection à la cible.
        - Si la cible n'était pas infectée: applique infection (durée standard) + inflige **+5 dégâts directs** (attribués à l’attaquant).
        - Si la cible était déjà infectée: pas de bonus, pas de refresh.
        """
        if not await has_effect(attacker_id, "infection"):
            return
        if random.random() >= 0.25:
            return
        if await has_effect(target_id, "infection"):
            return  # rien à faire

        # Par défaut : 3h / tick 30 min à 2 dégâts (adapte si différent dans tes OBJETS)
        await add_or_refresh_effect(target_id, "infection", 2, 3 * 3600, interval=1800, source_id=attacker_id)
        await deal_damage(attacker_id, target_id, 5)  # +5 directs

# ---------------------------------------------------------------------------

async def setup(bot: commands.Bot):
    await bot.add_cog(Combat(bot))

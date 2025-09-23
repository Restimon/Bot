# cogs/heal_cog.py
from __future__ import annotations

import json
from typing import Dict, List, Optional, Tuple

import discord
from discord.ext import commands
from discord import app_commands

# DB combat / stats
from stats_db import heal_user, get_hp

# Effets périodiques (regen/HoT)
try:
    from effects_db import add_or_refresh_effect, trigger as effects_trigger  # type: ignore
except Exception:
    async def add_or_refresh_effect(*args, **kwargs):  # type: ignore
        return True
    async def effects_trigger(*args, **kwargs):  # type: ignore
        return {}

# Inventaire
from inventory_db import get_item_qty, remove_item, get_all_items

# Catalogue d’objets (emoji -> fiche)
try:
    from utils import OBJETS  # type: ignore
except Exception:
    OBJETS: Dict[str, Dict] = {}

# Leaderboard live (optionnel)
def _schedule_lb(bot: commands.Bot, gid: Optional[int], reason: str):
    if not gid:
        return
    try:
        from cogs.leaderboard_live import schedule_lb_update  # type: ignore
        schedule_lb_update(bot, gid, reason)
    except Exception:
        pass


class HealCog(commands.Cog):
    """Gestion des soins: /heal (objets de type 'soin' et 'regen')."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ─────────────────────────────────────────────────────────
    # Helpers inventaire / catalogue
    # ─────────────────────────────────────────────────────────
    def _obj_info(self, emoji: str) -> Optional[Dict]:
        info = OBJETS.get(emoji)
        return dict(info) if isinstance(info, dict) else None

    async def _list_owned_items(self, uid: int) -> List[Tuple[str, int]]:
        """
        Retourne [(emoji, qty)] possédés, fusionnés/triés (utilisé par l’autocomplete).
        """
        owned: List[Tuple[str, int]] = []
        # 1) essai via listing complet
        try:
            rows = await get_all_items(uid)
            for emoji, qty in rows:
                try:
                    q = int(qty)
                except Exception:
                    q = 0
                if q > 0:
                    owned.append((str(emoji), q))
        except Exception:
            pass

        # 2) fallback: interroge seulement les items du catalogue
        if not owned and OBJETS:
            for emoji in OBJETS.keys():
                try:
                    q = int(await get_item_qty(uid, emoji) or 0)
                except Exception:
                    q = 0
                if q > 0:
                    owned.append((emoji, q))

        # fusion & tri
        merged: Dict[str, int] = {}
        for e, q in owned:
            merged[e] = merged.get(e, 0) + int(q)
        return sorted(merged.items(), key=lambda t: t[0])

    async def _ac_items_heal(self, inter: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        """
        Autocomplete: ne propose QUE les objets possédés dont type ∈ {'soin','regen'}.
        """
        uid = inter.user.id
        cur = (current or "").strip().lower()
        owned = await self._list_owned_items(uid)

        out: List[app_commands.Choice[str]] = []
        for emoji, qty in owned:
            info = OBJETS.get(emoji) or {}
            typ = str(info.get("type", "") or "")
            if typ not in ("soin", "regen"):
                continue

            # label lisible
            try:
                if typ == "soin":
                    s = int(info.get("soin", info.get("value", info.get("valeur", 0))) or 0)
                    label = f"soin {s}" if s else "soin"
                else:
                    v = int(info.get("valeur", info.get("value", 0)) or 0)
                    itv = int(info.get("intervalle", info.get("interval", 60)) or 60)
                    label = f"regen +{v}/{max(1, itv)//60}m" if v else "regen"
            except Exception:
                label = typ

            name = f"{emoji} — {label} (x{qty})"
            if cur and (cur not in emoji and cur not in label.lower()):
                continue
            out.append(app_commands.Choice(name=name[:100], value=emoji))
            if len(out) >= 20:
                break
        return out

    async def _consume_item(self, user_id: int, emoji: str) -> bool:
        try:
            qty = await get_item_qty(user_id, emoji)
            if int(qty or 0) <= 0:
                return False
            ok = await remove_item(user_id, emoji, 1)
            return bool(ok)
        except Exception:
            return False

    # ─────────────────────────────────────────────────────────
    # Logiques d’application
    # ─────────────────────────────────────────────────────────
    async def _apply_soin(
        self,
        inter: discord.Interaction,
        user: discord.Member,
        cible: Optional[discord.Member],
        emoji: str,
        info: Dict
    ) -> discord.Embed:
        target = cible or user
        # tolère diverses clés: soin/value/valeur
        val = int(info.get("soin", info.get("value", info.get("valeur", 0))) or 0)
        if val <= 0:
            return discord.Embed(
                title="❗ Objet de soin invalide",
                description=f"{emoji} n’a pas de valeur de soin.",
                color=discord.Color.red()
            )
        healed = await heal_user(user.id, target.id, val)
        hp, mx = await get_hp(target.id)
        desc = (
            f"{user.mention} utilise **{emoji}** sur {target.mention}.\n"
            f"💕 Soins effectifs: **+{healed} PV**\n"
            f"❤️ PV: **{hp}/{mx}**"
        )
        e = discord.Embed(title="Soin", description=desc, color=discord.Color.green())
        return e

    async def _apply_regen(
        self,
        inter: discord.Interaction,
        user: discord.Member,
        cible: Optional[discord.Member],
        emoji: str,
        info: Dict
    ) -> discord.Embed:
        target = cible or user
        # valeurs par défaut raisonnables
        val = int(info.get("valeur", info.get("value", 0)) or 0)
        dur = int(info.get("duree", info.get("duration", 300)) or 300)          # 5 min
        itv = int(info.get("intervalle", info.get("interval", 60)) or 60)       # 1 min

        if val <= 0 or itv <= 0 or dur <= 0:
            return discord.Embed(
                title="❗ Objet regen invalide",
                description=f"{emoji} doit avoir valeur/durée/intervalle > 0.",
                color=discord.Color.red()
            )

        # Hook passifs avant application (bloqueurs potentiels)
        try:
            res = await effects_trigger("on_effect_pre_apply", user_id=target.id, eff_type="regen") or {}
            if res.get("blocked"):
                return discord.Embed(
                    title="⚠️ Effet bloqué",
                    description=str(res.get("reason", "Application refusée.")),
                    color=discord.Color.orange()
                )
        except Exception:
            pass

        # Application de l’effet "regen"
        await add_or_refresh_effect(
            user_id=target.id,
            eff_type="regen",
            value=float(val),
            duration=int(dur),
            interval=int(itv),
            source_id=user.id,
            meta_json=json.dumps({"applied_in": inter.channel.id})
        )

        hp, mx = await get_hp(target.id)
        lignes = [
            f"{user.mention} applique **{emoji}** (Régénération) sur {target.mention}.",
            f"• Tick: **+{val} PV** toutes les **{itv}s**, durée **{dur}s**",
            f"• État actuel: ❤️ **{hp}/{mx}** PV"
        ]
        e = discord.Embed(title="Régénération appliquée", description="\n".join(lignes), color=discord.Color.blurple())
        return e

    # ─────────────────────────────────────────────────────────
    # /heal — seul point d’entrée public du cog
    # ─────────────────────────────────────────────────────────
    @app_commands.command(name="heal", description="Soigner un joueur avec un objet de soin ou de régénération.")
    @app_commands.describe(objet="Choisis un objet de type soin/regen", cible="Cible (par défaut: toi)")
    @app_commands.autocomplete(objet=_ac_items_heal)
    async def heal(self, inter: discord.Interaction, objet: str, cible: Optional[discord.Member] = None):
        if not inter.guild:
            return await inter.response.send_message("❌ À utiliser dans un serveur.", ephemeral=True)

        info = self._obj_info(objet)
        if not info or str(info.get("type", "")) not in ("soin", "regen"):
            return await inter.response.send_message("Objet invalide : il faut un **objet de soin**.", ephemeral=True)

        # Vérifie et consomme l’objet
        if not await self._consume_item(inter.user.id, objet):
            return await inter.response.send_message(f"Tu n’as pas **{objet}** dans ton inventaire.", ephemeral=True)

        await inter.response.defer(thinking=True)

        # Applique
        try:
            typ = str(info.get("type"))
            if typ == "soin":
                embed = await self._apply_soin(inter, inter.user, cible, objet, info)
            else:
                embed = await self._apply_regen(inter, inter.user, cible, objet, info)
        except Exception as e:
            embed = discord.Embed(
                title="❗ Erreur pendant le soin",
                description=f"Une erreur est survenue: `{type(e).__name__}`. L’action a été annulée.",
                color=discord.Color.red()
            )

        # Post & MAJ leaderboard
        await inter.followup.send(embed=embed)
        _schedule_lb(self.bot, inter.guild.id if inter.guild else None, "heal")


async def setup(bot: commands.Bot):
    await bot.add_cog(HealCog(bot))

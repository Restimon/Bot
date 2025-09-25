# cogs/heal_cog.py
from __future__ import annotations

import json
import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional, List, Tuple, Dict

# DBs
from inventory_db import get_item_qty, remove_item, add_item, get_all_items
from stats_db import heal_user
try:
    from shields_db import add_shield as _add_shield, get_shield as _get_shield, get_max_shield as _get_max_shield
except Exception:
    _add_shield = _get_shield = _get_max_shield = None  # fallbacks gérés plus bas

# Effets (pour HoT si nécessaire)
try:
    from effects_db import add_or_refresh_effect
except Exception:
    async def add_or_refresh_effect(*args, **kwargs):  # type: ignore
        return True

# On réutilise la mémorisation de salon de combat_cog pour router les ticks
try:
    from cogs.combat_cog import remember_tick_channel  # type: ignore
except Exception:
    def remember_tick_channel(user_id: int, guild_id: int, channel_id: int) -> None:
        """Fallback no-op si combat_cog n'est pas chargé."""
        return

# Catalogue d’objets
try:
    from utils import OBJETS
except Exception:
    OBJETS: Dict[str, Dict] = {}


# ─────────────────────────────────────────────────────────────
# Helpers d’affichage
# ─────────────────────────────────────────────────────────────
def _fmt_secs(secs: int) -> str:
    """Transforme 10800 -> '3 h', 5400 -> '1 h 30 min', 90 -> '1 min'."""
    try:
        s = int(secs)
    except Exception:
        return f"{secs}s"
    s = max(0, s)
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h} h {m} min" if m else f"{h} h"
    if m:
        return f"{m} min"
    return f"{s} s"


def _info(emoji: str) -> Optional[Dict]:
    meta = OBJETS.get(emoji)
    return dict(meta) if isinstance(meta, dict) else None


async def _list_owned_items(uid: int) -> List[Tuple[str, int]]:
    """Inventaire réel (robuste) pour l’autocomplétion."""
    out: List[Tuple[str, int]] = []
    try:
        rows = await get_all_items(uid)
        if isinstance(rows, list):
            for r in rows:
                if isinstance(r, (list, tuple)) and len(r) >= 2:
                    e, q = str(r[0]), int(r[1])
                    if e and q > 0:
                        out.append((e, q))
                elif isinstance(r, dict):
                    e = str(r.get("emoji") or r.get("item") or r.get("id") or r.get("key") or "")
                    q = int(r.get("qty") or r.get("quantity") or r.get("count") or r.get("n") or 0)
                    if e and q > 0: out.append((e, q))
        elif isinstance(rows, dict):
            for e, q in rows.items():
                try:
                    if int(q) > 0:
                        out.append((str(e), int(q)))
                except Exception:
                    continue
    except Exception:
        pass
    # fallback: on check tout le catalogue
    if not out:
        for e in OBJETS.keys():
            try:
                q = int(await get_item_qty(uid, e) or 0)
                if q > 0:
                    out.append((e, q))
            except Exception:
                continue
    # merge/tri
    merged: Dict[str, int] = {}
    for e, q in out:
        merged[e] = merged.get(e, 0) + int(q)
    return sorted(merged.items(), key=lambda t: t[0])


class HealCog(commands.Cog):
    """Gestion /heal : soin, régénération, bouclier."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ──────────── Autocomplétion : soin/regen/bouclier qu’on possède ───────────
    async def _ac_items_heal_like(self, inter: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        cur = (current or "").strip().lower()
        owned = await _list_owned_items(inter.user.id)
        out: List[app_commands.Choice[str]] = []
        for emoji, qty in owned:
            meta = OBJETS.get(emoji) or {}
            typ = str(meta.get("type", ""))
            if typ not in ("soin", "regen", "bouclier"):
                continue
            label = meta.get("nom") or meta.get("label") or typ
            display = f"{emoji} — {label} (x{qty})"
            if cur and (cur not in emoji and cur not in str(label).lower()):
                continue
            out.append(app_commands.Choice(name=display[:100], value=emoji))
            if len(out) >= 20:
                break
        return out

    # ──────────── Helpers ────────────
    async def _consume(self, uid: int, emoji: str) -> bool:
        try:
            q = int(await get_item_qty(uid, emoji) or 0)
            if q <= 0: return False
            ok = await remove_item(uid, emoji, 1)
            return bool(ok)
        except Exception:
            return False

    async def _roll_val(self, info: dict, default: int) -> int:
        if not isinstance(info, dict):
            return int(default)
        if "min" in info and "max" in info:
            try:
                a = int(info.get("min", 0)); b = int(info.get("max", 0))
                if a > b: a, b = b, a
                import random
                return random.randint(a, b)
            except Exception:
                pass
        for k in ("valeur","value","amount","heal","soin","degats","dmg"):
            if k in info:
                try: return int(info[k])
                except Exception: continue
        return int(default)

    def _read_interval(self, info: dict, fallback_secs: int = 60) -> int:
        # supporte 'intervalle' (utils.py) et 'interval' (autres configs)
        return int(info.get("intervalle", info.get("interval", fallback_secs)) or fallback_secs)

    def _read_duration(self, info: dict, fallback_secs: int = 300) -> int:
        return int(info.get("duree", info.get("duration", fallback_secs)) or fallback_secs)

    # ──────────── Actions ────────────
    async def _do_heal(self, inter: discord.Interaction, user: discord.Member, emoji: str, info: dict, cible: Optional[discord.Member]) -> discord.Embed:
        target = cible or user
        amount = await self._roll_val(info, 10)
        healed = await heal_user(user.id, target.id, amount)
        gif = info.get("gif_heal") or info.get("gif") or info.get("gif_attack")
        e = discord.Embed(title="💊 Soin", color=discord.Color.green())
        if healed <= 0:
            e.description = f"{user.mention} tente de soigner {target.mention} avec {emoji}, mais les PV sont déjà au max."
        else:
            from stats_db import get_hp  # re-lecture pour affichage
            hp_after, mx = await get_hp(target.id)
            e.description = f"{user.mention} rend **{healed} PV** à {target.mention} avec {emoji}.\n❤️ **{hp_after-healed}/{mx}** + (**{healed}**) = ❤️ **{hp_after}/{mx}**"
        if gif and isinstance(gif, str):
            e.set_image(url=gif)
        return e

    async def _do_regen(self, inter: discord.Interaction, user: discord.Member, emoji: str, info: dict, cible: Optional[discord.Member]) -> discord.Embed:
        target = cible or user
        val = await self._roll_val(info, 2)
        interval = self._read_interval(info, 60)
        duration = self._read_duration(info, 300)

        # ➜ mémorise le salon pour les ticks
        remember_tick_channel(target.id, inter.guild.id, inter.channel.id)

        await add_or_refresh_effect(
            user_id=target.id, eff_type="regen", value=float(val),
            duration=duration, interval=interval, source_id=user.id,
            meta_json=json.dumps({"applied_in": inter.channel.id})
        )
        gif = info.get("gif_heal") or info.get("gif") or info.get("gif_attack")
        e = discord.Embed(
            title="💕 Régénération",
            description=f"{user.mention} applique **{emoji}** sur {target.mention} "
                        f"(+{val} PV / {_fmt_secs(interval)} pendant {_fmt_secs(duration)}).",
            color=discord.Color.teal()
        )
        if gif and isinstance(gif, str):
            e.set_image(url=gif)
        return e

    async def _do_shield(self, inter: discord.Interaction, user: discord.Member, info: dict, cible: Optional[discord.Member]) -> discord.Embed:
        target = cible or user
        val = await self._roll_val(info, 5)

        desc = ""
        # Priorité shields_db si présent
        if _add_shield and _get_shield:
            before = 0; after = 0; cap = None
            try:
                before = int(await _get_shield(target.id))
            except Exception:
                pass
            try:
                added = await _add_shield(target.id, val, cap_to_max=True)  # type: ignore[arg-type]
            except TypeError:
                added = await _add_shield(target.id, val)  # type: ignore[misc]
            try:
                after = int(await _get_shield(target.id))
            except Exception:
                after = before + int(val)
            if _get_max_shield:
                try:
                    cap = int(await _get_max_shield(target.id))
                except Exception:
                    cap = None
            gained = max(0, after - before)
            desc = f"🛡 {target.mention} gagne **{gained} PB**" + (f" (cap {cap})" if cap is not None else "") + "."
        else:
            # Fallback stats_db
            try:
                from stats_db import get_shield as _get, set_shield as _set
                before = int(await _get(target.id))
                after = max(0, before + int(val))
                await _set(target.id, after)
                desc = f"🛡 {target.mention} gagne **{after-before} PB**."
            except Exception:
                desc = f"🛡 {target.mention} gagne un bouclier."

        e = discord.Embed(title="🛡 Bouclier", description=desc, color=discord.Color.brand_teal())
        gif = info.get("gif_heal") or info.get("gif") or info.get("gif_attack")
        if gif and isinstance(gif, str):
            e.set_image(url=gif)
        return e

    # ──────────── Slash ────────────
    @app_commands.command(name="heal", description="Soigner / régénérer / donner un bouclier.")
    @app_commands.describe(objet="Emoji de l'objet (soin/regen/bouclier)", cible="Cible (par défaut: toi)")
    @app_commands.autocomplete(objet=_ac_items_heal_like)
    async def heal(self, inter: discord.Interaction, objet: str, cible: Optional[discord.Member] = None):
        meta = _info(objet)
        if not meta:
            return await inter.response.send_message("❌ Objet inconnu.", ephemeral=True)
        typ = str(meta.get("type", ""))

        if typ not in ("soin", "regen", "bouclier"):
            return await inter.response.send_message("❌ Il faut un objet de **soin**, **régénération** ou **bouclier**.", ephemeral=True)

        if not await self._consume(inter.user.id, objet):
            return await inter.response.send_message(f"❌ Tu n’as pas **{objet}**.", ephemeral=True)

        await inter.response.defer(thinking=True)

        try:
            if typ == "soin":
                emb = await self._do_heal(inter, inter.user, objet, meta, cible)
            elif typ == "regen":
                emb = await self._do_regen(inter, inter.user, objet, meta, cible)
            else:  # bouclier
                emb = await self._do_shield(inter, inter.user, meta, cible)
        except Exception as e:
            emb = discord.Embed(
                title="❗ Erreur",
                description=f"Action interrompue : `{type(e).__name__}`",
                color=discord.Color.red()
            )

        await inter.followup.send(embed=emb)


async def setup(bot: commands.Bot):
    await bot.add_cog(HealCog(bot))

# cogs/heal_cog.py
from __future__ import annotations

import json
from typing import List, Tuple, Dict, Optional

import discord
from discord import app_commands
from discord.ext import commands

from inventory_db import get_all_items, get_item_qty, remove_item
from stats_db import heal_user, get_hp
try:
    from effects_db import add_or_refresh_effect, remove_effect
except Exception:
    async def add_or_refresh_effect(**kwargs): return True
    async def remove_effect(*args, **kwargs): return None

from utils import OBJETS

# ==========================================================
# Helpers autocomplétion robustes
# ==========================================================
def _safe_item_rows_to_list(rows) -> List[Tuple[str, int]]:
    out: List[Tuple[str, int]] = []
    if not rows:
        return out
    if isinstance(rows, list):
        for r in rows:
            try:
                if isinstance(r, (tuple, list)) and len(r) >= 2:
                    e, q = str(r[0]), int(r[1])
                elif isinstance(r, dict):
                    e = str(r.get("emoji") or r.get("item") or r.get("id") or r.get("key") or "")
                    q = int(r.get("qty") or r.get("quantity") or r.get("count") or r.get("n") or 0)
                else:
                    continue
                if e and q > 0:
                    out.append((e, q))
            except Exception:
                continue
    elif isinstance(rows, dict):
        for e, q in rows.items():
            try:
                e = str(e); q = int(q)
                if e and q > 0:
                    out.append((e, q))
            except Exception:
                continue
    return out

async def _list_owned_items(uid: int) -> List[Tuple[str, int]]:
    owned: List[Tuple[str, int]] = []
    try:
        rows = await get_all_items(uid)
        owned.extend(_safe_item_rows_to_list(rows))
    except Exception:
        pass

    if not owned:
        for e in OBJETS.keys():
            try:
                q = int(await get_item_qty(uid, e) or 0)
                if q > 0:
                    owned.append((e, q))
            except Exception:
                continue

    merged: Dict[str, int] = {}
    for e, q in owned:
        merged[e] = merged.get(e, 0) + int(q)
    return sorted(merged.items(), key=lambda t: t[0])

def _choices_from_owned(owned: List[Tuple[str, int]], allowed_types: set, current: str):
    cur = (current or "").strip().lower()
    out: List[app_commands.Choice[str]] = []
    for emoji, qty in owned:
        info = OBJETS.get(emoji) or {}
        typ = str(info.get("type", ""))
        if typ not in allowed_types:
            continue
        label = info.get("nom") or info.get("label") or typ or "objet"
        display = f"{emoji} — {label} (x{qty})"
        if cur and (cur not in emoji and cur not in str(label).lower()):
            continue
        out.append(app_commands.Choice(name=display[:100], value=emoji))
        if len(out) >= 20:
            break
    return out

async def ac_heal_items(inter: discord.Interaction, current: str):
    try:
        if not inter or not inter.user:
            return []
        owned = await _list_owned_items(inter.user.id)
        return _choices_from_owned(owned, {"soin", "regen"}, current)
    except Exception:
        return []


# ==========================================================
# Heal Cog
# ==========================================================
class HealCog(commands.Cog):
    """/heal pour les objets de type soin / régénération."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="heal", description="Soigner un joueur avec un objet de soin.")
    @app_commands.describe(objet="Choisis un objet de soin", cible="Cible (par défaut: toi)")
    @app_commands.autocomplete(objet=ac_heal_items)
    async def heal_cmd(self, inter: discord.Interaction, objet: str, cible: Optional[discord.Member] = None):
        info = OBJETS.get(objet) or {}
        typ = str(info.get("type", ""))
        if typ not in {"soin", "regen"}:
            return await inter.response.send_message("❌ Il faut un **objet de soin**.", ephemeral=True)

        # possession + consommation
        qty = int(await get_item_qty(inter.user.id, objet) or 0)
        if qty <= 0:
            return await inter.response.send_message(f"❌ Tu n’as pas **{objet}**.", ephemeral=True)
        if not await remove_item(inter.user.id, objet, 1):
            return await inter.response.send_message("❌ Impossible d’utiliser l’objet.", ephemeral=True)

        await inter.response.defer(thinking=True)

        target = cible or inter.user
        if typ == "soin":
            amount = int(info.get("soin", info.get("heal", 10)) or 10)
            healed = await heal_user(inter.user.id, target.id, amount)
            hp_after, mx = await get_hp(target.id)
            hp_before = max(0, hp_after - healed)
            desc = (
                f"{inter.user.mention} rend **{healed} PV** à {target.mention} avec {objet}.\n"
                f"❤️ **{hp_before}/{mx}** → **{hp_after}/{mx}**"
                if healed > 0 else
                f"{target.mention} a déjà ses PV au maximum."
            )
            embed = discord.Embed(title="💊 Soin", description=desc, color=discord.Color.green())

        else:  # regen
            val = float(info.get("valeur", info.get("value", 2)) or 2)
            interval = int(info.get("intervalle", info.get("interval", 60)) or 60)
            duration = int(info.get("duree", info.get("duration", 300)) or 300)
            ok = await add_or_refresh_effect(
                user_id=target.id, eff_type="regen", value=val,
                duration=duration, interval=interval, source_id=inter.user.id,
                meta_json=json.dumps({"from": inter.user.id, "emoji": objet})
            )
            if ok:
                embed = discord.Embed(
                    title="💕 Régénération",
                    description=f"{inter.user.mention} applique **{objet}** sur {target.mention} "
                                f"(+{val} PV / {interval}s pendant {duration}s).",
                    color=discord.Color.teal()
                )
            else:
                embed = discord.Embed(
                    title="💕 Régénération",
                    description=f"⛔ Effet **bloqué** sur {target.mention}.",
                    color=discord.Color.red()
                )

        await inter.followup.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(HealCog(bot))

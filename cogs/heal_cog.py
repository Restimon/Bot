# cogs/heal_cog.py
from __future__ import annotations

import json
from typing import List, Tuple, Dict, Optional

import discord
from discord import app_commands
from discord.ext import commands

# Inventaire
from inventory_db import get_all_items, get_item_qty, remove_item

# PV
from stats_db import heal_user, get_hp

# Effets (pour 💕 régén)
try:
    from effects_db import add_or_refresh_effect
except Exception:
    async def add_or_refresh_effect(**kwargs):  # type: ignore
        return True

# Passifs (facultatif)
try:
    from passifs import trigger as passifs_trigger
except Exception:
    async def passifs_trigger(*args, **kwargs): return {}

# Catalogue & GIFs
try:
    from utils import OBJETS, GIFS  # GIFS contient aussi les gifs de soin
except Exception:
    OBJETS, GIFS = {}, {}

# ─────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────
def _obj_info(emoji: str) -> Dict:
    return dict(OBJETS.get(emoji) or {})

def _heal_amount_from_info(info: Dict) -> int:
    # Priorité: clé "soin", sinon "valeur"/"value"/"heal"
    for k in ("soin", "valeur", "value", "heal", "amount"):
        if k in info:
            try:
                return max(0, int(info[k]))
            except Exception:
                pass
    return 0

def _regen_params_from_info(info: Dict) -> Tuple[int, int, int]:
    # valeur par tick, interval, durée
    val =  int(info.get("valeur", info.get("value", 0)) or 0)
    itv =  int(info.get("intervalle", info.get("interval", 60)) or 60)
    dur =  int(info.get("duree", info.get("duration", 300)) or 300)
    return max(0, val), max(1, itv), max(1, dur)

def _gif_for_heal(emoji: str) -> Optional[str]:
    # utils._merge_gifs_into_objets a déjà mis gif_heal / gif
    info = OBJETS.get(emoji, {})
    url = info.get("gif_heal") or info.get("gif")
    if isinstance(url, str) and url.startswith("http"):
        return url
    # fallback direct depuis GIFS
    url = GIFS.get(emoji)
    return url if isinstance(url, str) and url.startswith("http") else None

def _oldstyle_heal_embed(
    emoji: str,
    healer: discord.Member,
    target: discord.Member,
    healed: int,
    hp_before: int,
    hp_after: int,
) -> discord.Embed:
    title = f"{emoji} Action de GotValis"
    e = discord.Embed(title=title, color=discord.Color.green())
    if healer.id == target.id:
        e.description = (
            f"{healer.mention} se soigne de **{healed} PV** avec {emoji}\n"
            f"❤️ **{hp_before} PV** + (**{healed} PV**) = ❤️ **{hp_after} PV**"
        )
    else:
        e.description = (
            f"{healer.mention} rend **{healed} PV** à {target.mention} avec {emoji}\n"
            f"❤️ **{hp_before} PV** + (**{healed} PV**) = ❤️ **{hp_after} PV**"
        )
    gif = _gif_for_heal(emoji)
    if gif:
        e.set_image(url=gif)
    return e

# ─────────────────────────────────────────────────────────
# Auto-complétion : ne propose que les objets de soin possédés
# ─────────────────────────────────────────────────────────
async def _list_owned_items(uid: int) -> List[Tuple[str, int]]:
    rows = await get_all_items(uid)  # [(emoji, qty)]
    out: List[Tuple[str, int]] = []
    if isinstance(rows, list):
        for it in rows:
            try:
                e, q = str(it[0]), int(it[1])
            except Exception:
                continue
            if q > 0:
                out.append((e, q))
    return out

async def ac_heal_items(inter: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
    owned = await _list_owned_items(inter.user.id)
    cur = (current or "").strip().lower()
    out: List[app_commands.Choice[str]] = []
    for emoji, qty in owned:
        info = _obj_info(emoji)
        typ = info.get("type")
        if typ not in ("soin", "regen"):
            continue
        label = "Soin direct" if typ == "soin" else "Régénération"
        name = f"{emoji} — {label} (x{qty})"
        if cur and cur not in name.lower():
            continue
        out.append(app_commands.Choice(name=name[:100], value=emoji))
        if len(out) >= 20:
            break
    return out

# ─────────────────────────────────────────────────────────
# Le COG
# ─────────────────────────────────────────────────────────
class HealCog(commands.Cog):
    """Commande /heal avec affichage 'style combat' + GIF."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="heal", description="Soigne-toi ou un joueur avec un objet de soin.")
    @app_commands.describe(
        objet="Choisis un objet (soin direct ou régénération)",
        cible="Cible à soigner (par défaut: toi)"
    )
    @app_commands.autocomplete(objet=ac_heal_items)
    async def heal_cmd(self, inter: discord.Interaction, objet: str, cible: Optional[discord.Member] = None):
        if not inter.guild:
            return await inter.response.send_message("❌ À utiliser dans un serveur.", ephemeral=True)

        info = _obj_info(objet)
        typ = info.get("type")
        if typ not in ("soin", "regen"):
            return await inter.response.send_message("❌ Cet objet n’est pas un objet de **soin**.", ephemeral=True)

        # vérif + consommation
        qty = await get_item_qty(inter.user.id, objet)
        if int(qty or 0) <= 0:
            return await inter.response.send_message("❌ Tu n'as pas cet objet.", ephemeral=True)
        ok = await remove_item(inter.user.id, objet, 1)
        if not ok:
            return await inter.response.send_message("❌ Impossible d'utiliser cet objet.", ephemeral=True)

        target = cible or inter.user
        await inter.response.defer(thinking=True)

        if typ == "soin":
            amount = _heal_amount_from_info(info)
            hp_before, mx = await get_hp(target.id)
            healed = max(0, int(await heal_user(inter.user.id, target.id, amount)))
            hp_after, mx = await get_hp(target.id)
            embed = _oldstyle_heal_embed(objet, inter.user, target, healed, hp_before, hp_after)

        else:  # typ == "regen"
            val, itv, dur = _regen_params_from_info(info)

            # hook passif (blocage/immunité éventuelle)
            try:
                pre = await passifs_trigger("on_effect_pre_apply", user_id=target.id, eff_type="regen") or {}
                if pre.get("blocked"):
                    return await inter.followup.send(
                        f"⛔ Effet **bloqué** sur {target.mention} : {pre.get('reason','')}"
                    )
            except Exception:
                pass

            await add_or_refresh_effect(
                user_id=target.id, eff_type="regen", value=float(val),
                duration=int(dur), interval=int(itv),
                source_id=inter.user.id, meta_json=json.dumps({"from": inter.user.id, "emoji": objet})
            )

            # Embed style combat + gif
            title = f"{objet} Action de GotValis"
            embed = discord.Embed(
                title=title,
                description=(
                    f"{inter.user.mention} applique une **régénération** sur {target.mention} :\n"
                    f"➕ +{val} PV toutes les {itv}s pendant {dur}s."
                ),
                color=discord.Color.teal()
            )
            gif = _gif_for_heal(objet)
            if gif:
                embed.set_image(url=gif)

        # Hook post-usage (dont_consume)
        try:
            post = await passifs_trigger("on_use_item", user_id=inter.user.id, item_emoji=objet, item_type=typ) or {}
            if post.get("dont_consume"):
                from inventory_db import add_item
                await add_item(inter.user.id, objet, 1)
        except Exception:
            pass

        await inter.followup.send(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(HealCog(bot))

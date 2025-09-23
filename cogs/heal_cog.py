# cogs/heal_cog.py
from __future__ import annotations

import random
from typing import Dict, List, Optional, Tuple

import discord
from discord.ext import commands
from discord import app_commands

# DBs
from inventory_db import get_item_qty, remove_item
from stats_db import get_hp, heal_user

# Catalogue (emoji -> fiche)
try:
    from utils import OBJETS  # type: ignore
except Exception:
    OBJETS: Dict[str, Dict] = {}

# Optional: notify live leaderboard
def _schedule_lb(bot: commands.Bot, gid: Optional[int], reason: str):
    if not gid:
        return
    try:
        from cogs.leaderboard_live import schedule_lb_update  # type: ignore
        schedule_lb_update(bot, gid, reason)
    except Exception:
        pass

# ─────────────────────────────────────────────────────────
# GIFs
# ─────────────────────────────────────────────────────────
_HEAL_GIFS: List[str] = [
    # Feel free to swap with your own
    "https://media.tenor.com/Gm7x2q5dQOYAAAAC/heal-green.gif",
    "https://media.tenor.com/3f3oC0R2qGoAAAAC/heal-healing.gif",
    "https://media.tenor.com/3b2m1otcjdIAAAAC/magic-heal.gif",
    "https://media.tenor.com/9y3RFP6gqI8AAAAC/potion-heal.gif",
]

def _pick_gif(info: Dict) -> Optional[str]:
    # If the item defines a custom GIF/URL, use it
    url = info.get("gif") or info.get("image") or info.get("url")
    if isinstance(url, str) and url.startswith(("http://", "https://")):
        return url
    return random.choice(_HEAL_GIFS)

# ─────────────────────────────────────────────────────────
# Autocomplete: only show owned heal/regen items
# ─────────────────────────────────────────────────────────
async def _ac_heal_items(inter: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
    cur = (current or "").strip().lower()
    uid = inter.user.id
    out: List[app_commands.Choice[str]] = []
    for emoji, info in OBJETS.items():
        typ = str(info.get("type", "") or "")
        if typ not in ("soin", "regen"):
            continue
        try:
            q = int(await get_item_qty(uid, emoji) or 0)
        except Exception:
            q = 0
        if q <= 0:
            continue

        label = "soin"
        try:
            if typ == "soin":
                val = int(info.get("soin", info.get("value", info.get("valeur", 0))) or 0)
                label = f"soin +{val}" if val else "soin"
            elif typ == "regen":
                v = int(info.get("valeur", info.get("value", 0)) or 0)
                itv = int(info.get("intervalle", info.get("interval", 60)) or 60)
                d = int(info.get("duree", info.get("duration", 300)) or 300)
                label = f"regen +{v}/{max(1,itv)}s for {d}s"
        except Exception:
            pass

        name = f"{emoji} • {label} (x{q})"
        if not cur or cur in name.lower():
            out.append(app_commands.Choice(name=name[:100], value=emoji))
            if len(out) >= 20:
                break
    return out

# ─────────────────────────────────────────────────────────
# Cog
# ─────────────────────────────────────────────────────────
class HealCog(commands.Cog):
    """/heal — use a heal/regen item on yourself or someone else, with GIF + before/after HP"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="heal", description="Soigne un joueur avec un objet de soin.")
    @app_commands.describe(objet="Emoji de l'objet (soin/regen)", cible="Cible (par défaut: toi)")
    @app_commands.autocomplete(objet=_ac_heal_items)
    async def heal(
        self,
        inter: discord.Interaction,
        objet: str,
        cible: Optional[discord.Member] = None,
    ):
        if not inter.guild:
            return await inter.response.send_message("❌ À utiliser dans un serveur.", ephemeral=True)

        info = OBJETS.get(objet) or {}
        typ = str(info.get("type", "") or "")
        if typ not in ("soin", "regen"):
            return await inter.response.send_message(
                "Cet objet n’est pas un **soin/regen**. Utilise **/fight** ou **/use** selon le type.",
                ephemeral=True,
            )

        # Check inventory & consume 1
        try:
            have = int(await get_item_qty(inter.user.id, objet) or 0)
        except Exception:
            have = 0
        if have <= 0:
            return await inter.response.send_message(f"Tu n’as pas **{objet}**.", ephemeral=True)
        ok = await remove_item(inter.user.id, objet, 1)
        if not ok:
            return await inter.response.send_message(f"Impossible de consommer **{objet}**.", ephemeral=True)

        await inter.response.defer(thinking=True)

        target = cible or inter.user

        # Get HP before
        hp_before, mx = await get_hp(target.id)

        # Apply heal
        healed = 0
        if typ == "soin":
            val = int(info.get("soin", info.get("value", info.get("valeur", 0))) or 0)
            if val > 0:
                healed = await heal_user(inter.user.id, target.id, val)
        else:
            # regen as immediate 1-tick heal baseline (optional); full tick engine handled by effects_db elsewhere
            tick_val = int(info.get("valeur", info.get("value", 0)) or 0)
            if tick_val > 0:
                healed = await heal_user(inter.user.id, target.id, min(tick_val, mx))  # 1 pulse now

        # HP after
        hp_after, _ = await get_hp(target.id)

        # Build embed
        title = f"{objet} Soin"
        desc_lines = [
            f"{inter.user.mention} **rend {healed} PV** à {target.mention} avec {objet}."
            if healed > 0 else
            f"{inter.user.mention} utilise {objet} sur {target.mention}, mais rien à soigner."
        ]
        desc_lines.append(f"❤️ {hp_before}/{mx} → ❤️ **{hp_after}/{mx}**")

        embed = discord.Embed(title=title, description="\n".join(desc_lines), color=discord.Color.green())

        gif = _pick_gif(info)
        if gif:
            embed.set_image(url=gif)

        await inter.followup.send(embed=embed)

        # LB refresh
        _schedule_lb(self.bot, inter.guild.id if inter.guild else None, "heal")


async def setup(bot: commands.Bot):
    await bot.add_cog(HealCog(bot))

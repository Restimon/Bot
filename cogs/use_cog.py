# cogs/use_cog.py
from __future__ import annotations

import asyncio
import json
import random
from typing import Dict, List, Optional, Tuple

import discord
from discord import app_commands
from discord.ext import commands

# Catalogues / GIFs
try:
    from utils import OBJETS, FIGHT_GIFS as _GIFS  # type: ignore
except Exception:
    OBJETS: Dict[str, Dict] = {}
    _GIFS = {}

# Types autorisés pour /use (tout le reste passe par /fight ou /heal)
ALLOWED_USE_TYPES = {
    "vol", "bouclier", "vaccin", "immunite", "esquive+", "reduction", "mysterybox",
    # ajoute ici d'autres types utilitaires si besoin
}
# Types explicitement interdits sur /use
BLOCKED_USE_TYPES = {
    "attaque", "attaque_chaine", "soin", "regen", "poison", "infection", "brulure", "virus"
}

_FALLBACK_GIFS = {
    "vol": [
        "https://media.tenor.com/1aUIx4m7X-8AAAAC/steal-pickpocket.gif",
        "https://media.tenor.com/dC8XnW1y8hUAAAAC/steal-sneaky.gif",
    ],
    "buff": [
        "https://media.tenor.com/KkN9cCwzj8IAAAAC/shield-protect.gif",
    ],
    "box": [
        "https://media.tenor.com/dxgXgJ8bqK8AAAAC/lootbox-open.gif",
    ],
}

# Inventaire
from inventory_db import (
    get_all_items,
    get_item_qty,
    add_item,
    remove_item,
)

# Effets
try:
    from effects_db import add_or_refresh_effect
except Exception:
    async def add_or_refresh_effect(**kwargs):  # type: ignore
        return True

# Passifs
try:
    from passifs import trigger as passifs_trigger
except Exception:
    async def passifs_trigger(*args, **kwargs):
        return {}

# Leaderboard live
try:
    from cogs.leaderboard_live import schedule_lb_update
except Exception:
    def schedule_lb_update(*args, **kwargs):
        pass


def _obj_info(emoji: str) -> Optional[Dict]:
    info = OBJETS.get(emoji)
    return dict(info) if isinstance(info, dict) else None

async def _consume_item(user_id: int, emoji: str) -> bool:
    try:
        q = await get_item_qty(user_id, emoji)
        if int(q or 0) <= 0:
            return False
        ok = await remove_item(user_id, emoji, 1)
        return bool(ok)
    except Exception:
        return False

def _pick_gif(emoji: str, info: Optional[Dict], kind: str) -> Optional[str]:
    for k in ("gif", "image", "url", "gif_url"):
        if info and isinstance(info.get(k), str):
            url = info[k].strip()
            if url.startswith("http"):
                return url
    if isinstance(_GIFS, dict):
        url = _GIFS.get(emoji)
        if isinstance(url, str) and url.startswith("http"):
            return url
    lst = _FALLBACK_GIFS.get(kind) or []
    return random.choice(lst) if lst else None

def _label(info: Dict, default: str) -> str:
    return str(info.get("nom") or info.get("label") or default)


# ─────────────────────────────────────────────────────────
# Autocomplete — ne montrer que les items utilisables par /use
# ─────────────────────────────────────────────────────────
async def _ac_items_use_only(inter: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
    uid = inter.user.id
    cur = (current or "").strip().lower()
    try:
        rows = await get_all_items(uid)
    except Exception:
        rows = []

    out: List[app_commands.Choice[str]] = []
    for emoji, qty in rows:
        if int(qty or 0) <= 0:
            continue
        info = _obj_info(emoji) or {}
        typ = str(info.get("type", "objet")).lower()
        if typ in BLOCKED_USE_TYPES or (ALLOWED_USE_TYPES and typ not in ALLOWED_USE_TYPES):
            continue
        name = _label(info, typ)
        display = f"{emoji} — {name} (x{qty})"
        if cur and (cur not in emoji and cur not in str(name).lower()):
            continue
        out.append(app_commands.Choice(name=display[:100], value=emoji))
        if len(out) >= 20:
            break
    return out


class UseCog(commands.Cog):
    """Commande /use : objets utilitaires uniquement (pas d’attaque/soin/regen/DOT)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="use", description="Utiliser un objet utilitaire (vol, buffs, vaccin, box…).")
    @app_commands.describe(objet="Emoji de l'objet", cible="Cible (si nécessaire)")
    @app_commands.autocomplete(objet=_ac_items_use_only)
    async def use(self, inter: discord.Interaction, objet: str, cible: Optional[discord.Member] = None):
        info = _obj_info(objet)
        if not info:
            return await inter.response.send_message("Objet inconnu.", ephemeral=True)

        typ = str(info.get("type", "objet")).lower()

        # Bloque proprement les types qui doivent passer par /fight ou /heal
        if typ in {"attaque", "attaque_chaine", "poison", "infection", "brulure", "virus"}:
            return await inter.response.send_message(
                f"⚠️ **{objet}** est un objet d’attaque/DOT. Utilise plutôt **/fight**.",
                ephemeral=True,
            )
        if typ in {"soin", "regen"}:
            return await inter.response.send_message(
                f"⚠️ **{objet}** est un objet de soin/régénération. Utilise plutôt **/heal**.",
                ephemeral=True,
            )
        if ALLOWED_USE_TYPES and typ not in ALLOWED_USE_TYPES:
            return await inter.response.send_message(
                f"⚠️ **{objet}** n’est pas utilisable via **/use**.",
                ephemeral=True,
            )

        # Consomme l’objet (consommable) puis applique l’effet
        if not await _consume_item(inter.user.id, objet):
            return await inter.response.send_message(
                f"Tu n’as pas **{objet}** dans ton inventaire.", ephemeral=True
            )

        await inter.response.defer(thinking=True)

        title = f"{objet} {_label(info, 'Objet')}"
        embed = discord.Embed(title=title, color=discord.Color.blurple())

        # ── VOL
        if typ == "vol":
            if not isinstance(cible, discord.Member):
                return await inter.followup.send("Il faut **une cible** pour utiliser cet objet.", ephemeral=True)

            try:
                res = await passifs_trigger("on_theft_attempt", attacker_id=inter.user.id, target_id=cible.id) or {}
            except Exception:
                res = {}
            if res.get("blocked"):
                embed.description = f"🛡 {cible.mention} est **protégé** contre le vol."
                gif = _pick_gif(objet, info, "vol")
                if gif:
                    embed.set_image(url=gif)
                await inter.followup.send(embed=embed)
                return

            base_chance = float(info.get("chance", 0.25)) if isinstance(info.get("chance", None), (int, float, str)) else 0.25
            try:
                chance = max(0.0, min(1.0, float(base_chance)))
            except Exception:
                chance = 0.25

            if random.random() < chance:
                # pioche pondérée dans l'inventaire de la cible
                items = await get_all_items(cible.id)
                pool: List[str] = []
                for emj, q in items:
                    q = int(q or 0)
                    if q > 0:
                        pool.extend([emj] * q)
                if not pool:
                    embed.description = f"🕵️ {inter.user.mention} tente de voler {cible.mention}… mais **rien à voler**."
                else:
                    stolen = random.choice(pool)
                    if await remove_item(cible.id, stolen, 1):
                        await add_item(inter.user.id, stolen, 1)
                        embed.description = f"🕵️ **Vol réussi !** {inter.user.mention} dérobe **{stolen}** à {cible.mention}."
                    else:
                        embed.description = f"🕵️ {inter.user.mention} a failli voler {cible.mention}, mais l’objet a filé…"
            else:
                embed.description = f"🕵️ **Vol raté** — {cible.mention} t’a vu venir."

            gif = _pick_gif(objet, info, "vol")
            if gif:
                embed.set_image(url=gif)

        # ── BOUCLIER (PB temporaires via effects_db)
        elif typ == "bouclier":
            who = cible or inter.user
            val = int(info.get("valeur", info.get("value", 0)) or 0)
            dur = int(info.get("duree", info.get("duration", 3600)) or 3600)
            await add_or_refresh_effect(
                user_id=who.id, eff_type="bouclier", value=val,
                duration=dur, interval=0, source_id=inter.user.id,
                meta_json=json.dumps({"applied_in": inter.channel.id})
            )
            embed.title = f"{objet} Bouclier"
            embed.description = f"{inter.user.mention} applique **{val} PB temporaires** sur {who.mention}."
            gif = _pick_gif(objet, info, "buff")
            if gif:
                embed.set_image(url=gif)

        # ── VACCIN / IMMUNITÉ
        elif typ in {"vaccin", "immunite"}:
            who = cible or inter.user
            dur = int(info.get("duree", info.get("duration", 3600)) or 3600)
            await add_or_refresh_effect(
                user_id=who.id, eff_type="immunite", value=1,
                duration=dur, interval=0, source_id=inter.user.id,
                meta_json=json.dumps({"applied_in": inter.channel.id})
            )
            embed.title = f"{objet} Immunité"
            embed.description = f"{who.mention} devient **immunisé** pendant {dur//60} min."
            gif = _pick_gif(objet, info, "buff")
            if gif:
                embed.set_image(url=gif)

        # ── BUFFS DIVERS
        elif typ in {"esquive+", "reduction"}:
            who = cible or inter.user
            val = int(info.get("valeur", info.get("value", 0)) or 0)
            dur = int(info.get("duree", info.get("duration", 3600)) or 3600)
            await add_or_refresh_effect(
                user_id=who.id, eff_type=typ, value=val,
                duration=dur, interval=0, source_id=inter.user.id,
                meta_json=json.dumps({"applied_in": inter.channel.id})
            )
            label = "Esquive+" if typ == "esquive+" else "Réduction de dégâts"
            embed.title = f"{objet} {label}"
            more = f" (+{val})" if val else ""
            embed.description = f"{inter.user.mention} applique **{label}**{more} sur {who.mention}."
            gif = _pick_gif(objet, info, "buff")
            if gif:
                embed.set_image(url=gif)

        # ── BOX
        elif typ == "mysterybox":
            pool = [e for e in OBJETS.keys() if e != objet and (OBJETS.get(e, {}).get("type", "") not in BLOCKED_USE_TYPES)]
            if not pool:
                pool = ["🍀", "🧪", "🛡️"]
            got = random.choice(pool)
            await add_item(inter.user.id, got, 1)
            embed.title = f"{objet} Box ouverte"
            embed.description = f"{inter.user.mention} obtient **{got}** !"
            gif = _pick_gif(objet, info, "box")
            if gif:
                embed.set_image(url=gif)

        else:
            embed.description = f"{inter.user.mention} utilise **{objet}**. (Type utilitaire non-spécialisé)"

        try:
            await passifs_trigger("on_use_item", user_id=inter.user.id, item_emoji=objet, item_type=typ)
        except Exception:
            pass

        if inter.guild:
            try:
                schedule_lb_update(self.bot, inter.guild.id, "use")
            except Exception:
                pass

        await inter.followup.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(UseCog(bot))

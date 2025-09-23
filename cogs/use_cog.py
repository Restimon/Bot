# cogs/use_cog.py
from __future__ import annotations

import asyncio
import json
import random
from typing import Dict, List, Optional, Tuple

import discord
from discord import app_commands
from discord.ext import commands

# Catalogues / GIFs (robustes si utils.py n’existe pas)
try:
    from utils import OBJETS, FIGHT_GIFS as _GIFS  # type: ignore
except Exception:
    OBJETS: Dict[str, Dict] = {}
    _GIFS = {}

# Fallback GIFs locaux par type d’usage
_FALLBACK_GIFS = {
    "vol": [
        # quelques gifs génériques de “steal/pickpocket”
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

# Effets (buffs simples)
try:
    from effects_db import add_or_refresh_effect
except Exception:
    async def add_or_refresh_effect(**kwargs):  # type: ignore
        return True

# Passifs (événements)
try:
    from passifs import trigger as passifs_trigger
except Exception:
    async def passifs_trigger(*args, **kwargs):
        return {}

# Leaderboard live (rafraîchissement asynchrone)
try:
    from cogs.leaderboard_live import schedule_lb_update
except Exception:
    def schedule_lb_update(*args, **kwargs):
        pass


# ─────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────
def _obj_info(emoji: str) -> Optional[Dict]:
    info = OBJETS.get(emoji)
    return dict(info) if isinstance(info, dict) else None

async def _consume_item(user_id: int, emoji: str) -> bool:
    """Retire 1 exemplaire si dispo."""
    try:
        q = await get_item_qty(user_id, emoji)
        if int(q or 0) <= 0:
            return False
        ok = await remove_item(user_id, emoji, 1)
        return bool(ok)
    except Exception:
        return False

def _pick_gif(emoji: str, info: Optional[Dict], kind: str) -> Optional[str]:
    """Ordre: info.gif → utils.FIGHT_GIFS[emoji] → fallback par type."""
    # depuis la fiche
    for k in ("gif", "image", "url", "gif_url"):
        if info and isinstance(info.get(k), str):
            url = info[k].strip()
            if url.startswith("http"):
                return url

    # mapping utils (souvent utilisé dans le combat)
    if isinstance(_GIFS, dict):
        url = _GIFS.get(emoji)
        if isinstance(url, str) and url.startswith("http"):
            return url

    # fallback par type
    lst = _FALLBACK_GIFS.get(kind) or []
    return random.choice(lst) if lst else None

def _label(info: Dict, default: str) -> str:
    return str(info.get("nom") or info.get("label") or default)


# ─────────────────────────────────────────────────────────
# Autocomplete — items possédés utilisables
# ─────────────────────────────────────────────────────────
async def _ac_items_any(inter: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
    uid = inter.user.id
    cur = (current or "").strip().lower()

    # On lit tout l’inventaire réel
    try:
        rows = await get_all_items(uid)
    except Exception:
        rows = []

    out: List[app_commands.Choice[str]] = []
    for emoji, qty in rows:
        if int(qty or 0) <= 0:
            continue
        info = _obj_info(emoji) or {}
        typ = str(info.get("type", "objet"))
        name = _label(info, typ)
        display = f"{emoji} — {name} (x{qty})"
        if cur and (cur not in emoji and cur not in str(name).lower()):
            continue
        out.append(app_commands.Choice(name=display[:100], value=emoji))
        if len(out) >= 20:
            break
    return out


# ─────────────────────────────────────────────────────────
# Cog
# ─────────────────────────────────────────────────────────
class UseCog(commands.Cog):
    """Commande /use pour objets utilitaires : vol, buffs, box, bouclier, vaccin, etc."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ========== /use ==========
    @app_commands.command(name="use", description="Utiliser un objet de ton inventaire (vol, buffs, box…).")
    @app_commands.describe(objet="Emoji de l'objet", cible="Cible (si nécessaire)")
    @app_commands.autocomplete(objet=_ac_items_any)
    async def use(self, inter: discord.Interaction, objet: str, cible: Optional[discord.Member] = None):
        info = _obj_info(objet)
        if not info:
            return await inter.response.send_message("Objet inconnu.", ephemeral=True)

        # On consomme l'objet dès l'utilisation (même si vol échoue = consommable)
        if not await _consume_item(inter.user.id, objet):
            return await inter.response.send_message(f"Tu n’as pas **{objet}** dans ton inventaire.", ephemeral=True)

        await inter.response.defer(thinking=True)

        typ = str(info.get("type", "objet"))
        title = f"{objet} {_label(info, 'Objet')}"
        embed = discord.Embed(title=title, color=discord.Color.blurple())

        # 1) VOL
        if typ == "vol":
            # nécessite une cible
            if not isinstance(cible, discord.Member):
                return await inter.followup.send("Il faut **une cible** pour utiliser cet objet.", ephemeral=True)

            # passifs : tentative de vol (peut bloquer)
            try:
                res = await passifs_trigger("on_theft_attempt", attacker_id=inter.user.id, target_id=cible.id) or {}
            except Exception:
                res = {}
            if res.get("blocked"):
                embed.description = f"🛡 {cible.mention} est **intouchable** (anti-vol)."
                gif = _pick_gif(objet, info, "vol")
                if gif:
                    embed.set_image(url=gif)
                await inter.followup.send(embed=embed)
                return

            # taux de succès (dans la fiche sinon 25 %)
            try:
                base_chance = float(info.get("chance", 0.25))
            except Exception:
                base_chance = 0.25

            success = (random.random() < max(0.0, min(1.0, base_chance)))

            if success:
                # inventaire réel de la cible
                items = await get_all_items(cible.id)
                # on construit une “liste pondérée” par quantité
                pool: List[str] = []
                for emj, q in items:
                    q = int(q or 0)
                    if q <= 0:
                        continue
                    # on peut filtrer certains items si besoin (ex : pas voler des clés spéciales)
                    pool.extend([emj] * q)

                if not pool:
                    embed.description = f"🕵️ {inter.user.mention} essaie de voler {cible.mention}… mais **il n’a rien** à voler."
                else:
                    stolen = random.choice(pool)
                    # retire 1 chez la cible, ajoute 1 chez l’attaquant
                    ok = await remove_item(cible.id, stolen, 1)
                    if ok:
                        await add_item(inter.user.id, stolen, 1)
                        embed.description = (
                            f"🕵️ **Vol réussi !**\n"
                            f"{inter.user.mention} dérobe **{stolen}** à {cible.mention}."
                        )
                    else:
                        embed.description = (
                            f"🕵️ {inter.user.mention} a failli voler {cible.mention}, "
                            "mais l’objet a disparu au dernier moment…"
                        )
            else:
                embed.description = f"🕵️ **Vol raté…** {cible.mention} a été plus rapide."

            gif = _pick_gif(objet, info, "vol")
            if gif:
                embed.set_image(url=gif)

        # 2) BOUCLIER (buff simple stocké dans effects_db)
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

        # 3) VACCIN (immunité)
        elif typ == "vaccin":
            who = cible or inter.user
            dur = int(info.get("duree", info.get("duration", 3600)) or 3600)
            await add_or_refresh_effect(
                user_id=who.id, eff_type="immunite", value=1,
                duration=dur, interval=0, source_id=inter.user.id,
                meta_json=json.dumps({"applied_in": inter.channel.id})
            )
            embed.title = f"{objet} Vaccin"
            embed.description = f"{who.mention} devient **immunisé** pendant {dur//60} min."
            gif = _pick_gif(objet, info, "buff")
            if gif:
                embed.set_image(url=gif)

        # 4) BUFFS DIVERS (esquive+, reduction, immunite…)
        elif typ in ("esquive+", "reduction", "immunite"):
            who = cible or inter.user
            val = int(info.get("valeur", info.get("value", 0)) or 0)
            dur = int(info.get("duree", info.get("duration", 3600)) or 3600)
            await add_or_refresh_effect(
                user_id=who.id, eff_type=typ, value=val,
                duration=dur, interval=0, source_id=inter.user.id,
                meta_json=json.dumps({"applied_in": inter.channel.id})
            )
            labels = {"esquive+": "Esquive+", "reduction": "Réduction de dégâts", "immunite": "Immunité"}
            embed.title = f"{objet} {labels.get(typ, 'Buff')}"
            val_txt = f" (**+{val}**) " if val else " "
            embed.description = f"{inter.user.mention} applique **{labels.get(typ,'Buff')}**{val_txt}sur {who.mention}."
            gif = _pick_gif(objet, info, "buff")
            if gif:
                embed.set_image(url=gif)

        # 5) BOX (donne un item aléatoire) – logique volontaire ici
        elif typ == "mysterybox":
            # Ici seulement on donne un item random (comportement voulu pour la box).
            # Tu peux remplacer par ta propre logique si besoin.
            pool = [e for e in OBJETS.keys() if e != objet]
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
            # par défaut
            embed.description = (
                f"{inter.user.mention} utilise **{objet}**. "
                "Cet objet n’a pas encore de logique dédiée."
            )

        # Hook passifs post-usage
        try:
            await passifs_trigger("on_use_item", user_id=inter.user.id, item_emoji=objet, item_type=typ)
        except Exception:
            pass

        # MAJ du leaderboard (coins/pv/pb peuvent changer après un “vol” ou buff économique)
        if inter.guild:
            try:
                schedule_lb_update(self.bot, inter.guild.id, "use")
            except Exception:
                pass

        await inter.followup.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(UseCog(bot))

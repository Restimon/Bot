# cogs/use_cog.py
from __future__ import annotations

import asyncio
import json
import random
from typing import Dict, List, Optional, Tuple

import discord
from discord.ext import commands
from discord import app_commands

# ─────────────────────────────────────────────────────────
# Catalogues / GIFs
# ─────────────────────────────────────────────────────────
try:
    # OBJETS : dict[emoji] -> fiche (type, valeurs, etc.)
    # FIGHT_GIFS : dict[emoji] -> url (fallback si pas de gif_use dédié)
    # USE_GIFS   : dict[emoji] -> url (si tu en as un dédié pour /use)
    from utils import OBJETS, FIGHT_GIFS, USE_GIFS, get_random_item  # type: ignore
except Exception:
    OBJETS = {}
    FIGHT_GIFS = {}
    USE_GIFS = {}
    def get_random_item(debug: bool = False):
        return random.choice(["🍀", "🛡️", "🧪", "📦"])

# ─────────────────────────────────────────────────────────
# DB inventaire / effets / bouclier
# ─────────────────────────────────────────────────────────
from inventory_db import get_item_qty, remove_item, add_item, get_all_items
try:
    from effects_db import add_or_refresh_effect
except Exception:
    async def add_or_refresh_effect(**kwargs): return True  # stub

# Boucliers : si shields_db présent, on l’utilise ; sinon on essaie via stats_db
try:
    from shields_db import add_shield as shields_add_shield, get_shield as shields_get_shield, get_max_shield as shields_get_max
except Exception:
    shields_add_shield = None
    shields_get_shield = None
    shields_get_max = None

try:
    from stats_db import get_shield as stats_get_shield, set_shield as stats_set_shield
except Exception:
    async def stats_get_shield(user_id: int) -> int: return 0
    async def stats_set_shield(user_id: int, value: int): return None

# Passifs (optionnels)
try:
    from passifs import trigger as passifs_trigger
except Exception:
    async def passifs_trigger(*args, **kwargs): return {}

# Leaderboard live (optionnel)
try:
    from cogs.leaderboard_live import schedule_lb_update  # type: ignore
except Exception:
    def schedule_lb_update(bot, guild_id: int, reason: str = ""):  # stub
        pass


# ─────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────
ALLOWED_USE_TYPES: Tuple[str, ...] = (
    "vaccin", "bouclier", "mysterybox", "vol", "esquive+", "reduction", "immunite"
)  # pas d'attaque/soin/regen ici

def _obj_info(emoji: str) -> Optional[Dict]:
    info = OBJETS.get(emoji)
    return dict(info) if isinstance(info, dict) else None

def _pick_gif(emoji: str, info: Optional[Dict]) -> Optional[str]:
    """
    Priorité:
      1) info['gif_use']  (spécifique à /use si défini)
      2) info['gif']      (gif générique de l'objet)
      3) USE_GIFS[emoji]  (table dédiée aux gifs d'usage)
      4) FIGHT_GIFS[emoji] (fallback si tu réutilises les mêmes gifs)
    """
    if info:
        for key in ("gif_use", "gif", "gif_url", "image"):
            url = info.get(key)
            if isinstance(url, str) and url.startswith(("http://", "https://")):
                return url

    if isinstance(USE_GIFS, dict):
        url = USE_GIFS.get(emoji)
        if isinstance(url, str) and url.startswith(("http://", "https://")):
            return url

    if isinstance(FIGHT_GIFS, dict):
        url = FIGHT_GIFS.get(emoji)
        if isinstance(url, str) and url.startswith(("http://", "https://")):
            return url

    return None

async def _list_owned_items(uid: int) -> List[Tuple[str, int]]:
    """[(emoji, qty)] depuis la DB inventaire."""
    rows = await get_all_items(uid)
    out: List[Tuple[str, int]] = []
    for item_key, qty in rows:
        try:
            q = int(qty)
            if q > 0:
                out.append((str(item_key), q))
        except Exception:
            continue
    return out

async def _autocomplete_use_items(inter: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
    uid = inter.user.id
    cur = (current or "").strip().lower()

    owned = await _list_owned_items(uid)
    out: List[app_commands.Choice[str]] = []

    for emoji, qty in owned:
        info = OBJETS.get(emoji) or {}
        typ = str(info.get("type", ""))
        if typ not in ALLOWED_USE_TYPES:
            continue
        label = info.get("nom") or info.get("label") or typ
        display = f"{emoji} — {label} (x{qty})"
        if cur and (cur not in emoji and cur not in str(label).lower()):
            continue
        out.append(app_commands.Choice(name=display[:100], value=emoji))
        if len(out) >= 20:
            break
    return out

async def _consume_item(user_id: int, emoji: str) -> bool:
    qty = await get_item_qty(user_id, emoji)
    if int(qty or 0) <= 0:
        return False
    return await remove_item(user_id, emoji, 1)

def _title_for_use(emoji: str, info: Optional[Dict]) -> str:
    name = ""
    if info:
        name = str(info.get("nom") or info.get("label") or info.get("type") or "")
    return f"{emoji} Utilisation — {name}" if name else f"{emoji} Utilisation"

async def _apply_shield(user_id: int, value: int, cap_to_max: bool = True) -> int:
    """
    Ajoute un bouclier. Préfère shields_db si dispo, sinon stats_db.
    Retourne la nouvelle valeur de PB.
    """
    if shields_add_shield:
        return await shields_add_shield(user_id, int(value), cap_to_max=True)
    # fallback simple avec stats_db: on “cap” à 50 par défaut
    cur = int(await stats_get_shield(user_id))
    new_val = max(0, cur + int(value))
    if cap_to_max:
        new_val = min(new_val, 50)
    await stats_set_shield(user_id, new_val)
    return new_val

async def _steal_random_item(thief_id: int, victim_id: int) -> Optional[str]:
    """
    Vole 1 quantité d’un item aléatoire présent chez la cible (qty>0).
    Retourne l’emoji volé, ou None si rien.
    """
    items = await get_all_items(victim_id)
    pool = [(e, q) for (e, q) in items if int(q) > 0]
    if not pool:
        return None
    emoji, _ = random.choice(pool)
    ok = await remove_item(victim_id, emoji, 1)
    if not ok:
        return None
    await add_item(thief_id, emoji, 1)
    return str(emoji)


# ─────────────────────────────────────────────────────────
# Le COG
# ─────────────────────────────────────────────────────────
class UseCog(commands.Cog):
    """Commande /use — objets utilitaires (pas d'attaque/soin/regen ici)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="use", description="Utiliser un objet utilitaire de ton inventaire.")
    @app_commands.describe(
        objet="Choisis un objet utilitaire (vaccin, bouclier, vol, esquive+, reduction, immunite, mysterybox)",
        cible="Cible (selon l'objet)"
    )
    @app_commands.autocomplete(objet=_autocomplete_use_items)
    async def use(self, inter: discord.Interaction, objet: str, cible: Optional[discord.Member] = None):
        info = _obj_info(objet)
        if not info:
            return await inter.response.send_message("Objet inconnu.", ephemeral=True)

        typ = str(info.get("type", ""))
        if typ not in ALLOWED_USE_TYPES:
            return await inter.response.send_message(
                "❌ Cet objet ne se consomme pas via **/use** (attaque/soin/régénération ont leurs commandes dédiées).",
                ephemeral=True
            )

        if not await _consume_item(inter.user.id, objet):
            return await inter.response.send_message(f"Tu n’as pas **{objet}** dans ton inventaire.", ephemeral=True)

        await inter.response.defer(thinking=True)

        embed = discord.Embed(
            title=_title_for_use(objet, info),
            color=discord.Color.blurple()
        )
        gif = _pick_gif(objet, info)
        if gif:
            embed.set_image(url=gif)

        # ── ROUTAGE PAR TYPE ─────────────────────────────────
        # 1) Vaccin → on l’interprète comme une “immunité” temporaire (buff passif)
        if typ == "vaccin":
            who = cible or inter.user
            val = int(info.get("valeur", info.get("value", 1)) or 1)
            dur = int(info.get("duree", info.get("duration", 3600)) or 3600)
            ok = await add_or_refresh_effect(
                user_id=who.id, eff_type="immunite", value=float(val),
                duration=dur, interval=0,
                source_id=inter.user.id,
                meta_json=json.dumps({"applied_in": inter.channel.id})
            )
            if not ok:
                embed.description = f"⚠️ L’effet **immunité** n’a pas pu être appliqué à {who.mention}."
            else:
                embed.description = f"{inter.user.mention} utilise **{objet}** sur {who.mention} → ⭐ Immunité appliquée ({dur//60} min)."

        # 2) Bouclier → ajoute des PB
        elif typ == "bouclier":
            who = cible or inter.user
            val = int(info.get("valeur", info.get("value", 10)) or 10)
            new_pb = await _apply_shield(who.id, val, cap_to_max=True)
            embed.description = f"{inter.user.mention} applique **{objet}** → 🛡 **{val}** PB. Nouveau PB de {who.mention}: **{new_pb}**."

        # 3) Mystery box → donne un item random
        elif typ == "mysterybox":
            got = get_random_item(debug=False)
            await add_item(inter.user.id, got, 1)
            embed.description = f"📦 {inter.user.mention} ouvre **{objet}** et obtient **{got}** !"

        # 4) Vol → tente de voler 1 item random dans l’inventaire de la cible
        elif typ == "vol":
            if not isinstance(cible, discord.Member):
                return await inter.followup.send("Il faut une **cible** pour voler.", ephemeral=True)

            # Passifs : possibilité de bloquer
            try:
                res = await passifs_trigger("on_theft_attempt", attacker_id=inter.user.id, target_id=cible.id) or {}
                if res.get("blocked"):
                    embed.description = f"🛡 {cible.mention} est **intouchable** (anti-vol)."
                    await inter.followup.send(embed=embed)
                    return
            except Exception:
                pass

            # chance de réussite (par défaut 25%, surcharge via fiche 'chance')
            base_chance = float(info.get("chance", 0.25) or 0.25)
            success = (random.random() < base_chance)

            if not success:
                embed.description = f"🕵️ {inter.user.mention} tente de voler {cible.mention}… **raté**."
            else:
                stolen = await _steal_random_item(inter.user.id, cible.id)
                if not stolen:
                    embed.description = f"🕵️ {inter.user.mention} tente de voler {cible.mention}, mais **rien à voler**."
                else:
                    embed.description = f"🕵️ Vol **réussi** ! {inter.user.mention} dérobe **{stolen}** à {cible.mention}."

        # 5) Buffs passifs simples (esquive+, reduction, immunite)
        elif typ in ("esquive+", "reduction", "immunite"):
            who = cible or inter.user
            val = float(info.get("valeur", info.get("value", 0.1)) or 0.1)
            dur = int(info.get("duree", info.get("duration", 3600)) or 3600)
            ok = await add_or_refresh_effect(
                user_id=who.id, eff_type=str(typ), value=float(val),
                duration=dur, interval=0,
                source_id=inter.user.id,
                meta_json=json.dumps({"applied_in": inter.channel.id})
            )
            if not ok:
                embed.description = f"⚠️ Effet **{typ}** bloqué sur {who.mention}."
            else:
                labels = {
                    "esquive+": "👟 Esquive+",
                    "reduction": "🪖 Réduction de dégâts",
                    "immunite": "⭐ Immunité",
                }
                pretty = labels.get(typ, typ)
                # pour l’affichage, val peut être un pourcentage (ex: 0.1 → 10%)
                pct = f"{int(round(val * 100))}%" if 0 < val < 1 else str(int(val))
                embed.description = f"{inter.user.mention} applique **{objet}** → {pretty} (**{pct}**, {dur//60} min) sur {who.mention}."

        else:
            embed.description = f"ℹ️ **{objet}** (*{typ}*) n’a pas de logique dédiée ici."

        # MAJ live du classement si présent
        try:
            if inter.guild:
                schedule_lb_update(self.bot, inter.guild.id, "use")
        except Exception:
            pass

        await inter.followup.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(UseCog(bot))

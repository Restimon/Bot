# cogs/use_cog.py
from __future__ import annotations

import random
import time
from typing import List, Optional, Tuple, Dict, Any

import discord
from discord import app_commands
from discord.ext import commands

# ── Inventaire
from inventory_db import (
    get_all_items,
    get_item_qty,
    add_item,
    remove_item,
)

# ── Économie (coins pour la MysteryBox)
from economy_db import add_balance

# ── Effets (buffs / cleanse)
try:
    from effects_db import add_or_refresh_effect, remove_effect
except Exception:
    async def add_or_refresh_effect(*args, **kwargs):  # type: ignore
        return True
    async def remove_effect(*args, **kwargs):  # type: ignore
        return None

# ── Données d’objets + esquive globale
from utils import OBJETS, get_evade_chance

# ── Statut d’esquive temporaire (👟) côté mémoire
try:
    from data import esquive_status
except Exception:
    esquive_status: Dict[str, Dict[str, Dict[str, float]]] = {}

# ── LB live (optionnel)
try:
    from cogs.leaderboard_live import schedule_lb_update
except Exception:
    def schedule_lb_update(*args, **kwargs):
        return


# ==========================================================
# Helpers anti-crash pour l’AUTOCOMPLÉTION
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
        # Fallback : on scrute chaque emoji connu
        for e in OBJETS.keys():
            try:
                q = int(await get_item_qty(uid, e) or 0)
                if q > 0:
                    owned.append((e, q))
            except Exception:
                continue

    # merge + tri
    merged: Dict[str, int] = {}
    for e, q in owned:
        merged[e] = merged.get(e, 0) + int(q)
    return sorted(merged.items(), key=lambda t: t[0])

def _choices_from_owned(
    owned: List[Tuple[str, int]],
    allowed_types: Optional[set],
    current: str
) -> List[app_commands.Choice[str]]:
    cur = (current or "").strip().lower()
    out: List[app_commands.Choice[str]] = []
    for emoji, qty in owned:
        meta = OBJETS.get(emoji) or {}
        typ = str(meta.get("type", ""))
        if allowed_types and typ not in allowed_types:
            continue
        label = meta.get("nom") or meta.get("label") or typ or "objet"
        display = f"{emoji} — {label} (x{qty})"
        if cur and (cur not in emoji and cur not in str(label).lower()):
            continue
        out.append(app_commands.Choice(name=display[:100], value=emoji))
        if len(out) >= 20:
            break
    return out


# ==========================================================
# USE: objets utilitaires uniquement
# ==========================================================
USE_EMOJIS = {"📦", "🔍", "💉", "👟", "🪖", "⭐️"}

async def ac_use_items(inter: discord.Interaction, current: str):
    try:
        if not inter or not inter.user:
            return []
        owned = await _list_owned_items(inter.user.id)

        # types autorisés pour /use
        allowed_types: set[str] = set()
        for e in USE_EMOJIS:
            typ = (OBJETS.get(e) or {}).get("type")
            if typ:
                allowed_types.add(str(typ))

        # propose ce que l’utilisateur possède ET qui correspond aux types
        choices = _choices_from_owned(owned, allowed_types, current)

        # fallback : si rien (meta incomplètes), filtre par emoji connu de USE_EMOJIS
        if not choices:
            owned_use = [(e, q) for (e, q) in owned if e in USE_EMOJIS]
            choices = _choices_from_owned(owned_use, None, current)
        return choices
    except Exception:
        return []  # ne jamais lever → évite “Échec des options de chargement”


def _obj_gif(emoji: str) -> Optional[str]:
    meta = OBJETS.get(emoji, {})
    if meta.get("type") in ("soin", "regen") or emoji == "💉":
        return meta.get("gif_heal") or meta.get("gif")
    return meta.get("gif") or meta.get("gif_attack")


def _weighted_pool_for_box() -> List[str]:
    """
    Pool pondérée (26 - rarete) + entrée spéciale '💰COINS'.
    On autorise tous les types d’objets (attaque/soin/etc.), sauf la box elle-même.
    """
    pool: List[str] = []
    for emoji, data in OBJETS.items():
        if emoji == "📦":
            continue
        r = int(data.get("rarete", 25))
        w = 26 - r
        if w > 0:
            pool.extend([emoji] * w)

    # Coins pseudo-item (~poids 14)
    pool.extend(["💰COINS"] * 14)
    return pool


class UseCog(commands.Cog):
    """Commande /use : 📦 🔍 💉 👟 🪖 ⭐️"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="use", description="Utiliser un objet utilitaire (📦 🔍 💉 👟 🪖 ⭐️).")
    @app_commands.describe(
        objet="Emoji de l'objet",
        cible="Cible (requis pour 🔍 Vol ; ignoré pour les autres)"
    )
    @app_commands.autocomplete(objet=ac_use_items)
    async def use_cmd(self, inter: discord.Interaction, objet: str, cible: Optional[discord.Member] = None):
        if not inter.guild:
            return await inter.response.send_message("❌ À utiliser dans un serveur.", ephemeral=True)

        user = inter.user
        guild = inter.guild

        # vérif possession
        qty = int(await get_item_qty(user.id, objet) or 0)
        if qty <= 0:
            return await inter.response.send_message("❌ Tu n'as pas cet objet.", ephemeral=True)

        # consomme d'abord (évite double-usage)
        if not await remove_item(user.id, objet, 1):
            return await inter.response.send_message("❌ Impossible d'utiliser cet objet.", ephemeral=True)

        title = ""
        lines: List[str] = []
        gif = _obj_gif(objet)

        # ── Dispatcher
        if objet == "📦":
            title = "📦 Mystery Box"
            pool = _weighted_pool_for_box()
            for _ in range(3):
                if not pool:
                    break
                pick = random.choice(pool)
                if pick == "💰COINS":
                    amt = random.randint(15, 25)
                    await add_balance(user.id, amt, "mysterybox")
                    lines.append(f"• 💰 **+{amt}** GotCoins")
                else:
                    await add_item(user.id, pick, 1)
                    lines.append(f"• {pick} **+1**")

        elif objet == "🔍":
            # cible valide
            if (cible is None) or cible.bot or (cible.id == user.id):
                await add_item(user.id, "🔍", 1)  # on rend l’item
                return await inter.response.send_message(
                    "❌ Spécifie une **cible valide** (humaine, différente de toi).",
                    ephemeral=True
                )

            # esquive via utils.get_evade_chance (base 4% modifiable par buffs/passifs)
            evade = float(get_evade_chance(str(guild.id), str(cible.id)))
            if random.random() < max(0.0, min(0.95, evade)):
                title = "🔍 Vol raté"
                lines.append(f"{cible.mention} **esquive** ta tentative ({int(evade*100)}%).")
            else:
                # sac pondéré par les quantités réelles de la cible
                bag: List[str] = []
                try:
                    rows = await get_all_items(cible.id)
                except Exception:
                    rows = []
                for e, q in _safe_item_rows_to_list(rows):
                    bag.extend([e] * q)

                if not bag:
                    title = "🔍 Vol raté"
                    lines.append(f"{cible.mention} n'a **rien** à voler.")
                else:
                    stolen = random.choice(bag)

                    # 🔒 transfert sécurisé : re-check stock → remove cible → add voleur
                    left = int(await get_item_qty(cible.id, stolen) or 0)
                    if left <= 0:
                        title = "🔍 Vol raté"
                        lines.append(f"{cible.mention} n'a **plus** cet objet.")
                    else:
                        ok_rm = await remove_item(cible.id, stolen, 1)
                        if not ok_rm:
                            title = "🔍 Vol raté"
                            lines.append("Le transfert a échoué.")
                        else:
                            await add_item(user.id, stolen, 1)
                            title = "🔍 Vol réussi !"
                            lines.append(f"Tu dérobes **{stolen}** à {cible.mention} !")

        elif objet == "💉":
            title = "💉 Vaccination"
            removed_any = False
            for eff in ("poison", "infection", "virus", "brulure"):
                try:
                    await remove_effect(user.id, eff)
                    removed_any = True
                except Exception:
                    pass
            lines.append("Effets négatifs **retirés**." if removed_any else "Aucun effet négatif détecté.")

        elif objet == "👟":
            title = "👟 Esquive accrue"
            meta = OBJETS.get("👟", {})
            val = float(meta.get("valeur", 0.2))
            dur = int(meta.get("duree", 3 * 3600))
            gid = str(guild.id); uid = str(user.id)
            esquive_status.setdefault(gid, {})[uid] = {"start": time.time(), "duration": dur, "valeur": val}
            lines.append(f"**+{int(val*100)}%** d'esquive pendant **{dur//3600}h**.")

        elif objet == "🪖":
            title = "🪖 Réduction des dégâts"
            meta = OBJETS.get("🪖", {})
            val = float(meta.get("valeur", 0.5))
            dur = int(meta.get("duree", 4 * 3600))
            ok = await add_or_refresh_effect(
                user_id=user.id, eff_type="reduction", value=val,
                duration=dur, interval=0, source_id=user.id, meta_json=None
            )
            lines.append(
                f"Réduction **{int(val*100)}%** pendant **{dur//3600}h**."
                if ok else "Effet **bloqué** (immunité ?)."
            )

        elif objet == "⭐️":
            title = "⭐️ Immunité"
            meta = OBJETS.get("⭐️", {})
            dur = int(meta.get("duree", 2 * 3600))
            ok = await add_or_refresh_effect(
                user_id=user.id, eff_type="immunite", value=1.0,
                duration=dur, interval=0, source_id=user.id, meta_json=None
            )
            lines.append(
                f"**Immunisé** contre les altérations pendant **{dur//3600}h**."
                if ok else "Application **refusée** (déjà actif ?)."
            )

        else:
            title = "Objet non géré"
            lines.append(f"{objet} n’est pas utilisable via /use.")

        # Embed
        embed = discord.Embed(
            title=title or "🎯 Utilisation d'objet",
            description="\n".join(lines) if lines else "\u200b",
            color=discord.Color.blurple()
        )
        if gif:
            embed.set_image(url=gif)

        # MAJ LB
        try:
            schedule_lb_update(self.bot, guild.id, reason=f"use:{objet}")
        except Exception:
            pass

        await inter.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(UseCog(bot))

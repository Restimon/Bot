# cogs/use_cog.py
from __future__ import annotations

import random, time
from typing import List, Optional, Tuple

import discord
from discord import app_commands
from discord.ext import commands

# Inventaire
from inventory_db import get_all_items, get_item_qty, add_item, remove_item
# Économie (coins pour la box)
from economy_db import add_balance

# Effets (optionnels)
try:
    from effects_db import add_or_refresh_effect, remove_effect
except Exception:
    async def add_or_refresh_effect(*args, **kwargs): return True
    async def remove_effect(*args, **kwargs): return None

# Catalogue & esquive
from utils import OBJETS, get_evade_chance

# Buff 👟 en mémoire (utilisé par utils.get_evade_chance)
try:
    from data import esquive_status
except Exception:
    esquive_status = {}

# MAJ classement live (facultatif)
try:
    from cogs.leaderboard_live import schedule_lb_update
except Exception:
    def schedule_lb_update(*args, **kwargs): return

USE_KEYS = {"📦", "🔍", "💉", "👟", "🪖", "⭐️"}

def _item_label(emoji: str) -> str:
    d = OBJETS.get(emoji, {})
    if emoji == "📦": return "📦 • Mystery Box (3 récompenses)"
    if emoji == "🔍": return "🔍 • Vol (vole 1 objet à la cible)"
    if emoji == "💉": return "💉 • Vaccin (retire les debuffs)"
    if emoji == "👟": return f"👟 • Esquive+ (+{int(d.get('valeur',0)*100)}% {int(d.get('duree',0))//3600}h)"
    if emoji == "🪖": return f"🪖 • Réduction ({int(d.get('valeur',0)*100)}% {int(d.get('duree',0))//3600}h)"
    if emoji == "⭐️": return f"⭐️ • Immunité ({int(d.get('duree',0))//3600}h)"
    return f"{emoji}"

async def _ac_use(inter: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
    inv = await get_all_items(inter.user.id)  # [(emoji, qty)] ou similaire
    cur = (current or "").strip().lower()
    out: List[app_commands.Choice[str]] = []
    for emoji, qty in inv:
        if emoji in USE_KEYS and int(qty or 0) > 0:
            label = _item_label(emoji)
            if not cur or cur in label.lower():
                out.append(app_commands.Choice(name=f"{label} ×{qty}", value=emoji))
                if len(out) >= 20: break
    return out

def _gif(emoji: str) -> Optional[str]:
    d = OBJETS.get(emoji, {})
    if d.get("type") in ("soin", "regen") or emoji == "💉":
        return d.get("gif_heal") or d.get("gif")
    return d.get("gif") or d.get("gif_attack")

def _pool_box(exclude_box=True) -> List[str]:
    pool: List[str] = []
    for e, d in OBJETS.items():
        if exclude_box and e == "📦": continue
        w = 26 - int(d.get("rarete", 25))
        if w > 0: pool.extend([e]*w)
    pool.extend(["💰COINS"]*14)  # coins ~ rareté 12
    return pool

async def _box_rewards(user: discord.Member) -> Tuple[str, List[str]]:
    pool = _pool_box(True)
    lines: List[str] = []
    for _ in range(3):
        pick = random.choice(pool)
        if pick == "💰COINS":
            amt = random.randint(15, 25)
            await add_balance(user.id, amt, "mysterybox")
            lines.append(f"💰 **+{amt}** GotCoins")
        else:
            await add_item(user.id, pick, 1)
            lines.append(f"{pick} **+1**")
    return "🎁 Récompenses", lines

class UseCog(commands.Cog):
    """Commande /use : 📦 🔍 💉 👟 🪖 ⭐️"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="use", description="Utiliser 📦 🔍 💉 👟 🪖 ⭐️")
    @app_commands.describe(objet="Emoji de l'objet", cible="Cible (requis pour 🔍)")
    @app_commands.autocomplete(objet=_ac_use)
    async def use_cmd(self, inter: discord.Interaction, objet: str, cible: Optional[discord.Member] = None):
        if not inter.guild:
            return await inter.response.send_message("❌ À utiliser dans un serveur.", ephemeral=True)

        if objet not in USE_KEYS:
            return await inter.response.send_message("❌ Objet non utilisable avec /use.", ephemeral=True)

        # Possession & consommation
        if int(await get_item_qty(inter.user.id, objet) or 0) <= 0:
            return await inter.response.send_message("❌ Tu n'as pas cet objet.", ephemeral=True)
        if not await remove_item(inter.user.id, objet, 1):
            return await inter.response.send_message("❌ Impossible d'utiliser l'objet.", ephemeral=True)

        title = "🎯 Utilisation d'objet"
        desc_lines: List[str] = []
        color = discord.Color.blurple()
        gif = _gif(objet)

        if objet == "📦":
            title = "📦 Mystery Box ouverte !"
            section, rewards = await _box_rewards(inter.user)
            desc_lines.append(f"**{section}**")
            desc_lines += [f"• {r}" for r in rewards]

        elif objet == "🔍":
            # Cible valide ?
            if (cible is None) or cible.bot or cible.id == inter.user.id:
                # Rembourse l'objet
                await add_item(inter.user.id, "🔍", 1)
                return await inter.response.send_message("❌ Spécifie une **cible valide** (humaine, différente de toi).", ephemeral=True)

            evade = float(get_evade_chance(str(inter.guild.id), str(cible.id)))
            if random.random() < max(0.0, min(0.95, evade)):
                title = "🔍 Vol raté"
                desc_lines.append(f"{cible.mention} a **esquivé** ta tentative ({int(evade*100)}%).")
            else:
                # Sac pondéré par le stock RÉEL de la cible
                inv_target = await get_all_items(cible.id)
                bag: List[str] = []
                for e, q in inv_target:
                    q = int(q or 0)
                    if q > 0:
                        bag.extend([e] * q)
                if not bag:
                    title = "🔍 Vol raté"
                    desc_lines.append(f"{cible.mention} n'a **rien** à voler.")
                else:
                    stolen = random.choice(bag)
                    # Retire chez la cible → ajoute au voleur
                    if int(await get_item_qty(cible.id, stolen) or 0) <= 0:
                        title = "🔍 Vol raté"
                        desc_lines.append(f"{cible.mention} n'a **plus** cet objet.")
                    elif not await remove_item(cible.id, stolen, 1):
                        title = "🔍 Vol raté"
                        desc_lines.append("Le transfert a échoué.")
                    else:
                        await add_item(inter.user.id, stolen, 1)
                        title = "🔍 Vol réussi !"
                        desc_lines.append(f"Tu as volé **{stolen}** à {cible.mention} !")

        elif objet == "💉":
            title = "💉 Vaccination"
            removed_any = False
            for eff in ("poison", "infection", "virus", "brulure"):
                try:
                    await remove_effect(inter.user.id, eff)
                    removed_any = True
                except Exception:
                    pass
            desc_lines.append("Effets négatifs **retirés**." if removed_any else "Aucun effet négatif à retirer.")

        elif objet == "👟":
            title = "👟 Esquive accrue"
            d = OBJETS.get("👟", {})
            val = float(d.get("valeur", 0.2)); dur = int(d.get("duree", 3*3600))
            gid = str(inter.guild.id); uid = str(inter.user.id)
            esquive_status.setdefault(gid, {})[uid] = {"start": time.time(), "duration": dur, "valeur": val}
            desc_lines.append(f"**+{int(val*100)}%** d'esquive pendant **{dur//3600}h**.")

        elif objet == "🪖":
            title = "🪖 Réduction des dégâts"
            d = OBJETS.get("🪖", {})
            val = float(d.get("valeur", 0.5)); dur = int(d.get("duree", 4*3600))
            ok = await add_or_refresh_effect(user_id=inter.user.id, eff_type="reduction",
                                             value=val, duration=dur, interval=0,
                                             source_id=inter.user.id, meta_json=None)
            desc_lines.append(
                f"Réduction **{int(val*100)}%** pendant **{dur//3600}h**." if ok else
                "L'effet a été **bloqué** (immunité)."
            )

        elif objet == "⭐️":
            title = "⭐️ Immunité"
            dur = int(OBJETS.get("⭐️", {}).get("duree", 2*3600))
            ok = await add_or_refresh_effect(user_id=inter.user.id, eff_type="immunite",
                                             value=1.0, duration=dur, interval=0,
                                             source_id=inter.user.id, meta_json=None)
            desc_lines.append(
                f"**Immunisé** pendant **{dur//3600}h**." if ok else
                "Application **bloquée** (déjà immunisé ?)."
            )

        embed = discord.Embed(
            title=title,
            description="\n".join(desc_lines) if desc_lines else " ",
            color=color
        )
        if gif: embed.set_image(url=gif)

        try:
            schedule_lb_update(self.bot, inter.guild.id, reason=f"use:{objet}")
        except Exception:
            pass

        await inter.response.send_message(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(UseCog(bot))

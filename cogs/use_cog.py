# cogs/use_cog.py
from __future__ import annotations

import random
import time
from typing import List, Optional, Tuple, Dict

import discord
from discord import app_commands
from discord.ext import commands

# Inventaire (SQLite)
from inventory_db import (
    get_all_items,
    get_item_qty,
    add_item,
    remove_item,
    transfer_item,  # on le garde dispo, mais on sécurise avec remove+add
)

# Économie (coins)
from economy_db import add_balance

# Effets / stats (si présents)
try:
    from effects_db import add_or_refresh_effect, remove_effect
except Exception:
    async def add_or_refresh_effect(*args, **kwargs):  # type: ignore
        return True
    async def remove_effect(*args, **kwargs):  # type: ignore
        return None

# Utils (OBJETS, GIFS fusionnés, get_evade_chance…)
from utils import OBJETS, get_evade_chance

# Esquive buff (👟) stocké côté data.esquive_status
try:
    from data import esquive_status
except Exception:
    esquive_status = {}

# Ping MAJ leaderboard live (optionnel)
try:
    from cogs.leaderboard_live import schedule_lb_update
except Exception:
    def schedule_lb_update(bot, guild_id, reason=""):  # type: ignore
        return

# ─────────────────────────────────────────────────────────
# Autocomplete: seulement les items utilisables que l’utilisateur possède
# ─────────────────────────────────────────────────────────
USE_KEYS = {"📦", "🔍", "💉", "👟", "🪖", "⭐️"}

def _item_label(emoji: str) -> str:
    data = OBJETS.get(emoji, {})
    typ = str(data.get("type", "item"))
    if emoji == "📦":
        return "📦 • Mystery Box (3 récompenses)"
    if emoji == "🔍":
        return "🔍 • Vol (vole 1 objet à la cible)"
    if emoji == "💉":
        return "💉 • Vaccin (retire les debuffs)"
    if emoji == "👟":
        return f"👟 • Esquive+ (+{int(data.get('valeur',0)*100)}% pendant {int(data.get('duree',0))//3600}h)"
    if emoji == "🪖":
        return f"🪖 • Réduction ({int(data.get('valeur',0)*100)}% pendant {int(data.get('duree',0))//3600}h)"
    if emoji == "⭐️":
        return f"⭐️ • Immunité ({int(data.get('duree',0))//3600}h)"
    return f"{emoji} • {typ}"

async def ac_use_items(inter: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
    if not inter.user:
        return []
    user_id = inter.user.id
    inv = await get_all_items(user_id)  # [(emoji, qty)]
    cur = (current or "").strip().lower()
    out: List[app_commands.Choice[str]] = []
    for emoji, qty in inv:
        if emoji not in USE_KEYS:
            continue
        if qty <= 0:
            continue
        name = _item_label(emoji)
        if not cur or cur in name.lower():
            out.append(app_commands.Choice(name=f"{name} ×{qty}", value=emoji))
            if len(out) >= 20:
                break
    return out

# ─────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────
def _obj_gif(emoji: str) -> Optional[str]:
    data = OBJETS.get(emoji, {})
    # heal ou vaccin → gif_heal si présent, sinon gif
    if data.get("type") in ("soin", "regen") or emoji in ("💉",):
        return data.get("gif_heal") or data.get("gif")
    return data.get("gif") or data.get("gif_attack")

def _weighted_pool_for_box(exclude_box: bool = True) -> List[str]:
    """
    Construit une pool pondérée sur 26-rarete pour la MysteryBox.
    - Exclut 📦 si exclude_box=True
    - Ajoute l'option '💰COINS' comme pseudo-item (pondérée comme rarete=12 → poids 14)
    """
    pool: List[str] = []
    for emoji, data in OBJETS.items():
        if exclude_box and emoji == "📦":
            continue
        # Pondération par rareté (on permet tous les types d'objets à drop)
        r = int(data.get("rarete", 25))
        w = 26 - r
        if w <= 0:
            continue
        pool.extend([emoji] * w)

    # Coins comme candidat
    COINS_PSEUDO = "💰COINS"
    coins_r = 12
    pool.extend([COINS_PSEUDO] * (26 - coins_r))  # 14

    return pool

async def _give_box_rewards(bot: commands.Bot, guild: discord.Guild, user: discord.Member) -> Tuple[str, List[str]]:
    """
    Tire 3 récompenses indépendantes:
      - soit des items (ajout inventaire)
      - soit des coins (15 à 25)
    Retourne (title, lines)
    """
    pool = _weighted_pool_for_box(exclude_box=True)
    lines: List[str] = []
    for _ in range(3):
        if not pool:
            break
        pick = random.choice(pool)
        if pick == "💰COINS":
            amt = random.randint(15, 25)
            await add_balance(user.id, amt, "mysterybox")
            lines.append(f"💰 **+{amt}** GotCoins")
        else:
            # Donne 1 exemplaire
            await add_item(user.id, pick, 1)
            lines.append(f"{pick} **+1**")
    return ("🎁 Récompenses", lines)

def _now() -> float:
    return time.time()

# ─────────────────────────────────────────────────────────
# Le Cog
# ─────────────────────────────────────────────────────────
class UseCog(commands.Cog):
    """Commande /use : MysteryBox, Vol, Vaccin, Esquive+, Réduction, Immunité."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="use", description="Utiliser un objet utilitaire (📦 🔍 💉 👟 🪖 ⭐️).")
    @app_commands.describe(
        objet="Emoji de l'objet à utiliser",
        cible="Cible (requis pour 🔍 Vol ; ignoré pour les autres)"
    )
    @app_commands.autocomplete(objet=ac_use_items)
    async def use_cmd(
        self,
        inter: discord.Interaction,
        objet: str,
        cible: Optional[discord.Member] = None
    ):
        if not inter.guild:
            return await inter.response.send_message("❌ À utiliser dans un serveur.", ephemeral=True)

        user = inter.user
        guild = inter.guild

        if objet not in USE_KEYS:
            return await inter.response.send_message("❌ Cet objet ne peut pas être utilisé avec /use.", ephemeral=True)

        # vérif possession
        qty = await get_item_qty(user.id, objet)
        if qty <= 0:
            return await inter.response.send_message("❌ Tu n'as pas cet objet.", ephemeral=True)

        # On consomme l'objet d'abord (évite double-usage si erreurs réseau)
        removed = await remove_item(user.id, objet, 1)
        if not removed:
            return await inter.response.send_message("❌ Impossible d'utiliser cet objet (inventaire inchangé).", ephemeral=True)

        gif = _obj_gif(objet)
        title = ""
        desc_lines: List[str] = []
        color = discord.Color.blurple()

        # Dispatcher
        if objet == "📦":
            # MysteryBox → 3 récompenses
            title = "📦 Mystery Box ouverte !"
            section_title, rewards = await _give_box_rewards(self.bot, guild, user)
            desc_lines.append(f"**{section_title}**")
            for l in rewards:
                desc_lines.append(f"• {l}")

        elif objet == "🔍":
            # Vol → besoin d'une cible
            if (cible is None) or (cible.bot) or (cible.id == user.id):
                # On rend l'objet si param incorrect
                await add_item(user.id, "🔍", 1)
                return await inter.response.send_message("❌ Spécifie une **cible valide** (humaine, différente de toi).", ephemeral=True)

            # Check esquive fixe (mais modifiable par buffs/passifs) → via utils.get_evade_chance
            evade = float(get_evade_chance(str(guild.id), str(cible.id)))
            if random.random() < evade:
                title = "🔍 Vol raté"
                desc_lines.append(f"{cible.mention} a **esquivé** ta tentative ({int(evade*100)}%).")
            else:
                # Construire un sac pondéré par quantités réelles
                inv_target = await get_all_items(cible.id)  # [(emoji, qty)]
                bag: List[str] = []
                for emoji, q in inv_target:
                    if q and q > 0:
                        bag.extend([emoji] * int(q))

                if not bag:
                    title = "🔍 Vol raté"
                    desc_lines.append(f"{cible.mention} n'a **rien** à voler.")
                else:
                    stolen = random.choice(bag)

                    # 🔒 Transfert *sécurisé* : re-vérifie, retire chez la cible, puis ajoute au voleur
                    qty_check = await get_item_qty(cible.id, stolen)
                    if qty_check <= 0:
                        title = "🔍 Vol raté"
                        desc_lines.append(f"{cible.mention} n'a **plus** cet objet.")
                    else:
                        removed_from_target = await remove_item(cible.id, stolen, 1)
                        if not removed_from_target:
                            title = "🔍 Vol raté"
                            desc_lines.append("Le transfert a échoué (stock cible insuffisant).")
                        else:
                            await add_item(user.id, stolen, 1)
                            title = "🔍 Vol réussi !"
                            desc_lines.append(f"Tu as volé **{stolen}** à {cible.mention} !")

        elif objet == "💉":
            # Vaccin → retire effets négatifs
            title = "💉 Vaccination"
            NEG = ("poison", "infection", "virus", "brulure")
            removed_any = False
            for eff in NEG:
                try:
                    await remove_effect(user.id, eff)
                    removed_any = True
                except Exception:
                    pass
            desc_lines.append("Effets négatifs **retirés**." if removed_any else "Aucun effet négatif à retirer.")

        elif objet == "👟":
            # Esquive+ → écrit dans data.esquive_status (lu par utils.get_evade_chance)
            title = "👟 Esquive accrue"
            data = OBJETS.get("👟", {})
            val = float(data.get("valeur", 0.2))
            dur = int(data.get("duree", 3 * 3600))
            gid = str(guild.id); uid = str(user.id)
            esquive_status.setdefault(gid, {})[uid] = {
                "start": time.time(),
                "duration": dur,
                "valeur": val,
            }
            desc_lines.append(f"**+{int(val*100)}%** d'esquive pendant **{dur//3600}h**.")

        elif objet == "🪖":
            # Réduction dégâts (effet durable dans effects_db)
            title = "🪖 Réduction des dégâts"
            data = OBJETS.get("🪖", {})
            val = float(data.get("valeur", 0.5))
            dur = int(data.get("duree", 4 * 3600))
            ok = await add_or_refresh_effect(
                user_id=user.id,
                eff_type="reduction",
                value=val,
                duration=dur,
                interval=0,
                source_id=user.id,
                meta_json=None,
            )
            if ok:
                desc_lines.append(f"Les dégâts subis sont **réduits de {int(val*100)}%** pendant **{dur//3600}h**.")
            else:
                desc_lines.append("L'effet a été **bloqué** par une immunité.")

        elif objet == "⭐️":
            # Immunité (bloque debuffs ; à exploiter dans ton système d'effets/combat)
            title = "⭐️ Immunité"
            data = OBJETS.get("⭐️", {})
            dur = int(data.get("duree", 2 * 3600))
            ok = await add_or_refresh_effect(
                user_id=user.id,
                eff_type="immunite",
                value=1.0,
                duration=dur,
                interval=0,
                source_id=user.id,
                meta_json=None,
            )
            if ok:
                desc_lines.append(f"**Immunisé** contre les altérations pendant **{dur//3600}h**.")
            else:
                desc_lines.append("Application **bloquée** (immunité déjà active ?).")

        # Build embed
        embed = discord.Embed(
            title=title or "🎯 Utilisation d'objet",
            description="\n".join(desc_lines) if desc_lines else discord.utils.escape_markdown(" "),
            color=color
        )
        if gif:
            embed.set_image(url=gif)

        # Réponse + MAJ LB
        try:
            schedule_lb_update(self.bot, guild.id, reason=f"use:{objet}")
        except Exception:
            pass

        await inter.response.send_message(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(UseCog(bot))

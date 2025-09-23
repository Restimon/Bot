# cogs/use_cog.py
from __future__ import annotations

import random
from typing import Dict, Optional, Tuple, List, Union

import discord
from discord import app_commands
from discord.ext import commands

from inventory_db import add_item, remove_item, get_item_qty, get_all_items
from economy_db import add_balance

# Catalogue + GIFs depuis utils.py
try:
    from utils import OBJETS  # type: ignore
except Exception:
    OBJETS: Dict[str, Dict] = {}

# LB live (optionnel)
def _lb_update(bot: commands.Bot, guild_id: Optional[int], reason: str):
    if not guild_id:
        return
    try:
        from cogs.leaderboard_live import schedule_lb_update
        schedule_lb_update(bot, int(guild_id), reason)
    except Exception:
        pass

# ─────────────────────────────────────────────────────────
# Réglages box
# ─────────────────────────────────────────────────────────
BOX_ROLLS = 3                     # 3 tirages
GOLD_MIN, GOLD_MAX = 15, 25       # plage de gold
GOLD_RATIO = 0.25                 # ≈ 25% des tirages tombent sur Gold (pondéré dans le pool)

# ─────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────
def _info(emoji: str) -> Optional[Dict]:
    d = OBJETS.get(emoji)
    return dict(d) if isinstance(d, dict) else None

def _is_box(emoji: str) -> bool:
    return (_info(emoji) or {}).get("type") == "mysterybox"

def _item_weight_from_rarete(emoji: str, info: Dict) -> int:
    """
    Pondération alignée sur utils.get_random_item :
      poids = 26 - rarete   (rarete plus grande => item plus rare)
    Exclusions : type == 'mysterybox'
    """
    if info.get("type") == "mysterybox":
        return 0
    try:
        r = int(info.get("rarete", 25))
    except Exception:
        r = 25
    w = 26 - max(1, min(25, r))
    return max(0, w)

def _build_pool_for_box() -> List[Tuple[str, int]]:
    """
    Construit le pool pondéré pour les tirages de box (hors box).
    [(emoji, poids>0), ...]
    """
    pool: List[Tuple[str, int]] = []
    for e, inf in OBJETS.items():
        if not isinstance(inf, dict):
            continue
        w = _item_weight_from_rarete(e, inf)
        if w > 0:
            pool.append((e, w))
    # retire explicitement les box s'il en reste
    pool = [(e, w) for (e, w) in pool if not _is_box(e)]
    return pool

def _weighted_choice(pool: List[Tuple[str, int]]) -> Optional[str]:
    if not pool:
        return None
    total = sum(w for _, w in pool)
    if total <= 0:
        return None
    r = random.randint(1, total)
    acc = 0
    for e, w in pool:
        acc += w
        if r <= acc:
            return e
    return pool[-1][0]

async def _consume_item(uid: int, emoji: str) -> bool:
    try:
        q = await get_item_qty(uid, emoji)
        if int(q or 0) <= 0:
            return False
        return await remove_item(uid, emoji, 1)
    except Exception:
        return False

def _gif_for(emoji: str) -> Optional[str]:
    try:
        url = (_info(emoji) or {}).get("gif")
        if isinstance(url, str) and url.startswith(("http://", "https://")):
            return url
    except Exception:
        pass
    return None

# ─────────────────────────────────────────────────────────
# Cog
# ─────────────────────────────────────────────────────────
class UseCog(commands.Cog):
    """Utilisation d’objets utilitaires (/use) : mysterybox, vol, buffs génériques."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # — autocomplete : tout le catalogue
    async def _ac_items(self, inter: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        cur = (current or "").lower()
        out: List[app_commands.Choice[str]] = []
        for e, inf in OBJETS.items():
            label = str((inf or {}).get("type", "objet"))
            name = f"{e} • {label}"
            if not cur or cur in name.lower():
                out.append(app_commands.Choice(name=name[:100], value=e))
                if len(out) >= 20:
                    break
        return out

    @app_commands.command(name="use", description="Utiliser un objet utilitaire (box, vol, buffs…).")
    @app_commands.describe(objet="Choisis un objet (ex: 📦 box, 🔍 vol…)", cible="Cible si nécessaire")
    @app_commands.autocomplete(objet=_ac_items)
    async def use(self, inter: discord.Interaction, objet: str, cible: Optional[discord.Member] = None):
        if not inter.guild:
            return await inter.response.send_message("Commande serveur uniquement.", ephemeral=True)

        meta = _info(objet)
        if not meta:
            return await inter.response.send_message("Objet inconnu.", ephemeral=True)

        # On consomme l’objet d’abord
        if not await _consume_item(inter.user.id, objet):
            return await inter.response.send_message(f"Tu n’as pas **{objet}** dans ton inventaire.", ephemeral=True)

        await inter.response.defer(thinking=True)
        typ = str(meta.get("type", ""))

        # ─────────────────────────────
        # 📦 Mysterybox — 3 tirages
        # ─────────────────────────────
        if typ == "mysterybox":
            base_pool = _build_pool_for_box()

            # On ajoute l’option GOLD comme “pseudo item” dans le pool pour que ce soit
            # vraiment “dans les chances” (et pas un tirage séparé).
            # On approxime un poids équivalent à GOLD_RATIO du total courant.
            sum_w = sum(w for _, w in base_pool) or 1
            gold_weight = max(1, int(sum_w * GOLD_RATIO))
            pool_with_gold: List[Tuple[str, int]] = base_pool + [("$GOLD$", gold_weight)]

            results: List[Union[str, Tuple[str, int]]] = []
            total_gold = 0

            for _ in range(BOX_ROLLS):
                pick = _weighted_choice(pool_with_gold)
                if pick == "$GOLD$":
                    amount = random.randint(GOLD_MIN, GOLD_MAX)
                    total_gold += amount
                    results.append(("gold", amount))
                else:
                    # sécurité : évite de tirer une box en résultat
                    if pick is None or _is_box(pick):
                        # fallback simple : retente une fois dans le pool sans gold
                        pick = _weighted_choice(base_pool)
                        if pick is None or _is_box(pick):
                            continue  # rien ce tirage
                    results.append(pick)

            # Appliquer gains
            for r in results:
                if isinstance(r, tuple):
                    continue
                await add_item(inter.user.id, r, 1)

            new_bal = None
            if total_gold > 0:
                new_bal = await add_balance(inter.user.id, total_gold, "box_reward")

            # Embed + GIF
            title = f"{objet} Box ouverte"
            lines = [f"{inter.user.mention} ouvre **{objet}** !", "", "🎁 **Récompenses :**"]
            for r in results:
                if isinstance(r, tuple):
                    _, amt = r
                    lines.append(f"• 💰 **+{amt}** GoldCoins")
                else:
                    lines.append(f"• **{r}**")
            if new_bal is not None:
                lines.append(f"\n💼 Nouveau solde : **{new_bal}** GoldCoins")

            embed = discord.Embed(title=title, description="\n".join(lines), color=discord.Color.gold())
            gif = _gif_for(objet)
            if gif:
                embed.set_image(url=gif)
            await inter.followup.send(embed=embed)

            _lb_update(self.bot, inter.guild.id, "use_box")
            return

        # ─────────────────────────────
        # 🔍 Vol — vole un vrai item à la cible
        # ─────────────────────────────
        if typ == "vol":
            if not isinstance(cible, discord.Member):
                return await inter.followup.send("Il faut une **cible** pour voler.")

            # hook passifs (optionnel)
            try:
                from passifs import trigger as passifs_trigger
            except Exception:
                async def passifs_trigger(*args, **kwargs): return {}

            res = await passifs_trigger("on_theft_attempt", attacker_id=inter.user.id, target_id=cible.id) or {}
            if res.get("blocked"):
                return await inter.followup.send(f"🛡 {cible.mention} est **intouchable** (anti-vol).")

            # 25% de réussite (ajuste si besoin)
            if random.random() >= 0.25:
                embed = discord.Embed(title="Vol", description="🕵️ Vol raté...", color=discord.Color.dark_grey())
                gif = _gif_for(objet)
                if gif:
                    embed.set_image(url=gif)
                await inter.followup.send(embed=embed)
                return

            # items réels possédés par la cible
            inv_rows = await get_all_items(cible.id)
            candidates = [(it, q) for it, q in inv_rows if int(q) > 0]
            if not candidates:
                embed = discord.Embed(
                    title="Vol",
                    description=f"🕵️ Impossible de trouver un objet à voler chez {cible.mention}.",
                    color=discord.Color.dark_grey()
                )
                gif = _gif_for(objet)
                if gif:
                    embed.set_image(url=gif)
                await inter.followup.send(embed=embed)
                return

            # priorité aux non-box
            non_box = [it for it, q in candidates if not _is_box(it)]
            pool = non_box or [it for it, q in candidates]
            stolen = random.choice(pool) if pool else None

            if not stolen:
                embed = discord.Embed(
                    title="Vol",
                    description=f"🕵️ {cible.mention} n’avait rien d’utile à voler…",
                    color=discord.Color.dark_grey()
                )
                gif = _gif_for(objet)
                if gif:
                    embed.set_image(url=gif)
                await inter.followup.send(embed=embed)
                return

            ok = await remove_item(cible.id, stolen, 1)
            if ok:
                await add_item(inter.user.id, stolen, 1)
                embed = discord.Embed(
                    title="Vol réussi",
                    description=f"🕵️ {inter.user.mention} a volé **{stolen}** à {cible.mention} !",
                    color=discord.Color.dark_grey()
                )
            else:
                embed = discord.Embed(
                    title="Vol",
                    description=f"🕵️ {cible.mention} n’avait plus l’objet ciblé…",
                    color=discord.Color.dark_grey()
                )

            gif = _gif_for(objet)
            if gif:
                embed.set_image(url=gif)
            await inter.followup.send(embed=embed)
            _lb_update(self.bot, inter.guild.id, "use_vol")
            return

        # ─────────────────────────────
        # Autres utilitaires (buffs…)
        # ─────────────────────────────
        # Ici on ne traite pas les objets de dégâts/soins/régénération (ils sont gérés par /fight et /heal).
        await inter.followup.send("ℹ️ Cet objet est géré par une autre commande (/heal ou /fight).")


async def setup(bot: commands.Bot):
    await bot.add_cog(UseCog(bot))

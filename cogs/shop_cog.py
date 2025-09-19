# cogs/shop_cog.py
from __future__ import annotations
from typing import Optional, Dict, List
import math
import random

import discord
from discord import app_commands
from discord.ext import commands

# ──────────────────────────────────────────────
# Storage JSON (tickets)
# ──────────────────────────────────────────────
try:
    from data import storage  # type: ignore
except Exception:
    storage = None  # type: ignore

def _add_tickets(gid: int, uid: int, qty: int) -> int:
    """Incrémente les tickets (storage.json). Retourne le nouveau total."""
    if not storage:
        return 0
    if not hasattr(storage, "tickets") or not isinstance(storage.tickets, dict):
        storage.tickets = {}
    gmap = storage.tickets.setdefault(str(gid), {})
    cur = int(gmap.get(str(uid), 0) or 0)
    cur += int(qty or 0)
    gmap[str(uid)] = cur
    try:
        storage.save_data()
    except Exception:
        pass
    return cur

# ──────────────────────────────────────────────
# Catalogue boutique
# ──────────────────────────────────────────────
try:
    from data.shop_catalogue import ITEMS_CATALOGUE, RARETE_SELL_VALUES, CURRENCY_NAME  # type: ignore
except Exception:
    ITEMS_CATALOGUE: Dict[str, Dict] = {}
    RARETE_SELL_VALUES: Dict[object, int] = {}
    CURRENCY_NAME = "GotCoins"

# ──────────────────────────────────────────────
# Monnaie & Inventaire (SQLite)
# ──────────────────────────────────────────────
try:
    from economy_db import get_balance, add_balance  # type: ignore
except Exception:
    async def get_balance(user_id: int) -> int: return 0  # type: ignore
    async def add_balance(user_id: int, delta: int, reason: str = "") -> int: return 0  # type: ignore

try:
    from inventory_db import add_item as inv_add_item, remove_item, get_item_qty  # type: ignore
except Exception:
    inv_add_item = None  # type: ignore
    async def remove_item(user_id: int, emoji: str, qty: int): pass  # type: ignore
    async def get_item_qty(user_id: int, emoji: str) -> int: return 0  # type: ignore

# ──────────────────────────────────────────────
# Objets (définis dans utils.py)
# ──────────────────────────────────────────────
try:
    from utils import OBJETS  # type: ignore
except Exception:
    OBJETS: Dict[str, Dict] = {}

# ──────────────────────────────────────────────
# Passifs (personnage équipé)
# ──────────────────────────────────────────────
try:
    from passifs import trigger, get_equipped_code  # type: ignore
except Exception:
    async def trigger(event: str, **ctx): return {}
    async def get_equipped_code(user_id: int) -> Optional[str]: return None


def _sell_price_for(emoji: str) -> int:
    """
    Prix de revente unitaire d'un emoji, basé sur la rareté (OBJETS[emoji]["rarete"])
    et la table RARETE_SELL_VALUES (clé int ou str). Fallback raisonnable si absent.
    """
    info = OBJETS.get(emoji) or {}
    r = info.get("rarete")
    price: Optional[int] = None
    if r is not None:
        # essaie int puis str
        price = RARETE_SELL_VALUES.get(r) or RARETE_SELL_VALUES.get(str(r))
    if price is None:
        # fallback heuristique par rareté
        try:
            rv = int(r)
        except Exception:
            rv = 10  # indéterminé → milieu de gamme
        if rv <= 3:
            price = 2
        elif rv <= 6:
            price = 4
        elif rv <= 10:
            price = 6
        elif rv <= 18:
            price = 10
        else:
            price = 14
    return max(1, int(price))


class ShopCog(commands.Cog):
    """Boutique GotValis — achat & revente, intégration des passifs."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ──────────────────────────────────────────────
    # /shop — affiche le catalogue
    # ──────────────────────────────────────────────
    @app_commands.command(name="shop", description="Affiche la boutique GotValis.")
    async def shop(self, inter: discord.Interaction):
        await inter.response.defer(thinking=True)

        if not ITEMS_CATALOGUE:
            return await inter.followup.send("❌ La boutique est vide pour le moment.")

        e = discord.Embed(
            title="🛒 Boutique GotValis",
            description=f"Monnaie utilisée : **{CURRENCY_NAME}**",
            color=discord.Color.blurple(),
        )
        for key, it in ITEMS_CATALOGUE.items():
            label = it.get("label", key)
            emoji = it.get("emoji", "•")
            price = int(it.get("price", 0))
            desc = it.get("desc", "")
            e.add_field(
                name=f"{emoji} {label} — {price} {CURRENCY_NAME}",
                value=desc or f"`{key}`",
                inline=False,
            )
        e.set_footer(text="Utilise /buy <item> <quantité> pour acheter, /sell pour revendre.")
        await inter.followup.send(embed=e)

    # ──────────────────────────────────────────────
    # /buy — acheter un item
    # ──────────────────────────────────────────────
    @app_commands.command(name="buy", description="Achète un item de la boutique.")
    @app_commands.describe(item="Clé interne (ex: ticket, snow, fire…)", quantite="Quantité (par défaut 1)")
    async def buy(self, inter: discord.Interaction, item: str, quantite: Optional[int] = 1):
        await inter.response.defer(thinking=True, ephemeral=True)

        key = (item or "").lower().strip()
        it = ITEMS_CATALOGUE.get(key)
        if not it:
            return await inter.followup.send("❌ Cet item n’existe pas dans la boutique.")

        q_req = int(quantite or 1)
        q = max(1, min(q_req, int(it.get("max_per_buy", 20))))
        price_total = int(it.get("price", 0)) * q

        bal = await get_balance(inter.user.id)
        if bal < price_total:
            return await inter.followup.send(
                f"❌ Fonds insuffisants. Il te manque **{price_total - bal} {CURRENCY_NAME}**."
            )

        # Dépense (⚠️ les passifs d'argent NE s'appliquent pas sur une dépense)
        await add_balance(inter.user.id, -price_total, reason=f"shop:{key}x{q}")

        gid = inter.guild.id if inter.guild else 0
        emoji = it.get("emoji", "")
        label = it.get("label", key)

        # Tickets → storage JSON ; sinon → inventaire DB
        if key == "ticket" or emoji == "🎟️":
            total = _add_tickets(gid, inter.user.id, q)
            add_msg = f"🎟️ **{label} ×{q}** (total: {total})"
        else:
            if callable(inv_add_item):
                await inv_add_item(inter.user.id, emoji, q)  # type: ignore
                add_msg = f"{emoji} **{label} ×{q}**"
            else:
                # Fallback data.json (désactivable si tu n'en veux pas)
                try:
                    if storage is not None:
                        inv, _, _ = storage.get_user_data(str(gid), str(inter.user.id))
                        inv.extend([emoji] * q)
                        storage.save_data()
                except Exception:
                    pass
                add_msg = f"{emoji} **{label} ×{q}** (⚠️ inventaire non lié)"

        # Rafraîchir le leaderboard live (solde a changé)
        try:
            from cogs.leaderboard_live import schedule_lb_update  # type: ignore
            if inter.guild:
                schedule_lb_update(self.bot, inter.guild.id, "shop_buy")
        except Exception:
            pass

        await inter.followup.send(
            f"✅ Achat confirmé : {add_msg} pour **{price_total} {CURRENCY_NAME}**."
        )

    # ──────────────────────────────────────────────
    # Autocomplete de /buy item
    # ──────────────────────────────────────────────
    @buy.autocomplete("item")  # type: ignore
    async def autocomplete_item(self, itx: discord.Interaction, current: str):
        cur = (current or "").lower().strip()
        out: List[app_commands.Choice[str]] = []
        for key, it in ITEMS_CATALOGUE.items():
            label = it.get("label", key)
            shown = f"{label} ({key})"
            if not cur or cur in key.lower() or cur in label.lower():
                out.append(app_commands.Choice(name=shown[:100], value=key))
            if len(out) >= 25:
                break
        return out

    # ──────────────────────────────────────────────
    # /sell — revendre un item de ton inventaire
    # Intègre les passifs :
    #  • Vendeur rusé 💰 (shop_sell_bonus) → +25% sur le prix total
    #  • Silien Dorr (plus_un_coin_sur_gains) → +1 coin sur les gains
    # ──────────────────────────────────────────────
    @app_commands.command(name="sell", description="Revendre un objet (par son emoji).")
    @app_commands.describe(objet="Emoji de l'objet (ex: ❄️, 🪓, 🔥, ⚡, 🛡…)", quantite="Quantité à vendre (par défaut 1)")
    async def sell(self, inter: discord.Interaction, objet: str, quantite: Optional[int] = 1):
        await inter.response.defer(thinking=True, ephemeral=True)

        emoji = (objet or "").strip()
        if emoji not in OBJETS:
            return await inter.followup.send("❌ Cet objet n'existe pas (emoji inconnu).")

        q_req = int(quantite or 1)
        q = max(1, q_req)

        owned = await get_item_qty(inter.user.id, emoji)
        if int(owned or 0) < q:
            return await inter.followup.send(f"❌ Quantité insuffisante. Tu possèdes **{owned}** {emoji}.")

        # Prix unitaire par rareté
        unit = _sell_price_for(emoji)
        total = unit * q

        # Passif vendeur rusé 💰 : +25% sur la vente
        code = await get_equipped_code(inter.user.id)
        if code == "shop_sell_bonus":
            total = math.ceil(total * 1.25)

        # Bonus générique d’argent (ex: Silien Dorr +1)
        res = await trigger("on_gain_coins", user_id=inter.user.id, delta=total)
        total += int((res or {}).get("extra", 0))

        # Retirer les items puis créditer
        await remove_item(inter.user.id, emoji, q)
        await add_balance(inter.user.id, total, reason=f"shop_sell:{emoji}x{q}")

        # LB live
        try:
            from cogs.leaderboard_live import schedule_lb_update  # type: ignore
            if inter.guild:
                schedule_lb_update(self.bot, inter.guild.id, "shop_sell")
        except Exception:
            pass

        e = discord.Embed(
            title="♻️ Vente effectuée",
            description=(
                f"{emoji} ×{q} → **{total} {CURRENCY_NAME}**\n"
                f"(prix unitaire: {unit}{' • bonus vendeur rusé' if code=='shop_sell_bonus' else ''})"
            ),
            color=discord.Color.green()
        )
        await inter.followup.send(embed=e)

    # ──────────────────────────────────────────────
    # Autocomplete de /sell objet (propose les emojis connus)
    # ──────────────────────────────────────────────
    @sell.autocomplete("objet")  # type: ignore
    async def autocomplete_sell_obj(self, itx: discord.Interaction, current: str):
        cur = (current or "").strip()
        candidates = list(OBJETS.keys())
        # tri simple : commence par 'cur' en premier
        pref = [e for e in candidates if e.startswith(cur)]
        rest = [e for e in candidates if e not in pref and (not cur or cur in e)]
        lst = (pref + rest)[:25]
        return [app_commands.Choice(name=f"{e}", value=e) for e in lst]


async def setup(bot: commands.Bot):
    await bot.add_cog(ShopCog(bot))

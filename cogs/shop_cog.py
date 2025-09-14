# cogs/shop_cog.py
from __future__ import annotations
import discord
from discord import app_commands
from discord.ext import commands

# stockage inventaire (data.json)
try:
    from data import storage
except Exception:
    storage = None

# catalogue
from data.shop_catalogue import ITEMS_CATALOGUE, RARETE_SELL_VALUES, CURRENCY_NAME

# gestion des GoldValis (SQLite)
try:
    from economy_db import get_balance, add_balance
except Exception:
    async def get_balance(user_id: int) -> int: return 0
    async def add_balance(user_id: int, delta: int, reason: str = "") -> int: return 0


class ShopCog(commands.Cog):
    """Boutique GotValis — achat d’objets (ex: tickets)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ──────────────────────────────────────────────
    # /shop → affiche la boutique
    # ──────────────────────────────────────────────
    @app_commands.command(name="shop", description="Affiche la boutique GotValis.")
    async def shop(self, inter: discord.Interaction):
        await inter.response.defer(thinking=True)

        embed = discord.Embed(
            title="🛒 Boutique GotValis",
            description=f"Monnaie utilisée : **{CURRENCY_NAME}**",
            color=discord.Color.blurple(),
        )

        for key, it in SHOP_ITEMS.items():
            price = it["price"]
            label = it["label"]
            emoji = it["emoji"]
            desc = it.get("desc", "")
            embed.add_field(
                name=f"{emoji} {label} — {price} {CURRENCY_NAME}",
                value=desc or key,
                inline=False,
            )

        embed.set_footer(text="Utilise /buy <item> <quantité> pour acheter.")
        await inter.followup.send(embed=embed)

    # ──────────────────────────────────────────────
    # /buy → achète un item
    # ──────────────────────────────────────────────
    @app_commands.command(name="buy", description="Achète un item de la boutique.")
    @app_commands.describe(item="Nom interne (ex: ticket)", quantite="Quantité (max selon l’item)")
    async def buy(self, inter: discord.Interaction, item: str, quantite: int = 1):
        await inter.response.defer(thinking=True, ephemeral=True)

        key = item.lower().strip()
        if key not in SHOP_ITEMS:
            return await inter.followup.send("❌ Cet item n’existe pas dans la boutique.")

        it = SHOP_ITEMS[key]
        q = max(1, min(int(quantite), it.get("max_per_buy", 10)))
        price_total = it["price"] * q

        bal = await get_balance(inter.user.id)
        if bal < price_total:
            return await inter.followup.send(
                f"❌ Fonds insuffisants. Il te manque **{price_total - bal} {CURRENCY_NAME}**."
            )

        # Débit
        await add_balance(inter.user.id, -price_total, reason=f"shop:{key}x{q}")

        # Ajout inventaire dans data.json
        if storage is not None:
            inv, _, _ = storage.get_user_data(str(inter.guild_id), str(inter.user.id))
            inv.extend([it["emoji"]] * q)
            storage.save_data()

        await inter.followup.send(
            f"✅ Achat confirmé : **{it['emoji']} {it['label']} ×{q}** "
            f"pour **{price_total} {CURRENCY_NAME}**."
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(ShopCog(bot))

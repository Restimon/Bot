# cogs/shop.py
import unicodedata
import discord
from discord import app_commands, Interaction, Embed, Colour
from discord.ext import commands

from data.shop_catalogue import ITEMS_CATALOGUE, RARETE_PRIX_VENTE
from economy_db import get_balance, add_balance
from inventory import add_item, remove_item, get_item_qty
from gacha_db import add_tickets, get_tickets, get_personnage_qty, remove_personnage
import personnage as PERSO

TICKET = "🎟️"

def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return s.lower().strip()

class Shop(commands.Cog):
    """Boutique: achat/vente objets, achat tickets, vente personnages."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ---------- OBJETS ----------
    @app_commands.command(name="buy", description="Acheter un objet du shop (par emoji).")
    @app_commands.describe(emoji="Emoji de l'objet", quantity="Quantité (min 1)")
    async def buy(self, itx: Interaction, emoji: str, quantity: app_commands.Range[int,1,999]=1):
        if emoji not in ITEMS_CATALOGUE:
            return await itx.response.send_message("❌ Objet inconnu dans le shop.", ephemeral=True)
        price = int(ITEMS_CATALOGUE[emoji].get("achat", 0))
        cost = price * quantity

        bal = await get_balance(itx.user.id)
        if bal < cost:
            return await itx.response.send_message(
                f"❌ Solde insuffisant. Prix unitaire **{price}** • Total **{cost}** • Solde **{bal}**.",
                ephemeral=True
            )

        await add_balance(itx.user.id, -cost, "shop_buy_item")
        await add_item(itx.user.id, emoji, quantity)

        emb = Embed(
            title="🛒 Achat confirmé",
            description=f"Tu as acheté **{quantity}× {emoji}** pour **{cost}** GoldValis.",
            colour=Colour.green()
        ).set_footer(text="GotValis • Boutique")
        await itx.response.send_message(embed=emb)

    @app_commands.command(name="sell", description="Vendre un objet de ton inventaire (par emoji).")
    @app_commands.describe(emoji="Emoji de l'objet", quantity="Quantité (min 1)")
    async def sell(self, itx: Interaction, emoji: str, quantity: app_commands.Range[int,1,999]=1):
        if emoji not in ITEMS_CATALOGUE:
            return await itx.response.send_message("❌ Objet inconnu dans le shop.", ephemeral=True)
        have = await get_item_qty(itx.user.id, emoji)
        if have < quantity:
            return await itx.response.send_message(
                f"❌ Tu n’as pas assez de **{emoji}**. (stock: {have})", ephemeral=True
            )
        price = int(ITEMS_CATALOGUE[emoji].get("vente", 0))
        gain = price * quantity

        ok = await remove_item(itx.user.id, emoji, quantity)
        if not ok:
            return await itx.response.send_message("❌ Erreur de stock lors de la vente.", ephemeral=True)
        await add_balance(itx.user.id, gain, "shop_sell_item")

        emb = Embed(
            title="💰 Vente effectuée",
            description=f"Tu as vendu **{quantity}× {emoji}** pour **{gain}** GoldValis.",
            colour=Colour.gold()
        ).set_footer(text="GotValis • Boutique")
        await itx.response.send_message(embed=emb)

    # ---------- TICKETS ----------
    @app_commands.command(name="buy_ticket", description="Acheter un ou plusieurs tickets de tirage.")
    @app_commands.describe(quantity="Nombre de tickets (min 1)")
    async def buy_ticket(self, itx: Interaction, quantity: app_commands.Range[int,1,100]=1):
        price = int(ITEMS_CATALOGUE.get(TICKET, {}).get("achat", 200))
        total_cost = price * quantity

        bal = await get_balance(itx.user.id)
        if bal < total_cost:
            return await itx.response.send_message(
                f"❌ Solde insuffisant. Ticket={price} • Total **{total_cost}** • Solde **{bal}**.",
                ephemeral=True
            )

        await add_balance(itx.user.id, -total_cost, "shop_buy_ticket")
        await add_tickets(itx.user.id, quantity)
        new_t = await get_tickets(itx.user.id)

        emb = Embed(
            title="🎟️ Achat de tickets",
            description=f"Tu as acheté **{quantity}** ticket(s). Tickets maintenant : **{new_t}**.",
            colour=Colour.green()
        ).set_footer(text="GotValis • Boutique")
        await itx.response.send_message(embed=emb)

    # ---------- PERSONNAGES (vente uniquement) ----------
    @app_commands.command(name="sell_character", description="Vendre un personnage gacha de ta collection.")
    @app_commands.describe(nom="Nom (ou slug) du personnage", quantity="Quantité à vendre (min 1)")
    async def sell_character(self, itx: Interaction, nom: str, quantity: app_commands.Range[int,1,50]=1):
        p = PERSO.trouver(nom)
        if not p:
            return await itx.response.send_message("❌ Personnage introuvable.", ephemeral=True)

        rarete = p.get("rarete","Commun")
        key = _norm(rarete)  # commun/rare/epique/legendaire
        unit = int(RARETE_PRIX_VENTE.get(key, 0))
        if unit <= 0:
            return await itx.response.send_message("❌ Ce personnage ne peut pas être vendu.", ephemeral=True)

        have = await get_personnage_qty(itx.user.id, p["nom"])
        if have < quantity:
            return await itx.response.send_message(
                f"❌ Tu possèdes seulement **{have}× {p['nom']}**.", ephemeral=True
            )

        ok = await remove_personnage(itx.user.id, p["nom"], quantity)
        if not ok:
            return await itx.response.send_message("❌ Erreur lors de la vente.", ephemeral=True)

        gain = unit * quantity
        await add_balance(itx.user.id, gain, "shop_sell_character")

        emb = Embed(
            title="📤 Vente de personnage",
            description=f"Tu as vendu **{quantity}× {p['nom']}** ({rarete}) pour **{gain}** GoldValis.",
            colour=Colour.gold()
        ).set_footer(text="GotValis • Boutique")
        await itx.response.send_message(embed=emb)

async def setup(bot: commands.Bot):
    await bot.add_cog(Shop(bot))

# cogs/daily.py
import random
from typing import List

import discord
from discord import app_commands, Embed, Colour, Interaction
from discord.ext import commands

from data.items import OBJETS
from gacha_db import init_gacha_db, add_tickets, get_tickets
from inventory import init_inventory_db, add_item
from economy_db import init_economy_db, add_balance

# ------- utils -------

RARITY_EXP = 1.0  # poids = 1 / (rarete ** RARITY_EXP)

def _weighted_pick(exclude: set[str] | None = None) -> str:
    """Tire 1 emoji d'OBJETS pondéré à l'inverse de la 'rarete'."""
    exclude = exclude or set()
    emojis: List[str] = []
    weights: List[float] = []
    for e, data in OBJETS.items():
        if e in exclude:
            continue
        r = max(1, int(data.get("rarete", 1)))
        emojis.append(e)
        weights.append(1.0 / (r ** RARITY_EXP))
    return random.choices(emojis, weights=weights, k=1)[0]

def _pick_items_pattern() -> list[tuple[str, int]]:
    """
    Retourne la liste [(emoji, qty), ...] selon l'un des 3 schémas :
    A) 1 item ×3
    B) 2 items (×1 et ×2)
    C) 3 items ×1
    Les items sont distincts quand il y en a plusieurs.
    """
    roll = random.choice(("A", "B", "C"))
    taken: set[str] = set()

    if roll == "A":
        e = _weighted_pick()
        return [(e, 3)]

    if roll == "B":
        e1 = _weighted_pick()
        taken.add(e1)
        e2 = _weighted_pick(exclude=taken)
        # 50/50 pour savoir lequel a ×2
        if random.random() < 0.5:
            return [(e1, 2), (e2, 1)]
        else:
            return [(e1, 1), (e2, 2)]

    # "C"
    e1 = _weighted_pick()
    taken.add(e1)
    e2 = _weighted_pick(exclude=taken)
    taken.add(e2)
    e3 = _weighted_pick(exclude=taken)
    return [(e1, 1), (e2, 1), (e3, 1)]

def _fmt_items_lines(pairs: list[tuple[str, int]]) -> str:
    return "\n".join(f"{e} ×{q}" for e, q in pairs)

# ------- Cog -------

class Daily(commands.Cog):
    """Daily: 1 ticket gratuit + items (pattern aléatoire) + GoldValis."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        # on s'assure que les DB sont prêtes
        await init_gacha_db()
        await init_inventory_db()
        await init_economy_db()

    @app_commands.command(
        name="daily",
        description="Réclame ton daily : 1 ticket + items aléatoires + GoldValis."
    )
    async def daily(self, itx: Interaction):
        user = itx.user

        # 1) Donne 1 ticket
        await add_tickets(user.id, 1)
        total_tickets = await get_tickets(user.id)

        # 2) Donne items selon un schéma
        items = _pick_items_pattern()
        for emoji, qty in items:
            await add_item(user.id, emoji, qty)

        # 3) Donne des coins
        coins = random.randint(10, 100)
        await add_balance(user.id, coins, "daily_reward")

        # Embed récap
        emb = Embed(
            title="🎁 Daily récupéré",
            colour=Colour.blurple(),
            description=(
                f"🎟️ Ticket : **+1** *(total {total_tickets})*\n"
                f"📦 Objets :\n{_fmt_items_lines(items)}\n"
                f"💰 GoldValis : **+{coins}**"
            )
        )
        emb.set_footer(text="GotValis • Daily")
        await itx.response.send_message(embed=emb)

async def setup(bot: commands.Bot):
    await bot.add_cog(Daily(bot))

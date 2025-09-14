# cogs/gacha_cog.py
from __future__ import annotations

import random
from collections import Counter
from typing import Dict, Tuple, List, Optional

import discord
from discord import app_commands
from discord.ext import commands

# --- Dépendances souples (pas de gacha_db !) ---
try:
    from data import storage  # doit fournir get_user_data(gid, uid) et save_data()
except Exception:
    storage = None

try:
    from economy_db import add_balance, get_balance  # SQLite
except Exception:
    # Fallback no-op si pas dispo
    async def add_balance(user_id: int, delta: int, reason: str = "") -> int:
        return 0
    async def get_balance(user_id: int) -> int:
        return 0

try:
    from utils import get_random_item, OBJETS
except Exception:
    # Fallback simpliste
    def get_random_item(debug: bool = False):
        return random.choice(["🍀", "❄️", "🧪", "🩹", "💊", "💰"])
    OBJETS = {}

# -------------------- Réglages --------------------
MAX_ROLLS = 10
GOLD_COST_PER_ROLL = 100  # coût d’1 tirage en or
TICKET_COST_PER_ROLL = 1  # coût d’1 tirage en tickets
COIN_REWARD_RANGE = (100, 150)  # si le tirage donne "💰"
EMBED_COLOR = discord.Color.gold()

# -------------------- Tickets helpers --------------------
def _ensure_ticket_buckets():
    """Crée les seaux de tickets si absents dans storage."""
    if storage is None:
        return
    data = storage.data
    data.setdefault("tickets", {})

def _get_tickets(guild_id: str, user_id: str) -> int:
    if storage is None:
        return 0
    _ensure_ticket_buckets()
    gid = str(guild_id); uid = str(user_id)
    return int(storage.data["tickets"].get(gid, {}).get(uid, 0))

def _add_tickets(guild_id: str, user_id: str, delta: int) -> int:
    if storage is None:
        return 0
    _ensure_ticket_buckets()
    gid = str(guild_id); uid = str(user_id)
    bucket = storage.data["tickets"].setdefault(gid, {})
    bucket[uid] = int(bucket.get(uid, 0)) + int(delta)
    if bucket[uid] < 0:
        bucket[uid] = 0
    return bucket[uid]

# -------------------- Inventaire helper --------------------
def _give_item_to_inventory(guild_id: str, user_id: str, emoji: str, qty: int = 1):
    """Ajoute l’item (emoji) dans l’inventaire listé par storage.get_user_data."""
    if storage is None:
        return
    inv, _, _ = storage.get_user_data(str(guild_id), str(user_id))
    for _ in range(max(1, qty)):
        inv.append(emoji)

# -------------------- Résolution d’un tirage --------------------
async def _resolve_single_roll(guild_id: int, user_id: int) -> Tuple[str, Optional[int]]:
    """
    Renvoie (emoji, gold_gain).
    - Si l’emoji == '💰' → gold_gain ∈ [COIN_REWARD_RANGE].
    - Sinon gold_gain = None et l’emoji est ajouté à l’inventaire par le caller.
    """
    emoji = get_random_item(debug=False)
    if emoji == "💰":
        gain = random.randint(*COIN_REWARD_RANGE)
        await add_balance(user_id, gain, reason="Gacha: pièce")
        return emoji, gain
    else:
        _give_item_to_inventory(guild_id, user_id, emoji, qty=1)
        return emoji, None

# -------------------- Cog --------------------
class Gacha(commands.Cog):
    """Tirage Gacha GotValis™ — tickets ou or. 1 récompense par tirage, pondérée par la rareté (utils.OBJETS)."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="gacha", description="Effectue des tirages (tickets ou or).")
    @app_commands.describe(
        quantite="Nombre de tirages (1-10).",
        mode="auto (par défaut), ticket, ou gold."
    )
    @app_commands.choices(
        mode=[
            app_commands.Choice(name="auto", value="auto"),
            app_commands.Choice(name="ticket", value="ticket"),
            app_commands.Choice(name="gold", value="gold"),
        ]
    )
    async def gacha_slash(self, interaction: discord.Interaction, quantite: int = 1, mode: Optional[app_commands.Choice[str]] = None):
        if not interaction.guild:
            return await interaction.response.send_message("Utilise cette commande dans un serveur.", ephemeral=True)

        quantite = max(1, min(MAX_ROLLS, int(quantite)))
        mode_val = (mode.value if mode else "auto").lower()

        gid = interaction.guild.id
        uid = interaction.user.id

        # Détermination du paiement
        tickets_avail = _get_tickets(gid, uid)
        use_tickets = False
        if mode_val == "ticket":
            use_tickets = True
        elif mode_val == "gold":
            use_tickets = False
        else:  # auto
            use_tickets = tickets_avail >= quantite

        # Vérifs des ressources
        if use_tickets:
            if tickets_avail < quantite:
                return await interaction.response.send_message(
                    f"🎟️ Tu n’as pas assez de tickets ({tickets_avail}/{quantite}).", ephemeral=True
                )
        else:
            # paiement en or
            bal = await get_balance(uid)
            need = quantite * GOLD_COST_PER_ROLL
            if bal < need:
                return await interaction.response.send_message(
                    f"💰 Solde insuffisant ({bal}/{need}). Utilise des tickets ou gagne de l’or.", ephemeral=True
                )

        # Débit
        if use_tickets:
            _add_tickets(gid, uid, -quantite)
        else:
            await add_balance(uid, -quantite * GOLD_COST_PER_ROLL, reason="Gacha: achat tirage")

        await interaction.response.defer(thinking=True)

        # Tirages
        results: List[Tuple[str, Optional[int]]] = []
        coins_total = 0
        for _ in range(quantite):
            emoji, gold_gain = await _resolve_single_roll(gid, uid)
            results.append((emoji, gold_gain))
            if gold_gain:
                coins_total += gold_gain

        # Persist
        if storage is not None:
            storage.save_data()

        # Résumé
        # Compte les items (hors 💰)
        item_counts = Counter([e for e, g in results if e != "💰"])
        coin_hits = [g for e, g in results if e == "💰" and g]

        # Texte de loot
        lines = []
        if item_counts:
            for emoji, cnt in item_counts.most_common():
                suffix = f" ×{cnt}" if cnt > 1 else ""
                lines.append(f"{emoji}{suffix}")
        if coin_hits:
            # on détaille un total + mention si plusieurs hits
            hits = len(coin_hits)
            total = sum(coin_hits)
            if hits == 1:
                lines.append(f"💰 +{total} or")
            else:
                lines.append(f"💰 +{total} or (x{hits})")

        if not lines:
            lines = ["(rien ?) étrange…"]

        mode_label = "🎟️ Tickets" if use_tickets else "💰 Or"
        paid = f"{quantite}× {('ticket' if use_tickets else f'{GOLD_COST_PER_ROLL} or')}"
        embed = discord.Embed(
            title="🎰 Tirage Gacha — GotValis™",
            description=f"Paiement: **{mode_label}** — coût: **{paid}**",
            color=EMBED_COLOR
        )
        embed.add_field(name="Récompenses", value="\n".join(f"• {l}" for l in lines), inline=False)

        await interaction.followup.send(embed=embed)

# --- setup() pour extensions ---
async def setup(bot: commands.Bot):
    await bot.add_cog(Gacha(bot))

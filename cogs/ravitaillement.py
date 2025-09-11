# cogs/supply.py
import asyncio
import random
import time
from typing import Dict, List, Set

import discord
from discord import app_commands, Colour, Embed, Interaction
from discord.ext import commands

# ← ADAPTE SI TON CHEMIN DIFFÈRE
from data.items import OBJETS, GIFS
from inventory import init_inventory_db, add_item, get_item_qty

# ---------------- Réglages gameplay ----------------
MIN_MSGS = 10             # minimum de messages avant un drop
MAX_MSGS = 30             # maximum de messages avant un drop
CLAIM_WINDOW = 30         # secondes pour cliquer la réaction
MAX_WINNERS = 4           # nombre max de gagnants
RARITY_EXP = 1.0          # poids = 1 / (rarete ** RARITY_EXP)

# ---------------- Anti-spam ----------------
MIN_MSG_LEN = 4           # messages trop courts ignorés (à moins d’un fichier joint)
PER_USER_COOLDOWN = 8     # secondes avant que le même user recompte pour la jauge

# ---------------- Utilitaires ----------------
def _weighted_choice_from_objets() -> str:
    """
    Tire un emoji d'item pondéré à l'inverse de sa rareté :
    poids = 1 / (rarete ** RARITY_EXP). Plus "rarete" est grande => moins de chance.
    """
    emojis: List[str] = []
    weights: List[float] = []
    for emoji, data in OBJETS.items():
        r = max(1, int(data.get("rarete", 1)))
        w = 1.0 / (r ** RARITY_EXP)
        emojis.append(emoji)
        weights.append(w)
    return random.choices(emojis, weights=weights, k=1)[0]


class _ChannelState:
    __slots__ = ("count", "target", "last_counts_by_user", "dropping")

    def __init__(self):
        self.count = 0
        self.target = random.randint(MIN_MSGS, MAX_MSGS)
        self.last_counts_by_user: Dict[int, float] = {}
        self.dropping = False


class Supply(commands.Cog):
    """Système de ravitaillement par messages."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.states: Dict[int, _ChannelState] = {}

    # ---------- Lifecycle ----------
    async def cog_load(self) -> None:
        await init_inventory_db()

    # ---------- Helpers ----------
    def _state(self, channel_id: int) -> _ChannelState:
        st = self.states.get(channel_id)
        if not st:
            st = _ChannelState()
            self.states[channel_id] = st
        return st

    def _contributes(self, message: discord.Message) -> bool:
        """Renvoie True si le message doit compter pour la jauge (anti-spam basique)."""
        if message.author.bot:
            return False
        if message.type != discord.MessageType.default:
            return False

        content = (message.content or "").strip()

        # ignore slash/commands textuelles
        if content.startswith("/"):
            return False

        # taille minimale (sauf si pièces jointes)
        if len(content) < MIN_MSG_LEN and not message.attachments:
            return False

        # anti flood par user
        st = self._state(message.channel.id)
        now = time.time()
        last = st.last_counts_by_user.get(message.author.id, 0.0)
        if now - last < PER_USER_COOLDOWN:
            return False
        st.last_counts_by_user[message.author.id] = now

        return True

    # ---------- Listener messages ----------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # nécessite intents.message_content = True côté main.py
        if not message.guild:
            return
        if not isinstance(message.channel, discord.abc.Messageable):
            return
        if not self._contributes(message):
            return

        st = self._state(message.channel.id)
        st.count += 1

        if st.count >= st.target and not st.dropping:
            # évite chevauchement de drops dans le même canal
            st.dropping = True
            asyncio.create_task(self._start_drop(message.channel))

    # ---------- Logique d’un drop ----------
    async def _start_drop(self, channel: discord.abc.Messageable):
        st = self._state(channel.id)
        st.count = 0
        st.target = random.randint(MIN_MSGS, MAX_MSGS)

        emoji = _weighted_choice_from_objets()
        item_data = OBJETS[emoji]
        gif = GIFS.get(emoji)

        # Annonce initiale
        title = "📦 Ravitaillement !"
        desc = (
            f"Réagissez avec {emoji} pour récupérer **l'objet** "
            f"(type: `{item_data.get('type', 'inconnu')}` – rareté `{item_data.get('rarete')}`)\n"
            f"Seuls les **{MAX_WINNERS} premiers** gagnent.\n"
            f"⏱️ Vous avez **{CLAIM_WINDOW} secondes**."
        )
        embed = Embed(title=title, description=desc, colour=Colour.dark_theme())
        embed.set_footer(text="GotValis • Ravitaillement")
        if gif:
            embed.set_image(url=gif)

        msg: discord.Message = await channel.send(embed=embed)

        try:
            await msg.add_reaction(emoji)
        except discord.HTTPException:
            # Fallback si l’emoji ne peut pas être ajouté en réaction (très rare pour Unicode)
            emoji = "✅"
            await msg.add_reaction(emoji)

        winners: List[int] = []
        seen: Set[int] = set()
        end_at = time.time() + CLAIM_WINDOW

        def check(payload: discord.RawReactionActionEvent) -> bool:
            if payload.message_id != msg.id:
                return False
            if str(payload.emoji) != emoji:
                return False
            if payload.user_id == self.bot.user.id:
                return False
            if payload.user_id in seen:
                return False
            return True

        while len(winners) < MAX_WINNERS and time.time() < end_at:
            try:
                payload: discord.RawReactionActionEvent = await self.bot.wait_for(
                    "raw_reaction_add",
                    timeout=max(0.1, end_at - time.time())
                )
            except asyncio.TimeoutError:
                break

            if check(payload):
                winners.append(payload.user_id)
                seen.add(payload.user_id)

        await self._finalize_drop(msg, emoji, winners)
        st.dropping = False

    async def _finalize_drop(self, msg: discord.Message, emoji: str, winners: List[int]):
        # Distribution en base
        for uid in winners:
            await add_item(uid, emoji, 1)

        # Embed final (style SomniCorp)
        if winners:
            desc = (
                f"Le dépôt de **SomniCorp** contenant {emoji} a été récupéré par :\n\n"
                + "\n".join(f"✅ <@{uid}>" for uid in winners)
            )
            colour = Colour.dark_green()
        else:
            desc = f"Le dépôt de **SomniCorp** contenant {emoji} n'a été récupéré par personne."
            colour = Colour.dark_grey()

        final = Embed(
            title="📦 Ravitaillement récupéré",
            description=desc,
            colour=colour
        )
        final.set_footer(text="GotValis • Ravitaillement")
        gif = GIFS.get(emoji)
        if gif:
            final.set_image(url=gif)

        try:
            await msg.edit(embed=final)
        except discord.HTTPException:
            await msg.channel.send(embed=final)

    # ---------- Commandes utiles ----------
    @app_commands.command(name="force_drop", description="(Admin) Force un ravitaillement dans ce canal.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def force_drop(self, itx: Interaction):
        await itx.response.send_message("Ok, j’ouvre un ravitaillement…", ephemeral=True)
        await self._start_drop(itx.channel)

    @app_commands.command(name="inventory", description="Affiche ton inventaire d’objets de ravitaillement.")
    async def inventory(self, itx: Interaction, user: discord.User | None = None):
        target = user or itx.user

        # Récupère toutes les clés d’items connues (les emojis d'OBJETS)
        lines: List[str] = []
        total = 0
        for emoji in OBJETS.keys():
            qty = await get_item_qty(target.id, emoji)
            if qty > 0:
                total += qty
                lines.append(f"{emoji} × **{qty}**")

        if not lines:
            desc = f"{target.mention} n’a encore aucun objet."
        else:
            desc = "\n".join(lines)

        embed = Embed(
            title=f"Inventaire de {target.display_name}",
            description=desc,
            colour=Colour.blurple()
        )
        embed.set_footer(text=f"Total: {total} objet(s)")
        await itx.response.send_message(embed=embed, ephemeral=(target.id == itx.user.id))


async def setup(bot: commands.Bot):
    await bot.add_cog(Supply(bot))

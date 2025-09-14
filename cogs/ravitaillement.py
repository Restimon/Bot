# cogs/ravitaillement.py
import random
import asyncio
from typing import List

import discord
from discord.ext import commands

from utils import get_random_item, give_random_item  # tirage pondéré + ajout objet
from data import storage  # pour coins via get_user_data / set_user_data

BOX_EMOJI = "📦"

class Ravitaillement(commands.Cog):
    """
    Déploie automatiquement une caisse après un nombre de messages aléatoire (12–30).
    - La caisse est posée comme RÉACTION 📦 directement sous le message déclencheur.
    - Les joueurs cliquent pendant 30s.
    - À l’issue : on attribue les gains et on envoie un embed récap « 📦 Ravitaillement récupéré ».
    - Tant qu’un drop est en cours, aucun nouveau ne peut pop.
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.drop_pending: bool = False
        self.msg_since_last: int = 0
        self._roll_new_target()

    # ----------------------------
    # Compteur de messages
    # ----------------------------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # on ignore les bots et les DM
        if message.author.bot or not message.guild:
            return

        # si un drop est en cours, on n’augmente pas le compteur
        if self.drop_pending:
            return

        self.msg_since_last += 1
        if self.msg_since_last >= self.target_msg_count:
            # réinitialise tout de suite pour le prochain cycle
            self.msg_since_last = 0
            self._roll_new_target()
            await self._spawn_on_message(message)

    def _roll_new_target(self):
        # nouveau seuil aléatoire entre 12 et 30
        self.target_msg_count = random.randint(12, 30)

    # ----------------------------
    # Déploiement de la boîte
    # ----------------------------
    async def _spawn_on_message(self, message: discord.Message):
        """Pose la 📦 en réaction sous le message 'message', attend 30s, récap & récompenses."""
        if self.drop_pending:
            return
        self.drop_pending = True

        try:
            # Ajoute la réaction 📦 au message déclencheur
            await message.add_reaction(BOX_EMOJI)

            # Fenêtre de 30 secondes
            await asyncio.sleep(30)

            # On relit le message pour récupérer les réactions réelles
            fresh_msg = await message.channel.fetch_message(message.id)

            claimers: List[discord.Member] = []
            for r in fresh_msg.reactions:
                if str(r.emoji) == BOX_EMOJI:
                    # récupère tous les users (async iterator)
                    users = [u async for u in r.users() if not u.bot]
                    # map -> Member si possible, sinon garde User
                    for u in users:
                        m = message.guild.get_member(u.id)
                        claimers.append(m or u)
                    break  # une seule réaction nous intéresse

            # Attribution des récompenses au moment du récap
            lines = []
            for user in claimers:
                reward = get_random_item()  # "💰" ou un emoji d'objet
                gid = str(message.guild.id)
                uid = str(user.id)

                if reward == "💰":
                    # Ajoute 5–15 GoldValis
                    inv, coins, perso = storage.get_user_data(gid, uid)
                    delta = random.randint(5, 15)
                    coins += delta
                    storage.set_user_data(gid, uid, inv, coins, perso)
                    lines.append(f"✅ {user.mention} a récupéré : 💰 **{delta} GoldValis**")
                else:
                    # Objet : on l'ajoute dans l'inventaire
                    give_random_item(gid, uid, reward)
                    lines.append(f"✅ {user.mention} a récupéré : {reward}")

            # Embed récap
            if lines:
                recap = discord.Embed(
                    title="📦 Ravitaillement récupéré",
                    color=discord.Color.green(),
                    description="\n".join(lines),
                )
                await message.channel.send(embed=recap)
            else:
                # Personne n’a cliqué
                await message.channel.send("📦 Ravitaillement récupéré — personne n’a réclamé la caisse.")

        finally:
            # libère le verrou pour permettre un prochain drop
            self.drop_pending = False

# ----------------------------
# Hook d’extension
# ----------------------------
async def setup(bot: commands.Bot):
    await bot.add_cog(Ravitaillement(bot))

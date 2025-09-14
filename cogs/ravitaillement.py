# cogs/ravitaillement.py
from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass, field
from typing import Dict, Set, Optional, Tuple, List

import discord
from discord.ext import commands

# === Dépendances projet ===
# utils.get_random_item() tire un emoji d'objet selon ta rareté.
from utils import get_random_item

# Inventaire persistant (data.json) : on ajoute les loots à la fin
try:
    from data.storage import get_user_data, save_data  # type: ignore
except Exception:
    # Fallback doux si storage n’est pas prêt dans l’environnement
    def get_user_data(guild_id: str, user_id: str):
        # Retourne (inventory_list, hp, personnage_dict_or_None)
        return ([], 100, None)
    def save_data():
        return

BOX_EMOJI = "📦"

# Bornes du compteur automatique (inclusives)
MIN_MSG = 12
MAX_MSG = 30

# Fenêtre de récupération en secondes
CLAIM_WINDOW = 30

# ------------------------------------------------------------
# État interne par serveur
# ------------------------------------------------------------
@dataclass
class GuildRavitailState:
    # comptage auto (seulement si le bot PEUT réagir dans le salon)
    msg_target: Optional[int] = None      # seuil de messages pour le prochain drop
    msg_count: int = 0                    # compteur courant
    last_channel_id: Optional[int] = None # dernier salon éligible où on a compté

    # drop en cours
    active: bool = False
    drop_channel_id: Optional[int] = None
    drop_message_id: Optional[int] = None
    drop_starter_msg_id: Optional[int] = None  # l'ID du message SOUS lequel on a posé 📦
    participants: Set[int] = field(default_factory=set)
    started_at: float = 0.0

# guild_id (int) -> state
_STATES: Dict[int, GuildRavitailState] = {}

# ------------------------------------------------------------
# Helpers de permissions
# ------------------------------------------------------------
def _can_react(channel: discord.abc.GuildChannel, me: discord.Member) -> bool:
    """
    True si le bot peut compter ET poser 📦 dans ce salon :
    - Voir messages (read_messages)
    - Envoyer (send_messages) (pour le récap)
    - Ajouter des réactions (add_reactions)
    - Lire l'historique (read_message_history) (souvent requis pour réagir sur un msg)
    """
    try:
        perms = channel.permissions_for(me)
        return (
            perms.read_messages
            and perms.send_messages
            and perms.add_reactions
            and perms.read_message_history
        )
    except Exception:
        return False

def _is_text_like(channel: discord.abc.GuildChannel) -> bool:
    """Autorise TextChannel, Thread, ForumChannel (post)."""
    return isinstance(channel, (discord.TextChannel, discord.Thread, discord.ForumChannel))

# ------------------------------------------------------------
# Le Cog
# ------------------------------------------------------------
class RavitaillementCog(commands.Cog):
    """
    Auto-drop après 12 à 30 messages (aléatoire), mais
    - On compte UNIQUEMENT les messages dans les salons où le bot peut poser une réaction.
    - Une seule boîte active à la fois par serveur.
    - 30s pour cliquer 📦 ; sinon “Ravitaillement détruit”.
    - Les loots sont attribués à la fin (et sauvegardés).
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ---------------------------
    # Listener messages
    # ---------------------------
    @commands.Cog.listener()
    async def on_message(self, msg: discord.Message):
        # ignorer les bots
        if msg.author.bot:
            return
        # pas de serveur (DM)
        if not msg.guild:
            return
        # on ne compte que dans des salons textuels
        channel = msg.channel
        if not _is_text_like(channel):
            return

        # vérifier les permissions de réaction dans CE salon
        me = msg.guild.me
        if not me or not _can_react(channel, me):
            # 🔴 Pas les perms → ne pas compter dans ce salon
            return

        gid = msg.guild.id
        state = _STATES.setdefault(gid, GuildRavitailState())

        # si drop actif → on ne lance pas un autre ; on ignore le comptage tant que c'est actif
        if state.active:
            return

        # initialiser la cible si besoin
        if state.msg_target is None:
            state.msg_target = random.randint(MIN_MSG, MAX_MSG)
            state.msg_count = 0
            state.last_channel_id = channel.id

        # si on change de salon, on met quand même à jour last_channel_id (on compte cross-channels
        # tant que le bot a les perms — mais seulement dans les salons réactifs)
        state.last_channel_id = channel.id

        # incrémenter
        state.msg_count += 1

        # seuil atteint ? → on drop SOUS CE message
        if state.msg_count >= int(state.msg_target or MAX_MSG):
            await self._spawn_box_under_message(msg)
            # reset du compteur pour le prochain cycle (après fin du drop on re-choisira une cible)
            state.msg_target = None
            state.msg_count = 0

    # ---------------------------
    # Spawn + collecte
    # ---------------------------
    async def _spawn_box_under_message(self, msg: discord.Message):
        guild = msg.guild
        channel = msg.channel
        if not guild:
            return

        me = guild.me
        if not me or not _can_react(channel, me):
            # sécurité supplémentaire
            return

        state = _STATES.setdefault(guild.id, GuildRavitailState())
        if state.active:
            return  # une boîte est déjà active

        # Marquer l'état comme actif
        state.active = True
        state.drop_channel_id = channel.id
        state.drop_starter_msg_id = msg.id
        state.participants.clear()
        state.started_at = time.time()

        # Poser la réaction 📦 sous le message de l’utilisateur
        try:
            await msg.add_reaction(BOX_EMOJI)
        except Exception:
            # si on ne peut finalement pas réagir → on annule ce drop
            state.active = False
            return

        # Attendre la fenêtre de récup
        await asyncio.sleep(CLAIM_WINDOW)

        # Récupérer la liste des participants (utilisateurs ayant réagi)
        try:
            # on refetch pour lire les réactions actuelles
            fresh_msg = await channel.fetch_message(msg.id)
            users: List[discord.User] = []
            for reaction in fresh_msg.reactions:
                if str(reaction.emoji) == BOX_EMOJI:
                    # limit=None pour récupérer tous les réacteurs
                    async for u in reaction.users():
                        if not u.bot:
                            users.append(u)
                    break
            unique_ids = {u.id for u in users}
        except Exception:
            unique_ids = set()

        # Nettoyage immédiat de l'état d’activité (avant l’envoi du récap)
        state.active = False
        state.drop_channel_id = None
        state.drop_message_id = None
        state.drop_starter_msg_id = None
        state.started_at = 0.0

        if not unique_ids:
            # Personne n’a cliqué → “Ravitaillement détruit”
            await self._send_destroyed_embed(channel)
            return

        # Attribuer les loots à la fin puis récap
        allocations: List[Tuple[discord.Member, str]] = []
        for uid in unique_ids:
            member = guild.get_member(uid)
            if not member:
                # essayer un fetch si pas en cache
                try:
                    member = await guild.fetch_member(uid)
                except Exception:
                    member = None
            if not member:
                continue

            item = get_random_item()
            if not item:
                continue

            # On ajoute l’objet à l’inventaire persistant (data.storage)
            inv, _, _ = get_user_data(str(guild.id), str(member.id))
            # on stocke uniquement les emojis d'items
            inv.append(item)
            allocations.append((member, item))

        # Sauvegarde physique
        try:
            save_data()
        except Exception:
            pass

        # Récap “Ravitaillement récupéré”
        await self._send_recap_embed(channel, allocations)

    # ---------------------------
    # Embeds
    # ---------------------------
    async def _send_recap_embed(self, channel: discord.abc.Messageable, allocations: List[Tuple[discord.Member, str]]):
        # S'il n’y a finalement personne (edge case)
        if not allocations:
            await self._send_destroyed_embed(channel)
            return

        # Grouper par utilisateur au cas où quelqu’un a cliqué plusieurs fois
        lines = []
        for member, item in allocations:
            lines.append(f"• {member.mention} ─ **{item}**")

        embed = discord.Embed(
            title="📦 Ravitaillement récupéré",
            color=discord.Color.green(),
        )
        embed.add_field(name="Butin distribué", value="\n".join(lines), inline=False)
        await channel.send(embed=embed)

    async def _send_destroyed_embed(self, channel: discord.abc.Messageable):
        embed = discord.Embed(
            title="📦 Ravitaillement détruit",
            color=discord.Color.red(),
        )
        await channel.send(embed=embed)

# ------------------------------------------------------------
# Setup extension
# ------------------------------------------------------------
async def setup(bot: commands.Bot):
    await bot.add_cog(RavitaillementCog(bot))

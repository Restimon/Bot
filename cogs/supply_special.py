# cogs/supply_special.py
from __future__ import annotations

import asyncio
import random
import time
from typing import Dict, List, Optional, Tuple

import discord
from discord.ext import commands

# ---- Dépendances projet (avec fallback sûrs) ----
from utils import get_random_item, OBJETS  # raretés/objets
try:
    # si SQLite stats_db dispo → on applique de “vrais” dégâts
    from stats_db import deal_damage, get_hp  # type: ignore
    _HAVE_STATS = True
except Exception:
    _HAVE_STATS = False
    # Fallback tout doux: on essaie le storage JSON minimal
    try:
        from data.storage import hp as _hp_map, save_data  # type: ignore
    except Exception:
        _hp_map = {}
        def save_data():  # no-op
            return
    async def deal_damage(attacker_id: int, user_id: int, amount: int) -> Dict[str, int]:
        gid = "0"  # inconnu ici → juste décrément local (visuel)
        # Pas de guild ici pour le fallback → on ne peut pas tenir un PV précis cross-serveur
        # On renvoie juste une structure compatible pour l’affichage
        return {"lost": max(0, int(amount)), "absorbed": 0}
    async def get_hp(user_id: int) -> Tuple[int, int]:
        # Fallback neutre
        return (100, 100)

# ------------------------------------------------------------
# Réglages
# ------------------------------------------------------------
BOX_EMOJI = "📦"
WINDOW_SECONDS = 5 * 60         # 5 minutes
MAX_CLAIMERS = 5                # max 5 personnes
TRAP_CHANCE = 0.30              # 30% d’avoir un piège (dégâts)
TRAP_DMG_RANGE = (6, 12)        # dégâts du piège si déclenché

# ------------------------------------------------------------
# Cog
# ------------------------------------------------------------
class SpecialSupply(commands.Cog):
    """
    Ravitaillement spécial :
      - Message du bot (embed) → réagir avec 📦 pour participer.
      - Disponible 5 minutes, max 5 personnes (les premières).
      - À la fin : récapitulatif “Ravitaillement récupéré”.
      - Récompense par personne : soit un objet (tiré via la rareté utils.OBJETS),
        soit un piège qui inflige des dégâts.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Une protection simple : 1 événement actif par salon
        self._active_by_channel: Dict[int, bool] = {}

    # ---------------------------
    # Slash (admin & public)
    # ---------------------------
    @commands.has_permissions(manage_guild=True)
    @commands.hybrid_command(name="supply_special", description="(Admin) Lancer un ravitaillement spécial (5 min, max 5).")
    async def supply_special_cmd(self, ctx: commands.Context):
        if not ctx.guild or not isinstance(ctx.channel, (discord.TextChannel, discord.Thread)):
            return await ctx.reply("❌ Utilise cette commande dans un salon texte du serveur.")
        await self._launch_event(ctx.channel)

    # Option slash pure
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    @commands.hybrid_group(name="special", fallback="start", description="(Admin) Contrôle du ravitaillement spécial.")
    async def special_group(self, ctx: commands.Context):
        """Alias: /special start"""
        if not ctx.guild or not isinstance(ctx.channel, (discord.TextChannel, discord.Thread)):
            return await ctx.reply("❌ Utilise cette commande dans un salon texte du serveur.")
        await self._launch_event(ctx.channel)

    # --------------------------------------------------------
    # Cœur de l’événement
    # --------------------------------------------------------
    async def _launch_event(self, channel: discord.abc.Messageable):
        # évite 2 événements simultanés dans le même salon
        ch_id = getattr(channel, "id", None)
        if ch_id and self._active_by_channel.get(ch_id):
            await channel.send("⏳ Un ravitaillement spécial est déjà en cours ici.")
            return
        if ch_id:
            self._active_by_channel[ch_id] = True

        # Embed d’annonce
        embed = discord.Embed(
            title="📦 Ravitaillement spécial GotValis",
            description="Réagissez avec 📦 pour récupérer une récompense surprise !\n"
                        "⌛ Disponible pendant **5 minutes**, **maximum 5 personnes**.",
            color=discord.Color.orange()
        )
        msg = await channel.send(embed=embed)
        try:
            await msg.add_reaction(BOX_EMOJI)
        except Exception:
            # si on ne peut pas réagir ici, on annule
            if ch_id:
                self._active_by_channel[ch_id] = False
            return

        # Collecte des réacteurs (premiers arrivés)
        claimers: List[int] = []
        claimed_set: set[int] = set()

        def _is_valid_reaction(reaction: discord.Reaction, user: discord.User) -> bool:
            if reaction.message.id != msg.id:
                return False
            if str(reaction.emoji) != BOX_EMOJI:
                return False
            if user.bot:
                return False
            return True

        end_at = time.time() + WINDOW_SECONDS

        # Boucle de collecte pendant 5 min ou jusqu’à MAX_CLAIMERS
        while time.time() < end_at and len(claimers) < MAX_CLAIMERS:
            timeout = max(0.0, end_at - time.time())
            try:
                reaction, user = await self.bot.wait_for(
                    "reaction_add",
                    timeout=timeout,
                    check=_is_valid_reaction
                )
            except asyncio.TimeoutError:
                break

            # Prend uniquement les **premiers** (pas de doublons)
            if user.id in claimed_set:
                continue
            claimed_set.add(user.id)
            claimers.append(user.id)

        # Résolution des récompenses
        results: List[str] = []
        guild = msg.guild
        for uid in claimers:
            member = guild.get_member(uid) if guild else None
            if not member and guild:
                try:
                    member = await guild.fetch_member(uid)
                except Exception:
                    member = None

            mention = member.mention if member else f"<@{uid}>"

            # Piège ?
            if random.random() < TRAP_CHANCE:
                dmg = random.randint(*TRAP_DMG_RANGE)
                # dégâts (stats_db si dispo)
                lost = dmg
                pv_after = None
                try:
                    if _HAVE_STATS and member:
                        _res = await deal_damage(0, member.id, dmg)
                        lost = int(_res.get("lost", dmg))
                        hp_now, _mx = await get_hp(member.id)
                        pv_after = hp_now
                except Exception:
                    pass

                if pv_after is None:
                    # fallback d’affichage
                    pv_after = max(0, 100 - lost)

                results.append(f"💥 {mention} a subi **{lost} dégâts** (PV: **{pv_after}**)")
                continue

            # Objet (via rareté)
            item = get_random_item() or "💰"
            label = item

            # Texte enrichi si on a des infos d’OBJETS (ex: soins)
            meta = OBJETS.get(item, {})
            typ = meta.get("type")
            if typ == "soin":
                val = meta.get("soin", 0)
                crit = int((meta.get("crit") or 0) * 100) if meta.get("crit", 0) <= 1 else int(meta.get("crit", 0))
                # pas d’application immédiate des PV ici; on **donne** l’objet
                results.append(f"🎁 {mention} a obtenu **{label}** — 💚 Restaure **{val} PV**. (Crit {crit}%)")
            elif typ == "regen":
                val = meta.get("valeur", 0)
                results.append(f"🎁 {mention} a obtenu **{label}** — ♻️ Régénère **{val} PV**/tick.")
            elif typ in ("poison", "virus", "infection"):
                results.append(f"🎁 {mention} a obtenu **{label}** — ☣️ Effet spécial.")
            elif typ == "attaque":
                val = meta.get("degats", 0)
                results.append(f"🎁 {mention} a obtenu **{label}** — ⚔️ Dégâts **{val}**.")
            else:
                results.append(f"🎁 {mention} a obtenu **{label}** !")

            # (Optionnel) on pourrait l’ajouter à l’inventaire persistant ici.
            try:
                from data.storage import get_user_data, save_data  # type: ignore
                inv, _, _ = get_user_data(str(guild.id), str(uid))
                inv.append(item)
                save_data()
            except Exception:
                pass

        # Récapitulatif
        recap = discord.Embed(
            title="📦 Récapitulatif du ravitaillement",
            color=discord.Color.green() if results else discord.Color.red()
        )
        if results:
            recap.add_field(name="\u200b", value="\n".join(results), inline=False)
        else:
            recap.title = "📦 Aucun participant"
        await channel.send(embed=recap)

        # Fin de l’événement dans ce salon
        if ch_id:
            self._active_by_channel[ch_id] = False


# ------------------------------------------------------------
# Setup extension
# ------------------------------------------------------------
async def setup(bot: commands.Bot):
    await bot.add_cog(SpecialSupply(bot))

# cogs/combat_cogs.py
from __future__ import annotations

import asyncio
from typing import Dict, List, Optional, Tuple

import discord
from discord import app_commands
from discord.ext import commands

# ─────────────────────────────────────────────────────────────
# Imports projet
# ─────────────────────────────────────────────────────────────
try:
    from ravitaillement import OBJETS  # ton dict d'items (types…) ⚠️ nom confirmé par toi
except Exception:
    # Fallback minimal si import échoue (pour éviter crash au chargement)
    OBJETS = {}

from inventory import get_item_qty
import combat  # ton moteur de combat (logique pure)

# ─────────────────────────────────────────────────────────────
# Config commande / catégories
# ─────────────────────────────────────────────────────────────

# Types d'items autorisés par commande
ATTACK_TYPES = {"attaque", "attaque_chaine", "poison", "virus", "infection"}
HEAL_TYPES = {"soin", "regen"}
USE_TYPES = {
    "bouclier",
    "vaccin",
    "vol",
    "immunite",
    "esquive+",
    "reduction",
    "mysterybox",
    # ajoute d'autres types non offensifs si besoin
}

ATTACK_COOLDOWN_SECONDS = 5  # CD demandé: 5s pour les attaques, pas pour heal

# Locks anti double-action par utilisateur
_user_locks: Dict[int, asyncio.Lock] = {}


def _get_lock(user_id: int) -> asyncio.Lock:
    lock = _user_locks.get(user_id)
    if not lock:
        lock = asyncio.Lock()
        _user_locks[user_id] = lock
    return lock


# ─────────────────────────────────────────────────────────────
# Utils
# ─────────────────────────────────────────────────────────────

def _item_matches_type(item_key: str, allowed_types: set) -> bool:
    meta = OBJETS.get(item_key) or {}
    return meta.get("type") in allowed_types

def _all_items_of_types(allowed_types: set) -> List[str]:
    return [k for k, v in OBJETS.items() if v.get("type") in allowed_types]

def _format_embed_from_result(result: dict, *, default_title: str) -> discord.Embed:
    """Transforme le dict résultat du moteur en Embed Discord."""
    title = result.get("title") or default_title
    desc_lines = result.get("lines") or []
    color = result.get("color") or 0x5865F2  # blurple par défaut

    emb = discord.Embed(title=title, description="\n".join(desc_lines), color=color)

    # Quelques extras si fournis par le moteur
    if "fields" in result and isinstance(result["fields"], list):
        for f in result["fields"]:
            name = f.get("name", "\u200b")
            value = f.get("value", "\u200b")
            inline = bool(f.get("inline", False))
            emb.add_field(name=name, value=value, inline=inline)

    if result.get("gif"):
        emb.set_image(url=result["gif"])

    if thumb := result.get("thumb"):
        emb.set_thumbnail(url=thumb)

    return emb


# ─────────────────────────────────────────────────────────────
# Cooldown personnalisé pour /fight (par user)
# ─────────────────────────────────────────────────────────────
# On utilise app_commands.checks.cooldown côté slash commands
fight_cooldown = app_commands.checks.cooldown(1, ATTACK_COOLDOWN_SECONDS, key=lambda i: (i.user.id))


# ─────────────────────────────────────────────────────────────
# Cog
# ─────────────────────────────────────────────────────────────

class CombatCog(commands.Cog):
    """Slash commandes de combat: /fight, /heal, /use."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # -------------- Autocomplete helpers --------------

    async def _autocomplete_items(self, interaction: discord.Interaction, current: str, pool_types: set) -> List[app_commands.Choice[str]]:
        keys = _all_items_of_types(pool_types)
        if current:
            cur = current.lower()
            keys = [k for k in keys if cur in k.lower()]
        # Trie les items par “type puis clé” pour cohérence
        keys.sort(key=lambda k: (OBJETS.get(k, {}).get("type", ""), k))
        return [app_commands.Choice(name=f"{k} — {OBJETS[k].get('type','')}", value=k) for k in keys[:25]]

    # -------------- /fight --------------

    @app_commands.command(name="fight", description="Attaquer une cible avec un objet d'attaque.")
    @app_commands.describe(cible="La cible à attaquer", item="Emoji/clé de l'objet d'attaque")
    @app_commands.autocomplete(item=lambda self, i, cur: self._autocomplete_items(i, cur, ATTACK_TYPES))
    @fight_cooldown
    async def fight_cmd(self, itx: discord.Interaction, cible: discord.Member, item: str):
        await itx.response.defer()

        # Vérifs basiques
        if cible.bot:
            return await itx.followup.send("❌ Tu ne peux pas attaquer un bot.", ephemeral=True)

        # Vérif type d'item
        if not OBJETS:
            return await itx.followup.send("❌ Aucun catalogue d'objets chargé.", ephemeral=True)
        if item not in OBJETS or not _item_matches_type(item, ATTACK_TYPES):
            return await itx.followup.send("❌ Cet item n'est pas un objet d'attaque valide.", ephemeral=True)

        # Vérif inventaire (on laisse le moteur décrémenter s'il a des règles spéciales ; ici on check juste > 0)
        have = await get_item_qty(itx.user.id, item)
        if have <= 0:
            return await itx.followup.send(f"❌ Tu n'as plus **{item}** dans ton inventaire.", ephemeral=True)

        # Lock par utilisateur attaquant
        lock = _get_lock(itx.user.id)
        if lock.locked():
            return await itx.followup.send("⏳ Action déjà en cours. Réessaie un instant.", ephemeral=True)

        async with lock:
            # Délègue au moteur
            try:
                result = await combat.fight(
                    attacker_id=itx.user.id,
                    target_id=cible.id,
                    item_key=item,
                    guild_id=itx.guild.id if itx.guild else 0,
                    channel_id=itx.channel.id if itx.channel else 0,
                )
            except AttributeError:
                return await itx.followup.send("❌ Le moteur de combat n'implémente pas `combat.fight(...)`.", ephemeral=True)

        emb = _format_embed_from_result(result or {}, default_title="⚔️ Attaque")
        await itx.followup.send(content=f"{itx.user.mention} → {cible.mention}", embed=emb)

    # -------------- /heal --------------

    @app_commands.command(name="heal", description="Soigner une cible avec un objet de soin.")
    @app_commands.describe(cible="La cible à soigner", item="Emoji/clé de l'objet de soin")
    @app_commands.autocomplete(item=lambda self, i, cur: self._autocomplete_items(i, cur, HEAL_TYPES))
    async def heal_cmd(self, itx: discord.Interaction, cible: discord.Member, item: str):
        await itx.response.defer()

        if cible.bot:
            return await itx.followup.send("❌ Tu ne peux pas soigner un bot.", ephemeral=True)

        if not OBJETS:
            return await itx.followup.send("❌ Aucun catalogue d'objets chargé.", ephemeral=True)
        if item not in OBJETS or not _item_matches_type(item, HEAL_TYPES):
            return await itx.followup.send("❌ Cet item n'est pas un objet de **soin** valide.", ephemeral=True)

        have = await get_item_qty(itx.user.id, item)
        if have <= 0:
            return await itx.followup.send(f"❌ Tu n'as plus **{item}** dans ton inventaire.", ephemeral=True)

        # Pas de cooldown pour le heal (selon tes règles)
        lock = _get_lock(itx.user.id)
        if lock.locked():
            return await itx.followup.send("⏳ Action déjà en cours. Réessaie un instant.", ephemeral=True)

        async with lock:
            try:
                result = await combat.heal(
                    healer_id=itx.user.id,
                    target_id=cible.id,
                    item_key=item,
                    guild_id=itx.guild.id if itx.guild else 0,
                    channel_id=itx.channel.id if itx.channel else 0,
                )
            except AttributeError:
                return await itx.followup.send("❌ Le moteur de combat n'implémente pas `combat.heal(...)`.", ephemeral=True)

        emb = _format_embed_from_result(result or {}, default_title="💊 Soin")
        await itx.followup.send(content=f"{itx.user.mention} → {cible.mention}", embed=emb)

    # -------------- /use --------------

    @app_commands.command(name="use", description="Utiliser un objet de soutien/état (bouclier, vaccin, etc.) sur une cible.")
    @app_commands.describe(cible="La cible (toi ou quelqu'un d'autre)", item="Emoji/clé de l'objet à utiliser")
    @app_commands.autocomplete(item=lambda self, i, cur: self._autocomplete_items(i, cur, USE_TYPES))
    async def use_cmd(self, itx: discord.Interaction, cible: discord.Member, item: str):
        await itx.response.defer()

        if cible.bot:
            return await itx.followup.send("❌ Tu ne peux pas cibler un bot.", ephemeral=True)

        if not OBJETS:
            return await itx.followup.send("❌ Aucun catalogue d'objets chargé.", ephemeral=True)
        if item not in OBJETS or not _item_matches_type(item, USE_TYPES):
            return await itx.followup.send("❌ Cet item n'est pas un objet **utilisable** valide.", ephemeral=True)

        have = await get_item_qty(itx.user.id, item)
        if have <= 0:
            return await itx.followup.send(f"❌ Tu n'as plus **{item}** dans ton inventaire.", ephemeral=True)

        # Décide si /use doit subir le cooldown d'attaque (tu as dit non: seulement attaques)
        lock = _get_lock(itx.user.id)
        if lock.locked():
            return await itx.followup.send("⏳ Action déjà en cours. Réessaie un instant.", ephemeral=True)

        async with lock:
            try:
                result = await combat.use_item(
                    user_id=itx.user.id,
                    target_id=cible.id,
                    item_key=item,
                    guild_id=itx.guild.id if itx.guild else 0,
                    channel_id=itx.channel.id if itx.channel else 0,
                )
            except AttributeError:
                return await itx.followup.send("❌ Le moteur de combat n'implémente pas `combat.use_item(...)`.", ephemeral=True)

        emb = _format_embed_from_result(result or {}, default_title="🧰 Utilisation")
        await itx.followup.send(content=f"{itx.user.mention} → {cible.mention}", embed=emb)

    # -------------- error handlers --------------

    @fight_cmd.error
    async def fight_error(self, itx: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CommandOnCooldown):
            retry = f"{error.retry_after:.1f}s"
            return await itx.response.send_message(f"⌛ Tu dois attendre **{retry}** avant de réattaquer.", ephemeral=True)
        # autre erreur: on essaie de répondre proprement
        try:
            await itx.response.send_message("❌ Erreur pendant /fight.", ephemeral=True)
        except discord.InteractionResponded:
            await itx.followup.send("❌ Erreur pendant /fight.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(CombatCog(bot))

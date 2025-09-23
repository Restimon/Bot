# cogs/use_cog.py
from __future__ import annotations

import json
import random
from typing import Dict, List, Optional, Tuple

import discord
from discord.ext import commands
from discord import app_commands

# Effets & passifs
try:
    from effects_db import add_or_refresh_effect, remove_effect  # type: ignore
except Exception:
    async def add_or_refresh_effect(*args, **kwargs):  # type: ignore
        return True
    async def remove_effect(*args, **kwargs):  # type: ignore
        return None

try:
    # Hooks optionnels
    from passifs import trigger as passifs_trigger  # type: ignore
except Exception:
    async def passifs_trigger(*args, **kwargs):  # type: ignore
        return {}

# Boucliers (PB)
try:
    from shields_db import add_shield  # type: ignore
except Exception:
    async def add_shield(uid: int, delta: int, cap_to_max: bool = True) -> int:  # type: ignore
        return 0

# Inventaire
from inventory_db import get_item_qty, remove_item, add_item, get_all_items

# Catalogue d’objets (emoji -> fiche) + tirage aléatoire
try:
    from utils import OBJETS, get_random_item  # type: ignore
except Exception:
    OBJETS: Dict[str, Dict] = {}
    def get_random_item(debug: bool = False) -> str:
        return random.choice(["🍀", "❄️", "🧪", "🩹", "💊"])

# Leaderboard live (optionnel)
def _schedule_lb(bot: commands.Bot, gid: Optional[int], reason: str):
    if not gid:
        return
    try:
        from cogs.leaderboard_live import schedule_lb_update  # type: ignore
        schedule_lb_update(bot, gid, reason)
    except Exception:
        pass


ALLOWED_TYPES = (
    "vaccin",        # retire les DOTs/virus
    "bouclier",      # +PB
    "mysterybox",    # donne un objet aléatoire
    "vol",           # tentative de vol
    "esquive+",      # buff esquive
    "reduction",     # réduction dégâts
    "immunite",      # immunité temporaire (selon logique de tes passifs/effets)
)

NEGATIVE_EFFECTS = ("poison", "infection", "brulure", "virus")


class UseCog(commands.Cog):
    """Gestion des objets utilitaires/buffs: /use"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ─────────────────────────────────────────────────────────
    # Helpers inventaire / catalogue
    # ─────────────────────────────────────────────────────────
    def _obj_info(self, emoji: str) -> Optional[Dict]:
        info = OBJETS.get(emoji)
        return dict(info) if isinstance(info, dict) else None

    async def _list_owned_items(self, uid: int) -> List[Tuple[str, int]]:
        """
        Retourne [(emoji, qty)] possédés, fusionnés/triés (utilisé par l’autocomplete).
        """
        owned: List[Tuple[str, int]] = []
        # 1) essai via listing complet
        try:
            rows = await get_all_items(uid)
            for emoji, qty in rows:
                try:
                    q = int(qty)
                except Exception:
                    q = 0
                if q > 0:
                    owned.append((str(emoji), q))
        except Exception:
            pass

        # 2) fallback: interroge seulement les items du catalogue
        if not owned and OBJETS:
            for emoji in OBJETS.keys():
                try:
                    q = int(await get_item_qty(uid, emoji) or 0)
                except Exception:
                    q = 0
                if q > 0:
                    owned.append((emoji, q))

        # fusion & tri
        merged: Dict[str, int] = {}
        for e, q in owned:
            merged[e] = merged.get(e, 0) + int(q)
        return sorted(merged.items(), key=lambda t: t[0])

    async def _ac_items_use(self, inter: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        """
        Autocomplete: ne propose QUE les objets possédés dont type ∈ ALLOWED_TYPES.
        """
        uid = inter.user.id
        cur = (current or "").strip().lower()
        owned = await self._list_owned_items(uid)

        out: List[app_commands.Choice[str]] = []
        for emoji, qty in owned:
            info = OBJETS.get(emoji) or {}
            typ = str(info.get("type", "") or "")
            if typ not in ALLOWED_TYPES:
                # On ne mélange pas le /use avec /fight et /heal :
                # typ == "attaque"/"attaque_chaine" → /fight
                # typ == "soin"/"regen" → /heal
                continue

            # label lisible
            try:
                if typ == "bouclier":
                    val = int(info.get("valeur", info.get("value", 0)) or 0)
                    label = f"bouclier {val}" if val else "bouclier"
                elif typ == "esquive+":
                    v = int(info.get("valeur", info.get("value", 0)) or 0)
                    d = int(info.get("duree", info.get("duration", 300)) or 300)
                    label = f"esquive+ +{v}%/{d}s" if v else "esquive+"
                elif typ == "reduction":
                    v = int(info.get("valeur", info.get("value", 0)) or 0)
                    d = int(info.get("duree", info.get("duration", 300)) or 300)
                    label = f"réduction {v}%/{d}s" if v else "réduction"
                elif typ == "immunite":
                    d = int(info.get("duree", info.get("duration", 300)) or 300)
                    label = f"immunité {d}s"
                else:
                    label = typ
            except Exception:
                label = typ

            name = f"{emoji} — {label} (x{qty})"
            if cur and (cur not in emoji and cur not in label.lower()):
                continue
            out.append(app_commands.Choice(name=name[:100], value=emoji))
            if len(out) >= 20:
                break
        return out

    async def _consume_item(self, user_id: int, emoji: str) -> bool:
        try:
            qty = await get_item_qty(user_id, emoji)
            if int(qty or 0) <= 0:
                return False
            ok = await remove_item(user_id, emoji, 1)
            return bool(ok)
        except Exception:
            return False

    # ─────────────────────────────────────────────────────────
    # Logiques d’application
    # ─────────────────────────────────────────────────────────
    async def _apply_vaccin(
        self, inter: discord.Interaction, user: discord.Member, cible: Optional[discord.Member], emoji: str, info: Dict
    ) -> discord.Embed:
        target = cible or user
        # Retire les effets négatifs usuels
        removed = []
        for eff in NEGATIVE_EFFECTS:
            try:
                await remove_effect(target.id, eff)
                removed.append(eff)
            except Exception:
                pass

        # Hook passifs après "soin d’état"
        try:
            await passifs_trigger("on_cleanse", user_id=user.id, target_id=target.id, item_emoji=emoji)
        except Exception:
            pass

        lines = [
            f"{user.mention} utilise **{emoji}** sur {target.mention}.",
            "🧼 Effets retirés : " + (", ".join(removed) if removed else "_aucun trouvé_"),
        ]
        return discord.Embed(title="Vaccin", description="\n".join(lines), color=discord.Color.teal())

    async def _apply_bouclier(
        self, inter: discord.Interaction, user: discord.Member, cible: Optional[discord.Member], emoji: str, info: Dict
    ) -> discord.Embed:
        target = cible or user
        val = int(info.get("valeur", info.get("value", 0)) or 0)
        if val <= 0:
            return discord.Embed(
                title="❗ Objet bouclier invalide",
                description=f"{emoji} n’a pas de valeur.",
                color=discord.Color.red()
            )
        new_pb = await add_shield(target.id, val, cap_to_max=True)
        lines = [
            f"{user.mention} applique **{emoji}** sur {target.mention}.",
            f"🛡 Bouclier **+{val}** → **{new_pb}** PB"
        ]
        return discord.Embed(title="Bouclier", description="\n".join(lines), color=discord.Color.blue())

    async def _apply_buff(
        self, inter: discord.Interaction, user: discord.Member, cible: Optional[discord.Member], emoji: str, info: Dict
    ) -> discord.Embed:
        target = cible or user
        typ = str(info.get("type"))

        # Lecture souple des champs
        val = float(info.get("valeur", info.get("value", 0)) or 0)
        dur = int(info.get("duree", info.get("duration", 300)) or 300)

        # Normalise quelques cas (ex: pourcent)
        # Tu peux définir tes unités comme tu veux dans tes passifs
        # Ici, on stocke la value telle quelle; tes passifs/effets interprètent.
        await add_or_refresh_effect(
            user_id=target.id,
            eff_type=typ,          # "esquive+", "reduction", "immunite"
            value=float(val),
            duration=int(dur),
            interval=0,
            source_id=user.id,
            meta_json=json.dumps({"applied_in": inter.channel.id})
        )

        labels = {
            "esquive+": "👟 Esquive+",
            "reduction": "🪖 Réduction de dégâts",
            "immunite": "⭐️ Immunité",
        }
        desc = (
            f"{user.mention} applique **{emoji}** ({labels.get(typ, typ)}) "
            f"sur {target.mention} pour **{dur}s**."
        )
        if val:
            desc += f"\nValeur: **{val}**"
        return discord.Embed(title="Buff appliqué", description=desc, color=discord.Color.blurple())

    async def _apply_mysterybox(
        self, inter: discord.Interaction, user: discord.Member, emoji: str, info: Dict
    ) -> discord.Embed:
        got = get_random_item(debug=False)
        await add_item(user.id, got, 1)
        desc = [f"{user.mention} ouvre **{emoji}** :", f"🎁 Tu obtiens **{got}** !"]

        # Hook passifs : bonus potentiel
        try:
            post = await passifs_trigger("on_box_open", user_id=user.id) or {}
        except Exception:
            post = {}

        extra = int(post.get("extra_items", 0) or 0)
        while extra > 0:
            extra_item = get_random_item(debug=False)
            await add_item(user.id, extra_item, 1)
            desc.append(f"🎉 Bonus: **{extra_item}**")
            extra -= 1

        return discord.Embed(title="📦 Box ouverte", description="\n".join(desc), color=discord.Color.gold())

    async def _apply_vol(
        self, inter: discord.Interaction, user: discord.Member, cible: Optional[discord.Member], emoji: str, info: Dict
    ) -> discord.Embed:
        if not isinstance(cible, discord.Member):
            return discord.Embed(
                title="Vol",
                description="Il faut une **cible** pour tenter un vol.",
                color=discord.Color.dark_grey()
            )

        # Hook passifs: possibilité de blocage anti-vol
        try:
            res = await passifs_trigger("on_theft_attempt", attacker_id=user.id, target_id=cible.id) or {}
        except Exception:
            res = {}

        if res.get("blocked"):
            return discord.Embed(
                title="Vol",
                description=f"🛡 {cible.mention} est **intouchable** (anti-vol).",
                color=discord.Color.dark_grey()
            )

        success = (random.random() < 0.25)  # 25%
        if success:
            got = get_random_item(debug=False)
            await add_item(user.id, got, 1)
            desc = f"🕵️ Vol réussi sur {cible.mention} ! Tu obtiens **{got}**."
        else:
            desc = f"🕵️ Vol raté sur {cible.mention}…"

        return discord.Embed(title="Vol", description=desc, color=discord.Color.dark_grey())

    # ─────────────────────────────────────────────────────────
    # /use — point d’entrée
    # ─────────────────────────────────────────────────────────
    @app_commands.command(name="use", description="Utiliser un objet utilitaire/buff de ton inventaire.")
    @app_commands.describe(objet="Choisis un objet", cible="Cible (selon l'objet)")
    @app_commands.autocomplete(objet=_ac_items_use)
    async def use(self, inter: discord.Interaction, objet: str, cible: Optional[discord.Member] = None):
        if not inter.guild:
            return await inter.response.send_message("❌ À utiliser dans un serveur.", ephemeral=True)

        info = self._obj_info(objet)
        if not info:
            return await inter.response.send_message("Objet inconnu.", ephemeral=True)

        typ = str(info.get("type", ""))

        # Redirections explicites pour éviter les confusions
        if typ in ("attaque", "attaque_chaine", "poison", "infection", "virus", "brulure"):
            return await inter.response.send_message(
                "Cet objet s’utilise avec **/fight** (attaque/effet offensif).",
                ephemeral=True
            )
        if typ in ("soin", "regen"):
            return await inter.response.send_message(
                "Cet objet s’utilise avec **/heal** (soins/régénération).",
                ephemeral=True
            )
        if typ not in ALLOWED_TYPES:
            return await inter.response.send_message(
                f"Objet non géré par **/use** (`type={typ}`)").  # noqa: E999
        
        # Consommation
        if not await self._consume_item(inter.user.id, objet):
            return await inter.response.send_message(f"Tu n’as pas **{objet}** dans ton inventaire.", ephemeral=True)

        await inter.response.defer(thinking=True)

        # Application selon type
        try:
            if typ == "vaccin":
                embed = await self._apply_vaccin(inter, inter.user, cible, objet, info)
            elif typ == "bouclier":
                embed = await self._apply_bouclier(inter, inter.user, cible, objet, info)
            elif typ in ("esquive+", "reduction", "immunite"):
                embed = await self._apply_buff(inter, inter.user, cible, objet, info)
            elif typ == "mysterybox":
                embed = await self._apply_mysterybox(inter, inter.user, objet, info)
            elif typ == "vol":
                embed = await self._apply_vol(inter, inter.user, cible, objet, info)
            else:
                embed = discord.Embed(
                    title="Objet non géré",
                    description=f"{objet} (`{typ}`) n’a pas de logique dédiée pour le moment.",
                    color=discord.Color.dark_grey()
                )
        except Exception as e:
            embed = discord.Embed(
                title="❗ Erreur pendant l’utilisation",
                description=f"Une erreur est survenue: `{type(e).__name__}`.",
                color=discord.Color.red()
            )
            # on renvoie tout de même la maj leaderboard plus bas

        # Hook passifs “post-use” (ex: annuler la conso, bonus…)
        try:
            post = await passifs_trigger("on_use_item", user_id=inter.user.id, item_emoji=objet, item_type=typ) or {}
        except Exception:
            post = {}
        if post.get("dont_consume"):
            try:
                await add_item(inter.user.id, objet, 1)
            except Exception:
                pass

        await inter.followup.send(embed=embed)
        _schedule_lb(self.bot, inter.guild.id if inter.guild else None, "use")

    # ─────────────────────────────────────────────────────────
    # Utilitaires privés
    # ─────────────────────────────────────────────────────────
    async def _consume_item(self, user_id: int, emoji: str) -> bool:
        try:
            qty = await get_item_qty(user_id, emoji)
            if int(qty or 0) <= 0:
                return False
            ok = await remove_item(user_id, emoji, 1)
            return bool(ok)
        except Exception:
            return False


async def setup(bot: commands.Bot):
    await bot.add_cog(UseCog(bot))

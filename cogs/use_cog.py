# cogs/use_cog.py
from __future__ import annotations

import json
from typing import Optional, Dict, List, Tuple

import discord
from discord import app_commands
from discord.ext import commands

# Inventaire / objets
from inventory_db import get_item_qty, remove_item, get_all_items
try:
    from utils import OBJETS
except Exception:
    OBJETS: Dict[str, Dict] = {}

# HP / PB
from stats_db import heal_user, get_hp
try:
    from shields_db import add_shield as _add_shield, get_shield as _get_shield, get_max_shield as _get_max_shield
except Exception:
    _add_shield = _get_shield = _get_max_shield = None  # fallback gérés plus bas

# Effets périodiques / temporaires
try:
    from effects_db import add_or_refresh_effect
except Exception:
    async def add_or_refresh_effect(*args, **kwargs):  # type: ignore
        return True

# Pour broadcaster les ticks au bon salon (partagé avec combat_cog)
try:
    from cogs.combat_cog import remember_tick_channel  # type: ignore
except Exception:
    def remember_tick_channel(user_id: int, guild_id: int, channel_id: int) -> None:  # type: ignore
        pass


def _info(emoji: str) -> Optional[Dict]:
    meta = OBJETS.get(emoji)
    return dict(meta) if isinstance(meta, dict) else None


async def _list_owned_items(uid: int) -> List[Tuple[str, int]]:
    """Inventaire robuste pour autocompléter."""
    out: List[Tuple[str, int]] = []
    try:
        rows = await get_all_items(uid)
        if isinstance(rows, list):
            for r in rows:
                if isinstance(r, (list, tuple)) and len(r) >= 2:
                    e, q = str(r[0]), int(r[1])
                    if e and q > 0:
                        out.append((e, q))
                elif isinstance(r, dict):
                    e = str(r.get("emoji") or r.get("item") or r.get("id") or r.get("key") or "")
                    q = int(r.get("qty") or r.get("quantity") or r.get("count") or r.get("n") or 0)
                    if e and q > 0:
                        out.append((e, q))
        elif isinstance(rows, dict):
            for e, q in rows.items():
                try:
                    if int(q) > 0:
                        out.append((str(e), int(q)))
                except Exception:
                    continue
    except Exception:
        pass
    return sorted(out, key=lambda t: t[0])


def _fmt_interval_secs(s: int) -> str:
    s = max(1, int(s))
    if s % 3600 == 0:
        h = s // 3600
        return f"{h} heure" if h == 1 else f"{h} heures"
    if s % 60 == 0:
        m = s // 60
        return f"{m} minute" if m == 1 else f"{m} minutes"
    return f"{s} s"


class UseCog(commands.Cog):
    """Commande /use pour utiliser des objets non offensifs (soin, regen, bouclier, buffs) sur soi **ou** sur une cible."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ---------- Autocomplétion : on ne propose pas les objets offensifs ----------
    async def _ac_items_use(self, inter: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        cur = (current or "").strip().lower()
        owned = await _list_owned_items(inter.user.id)

        offensive = {"attaque", "attaque_chaine", "poison", "infection", "virus", "brulure"}
        out: List[app_commands.Choice[str]] = []
        for emoji, qty in owned:
            meta = OBJETS.get(emoji) or {}
            typ = str(meta.get("type", ""))
            if typ in offensive:
                continue
            label = meta.get("nom") or meta.get("label") or typ or "objet"
            display = f"{emoji} — {label} (x{qty})"
            if cur and (cur not in emoji and cur not in str(label).lower()):
                continue
            out.append(app_commands.Choice(name=display[:100], value=emoji))
            if len(out) >= 20:
                break
        return out

    # ---------- Helpers ----------
    async def _consume(self, uid: int, emoji: str) -> bool:
        try:
            q = int(await get_item_qty(uid, emoji) or 0)
            if q <= 0:
                return False
            ok = await remove_item(uid, emoji, 1)
            return bool(ok)
        except Exception:
            return False

    def _roll_val(self, info: dict, default: int) -> int:
        if not isinstance(info, dict):
            return int(default)
        if "min" in info and "max" in info:
            try:
                import random
                a = int(info.get("min", 0)); b = int(info.get("max", 0))
                if a > b: a, b = b, a
                return random.randint(a, b)
            except Exception:
                pass
        for k in ("valeur","value","amount","heal","soin","degats","dmg"):
            if k in info:
                try: return int(info[k])
                except Exception: continue
        return int(default)

    # ---------- Slash ----------
    @app_commands.command(name="use", description="Utiliser un objet de soutien sur toi ou sur une cible.")
    @app_commands.describe(objet="Emoji de l'objet (soin/regen/bouclier/buffs...)", cible="Cible (optionnel, par défaut: toi)")
    @app_commands.autocomplete(objet=_ac_items_use)
    async def use(self, inter: discord.Interaction, objet: str, cible: Optional[discord.Member] = None):
        meta = _info(objet)
        if not meta:
            return await inter.response.send_message("❌ Objet inconnu.", ephemeral=True)

        typ = str(meta.get("type", "")).lower()

        # Les objets offensifs doivent passer par /fight
        if typ in {"attaque", "attaque_chaine", "poison", "infection", "virus", "brulure"}:
            return await inter.response.send_message("⚠️ Utilise plutôt **/fight** pour les objets offensifs.", ephemeral=True)

        # Ciblage : par défaut on prend la cible fournie ; si self_only => forcer sur soi
        target: discord.Member = cible or inter.user
        if meta.get("self_only", False):
            target = inter.user

        # Consommation toujours chez l’UTILISATEUR (pas chez la cible)
        if not await self._consume(inter.user.id, objet):
            return await inter.response.send_message(f"❌ Tu n’as pas **{objet}**.", ephemeral=True)

        await inter.response.defer(thinking=True)

        # Branches principales
        try:
            if typ == "soin":
                amount = self._roll_val(meta, 10)
                healed = await heal_user(inter.user.id, target.id, amount)
                hp_after, mx = await get_hp(target.id)
                gif = meta.get("gif_heal") or meta.get("gif") or meta.get("gif_attack")
                if healed <= 0:
                    desc = f"{inter.user.mention} tente de soigner {target.mention} avec {objet}, mais les PV sont déjà au max."
                else:
                    desc = (
                        f"{inter.user.mention} rend **{healed} PV** à {target.mention} avec {objet}.\n"
                        f"❤️ **{hp_after-healed}/{mx}** + (**{healed}**) = ❤️ **{hp_after}/{mx}**"
                    )
                emb = discord.Embed(title="💊 Soin", description=desc, color=discord.Color.green())
                if isinstance(gif, str):
                    emb.set_image(url=gif)
                return await inter.followup.send(embed=emb)

            if typ == "regen":
                val = self._roll_val(meta, 2)
                interval = int(meta.get("interval", meta.get("intervalle", 60)) or 60)
                duration = int(meta.get("duration", meta.get("duree", 1800)) or 1800)
                remember_tick_channel(target.id, inter.guild.id, inter.channel.id)
                await add_or_refresh_effect(
                    user_id=target.id, eff_type="regen", value=float(val),
                    duration=duration, interval=interval, source_id=inter.user.id,
                    meta_json=json.dumps({"applied_in": inter.channel.id})
                )
                gif = meta.get("gif_heal") or meta.get("gif") or meta.get("gif_attack")
                emb = discord.Embed(
                    title="💕 Régénération",
                    description=(
                        f"{inter.user.mention} applique **{objet}** sur {target.mention} "
                        f"(+{val} PV / **{_fmt_interval_secs(interval)}** pendant **{_fmt_interval_secs(duration)}**)."
                    ),
                    color=discord.Color.teal()
                )
                if isinstance(gif, str):
                    emb.set_image(url=gif)
                return await inter.followup.send(embed=emb)

            if typ == "bouclier":
                val = self._roll_val(meta, 5)
                gif = meta.get("gif_heal") or meta.get("gif") or meta.get("gif_attack")

                if _add_shield and _get_shield:
                    before = 0
                    try: before = int(await _get_shield(target.id))
                    except Exception: pass
                    try:
                        added = await _add_shield(target.id, val, cap_to_max=True)  # type: ignore[arg-type]
                    except TypeError:
                        added = await _add_shield(target.id, val)  # type: ignore[misc]
                    try: after = int(await _get_shield(target.id))
                    except Exception: after = before
                    gained = max(0, after - before)
                    desc = f"🛡 {target.mention} gagne **{gained} PB**."
                else:
                    # Fallback simplifié via stats_db si dispo
                    try:
                        from stats_db import get_shield as _get, set_shield as _set
                        before = int(await _get(target.id))
                        after = max(0, before + int(val))
                        await _set(target.id, after)
                        desc = f"🛡 {target.mention} gagne **{after-before} PB**."
                    except Exception:
                        desc = f"🛡 {target.mention} gagne un bouclier."

                emb = discord.Embed(title="🛡 Bouclier", description=desc, color=discord.Color.brand_teal())
                if isinstance(gif, str):
                    emb.set_image(url=gif)
                return await inter.followup.send(embed=emb)

            # Buffs génériques (réduction, esquive, etc.)
            # On attend dans OBJETS soit "eff_type", soit on réutilise "type" (ex: reduction_temp).
            eff_type = str(meta.get("eff_type", typ))
            if eff_type:
                val = float(meta.get("valeur", meta.get("value", 0.1)) or 0.1)
                interval = int(meta.get("interval", meta.get("intervalle", 60)) or 60)
                duration = int(meta.get("duration", meta.get("duree", 3600)) or 3600)
                remember_tick_channel(target.id, inter.guild.id, inter.channel.id)
                await add_or_refresh_effect(
                    user_id=target.id, eff_type=eff_type, value=float(val),
                    duration=duration, interval=interval, source_id=inter.user.id,
                    meta_json=json.dumps({"applied_in": inter.channel.id})
                )
                label = meta.get("nom") or meta.get("label") or eff_type
                emb = discord.Embed(
                    title=f"✨ {label}",
                    description=(
                        f"{inter.user.mention} applique **{objet}** sur {target.mention} "
                        f"(val={val}, tick **{_fmt_interval_secs(interval)}**, durée **{_fmt_interval_secs(duration)}**)."
                    ),
                    color=discord.Color.blurple()
                )
                gif = meta.get("gif") or meta.get("gif_heal") or meta.get("gif_attack")
                if isinstance(gif, str):
                    emb.set_image(url=gif)
                return await inter.followup.send(embed=emb)

            # Si on ne sait pas quoi faire
            return await inter.followup.send("ℹ️ Objet non offensif reconnu, mais aucun effet associé.", ephemeral=True)

        except Exception as e:
            emb = discord.Embed(
                title="❗ Erreur",
                description=f"Action interrompue : `{type(e).__name__}: {e}`",
                color=discord.Color.red()
            )
            return await inter.followup.send(embed=emb)


async def setup(bot: commands.Bot):
    await bot.add_cog(UseCog(bot))

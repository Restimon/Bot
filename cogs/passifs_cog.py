# cogs/passifs_cog.py
from __future__ import annotations

import time
from typing import List, Optional, Dict

import discord
from discord import app_commands
from discord.ext import commands

from passifs import (
    set_equipped_from_personnage,
    get_equipped_code,
)
from effects_db import list_effects
from personnage import (
    PERSONNAGES,
    PASSIF_CODE_MAP,
    get_tous_les_noms,
    trouver,
)

# ─────────────────────────────────────────────────────────────
# Utils
# ─────────────────────────────────────────────────────────────

def _now() -> int:
    return int(time.time())

def _format_duration(seconds: int) -> str:
    if seconds <= 0:
        return "0s"
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h}h {m}m {s}s"
    if m > 0:
        return f"{m}m {s}s"
    return f"{s}s"

# label + emoji pour les effets fréquents
EFFECT_LABELS: Dict[str, str] = {
    "poison": "🧪 Poison",
    "virus": "🦠 Virus",
    "infection": "🧟 Infection",
    "brulure": "🔥 Brûlure",
    "regen": "💕 Régénération",
    "reduction": "🛡 Réduction (perma)",
    "reduction_temp": "🛡 Réduction (temp.)",
    "reduction_valen": "🛡 Réduction (Valen)",
    "esquive": "👟 Esquive",
    "immunite": "⭐ Immunité",
}

# reverse map: code -> nom passif (pour affichage)
CODE_TO_PASSIF_NOM: Dict[str, str] = {v: k for k, v in PASSIF_CODE_MAP.items()}

# ─────────────────────────────────────────────────────────────
# Cog
# ─────────────────────────────────────────────────────────────

class PassifsCog(commands.Cog):
    """Commandes pour équiper et visualiser les passifs + effets actifs."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # -------------- /equip --------------

    @app_commands.command(name="equip", description="Équiper un personnage pour activer son passif.")
    @app_commands.describe(personnage="Nom du personnage à équiper")
    @app_commands.autocomplete(personnage=lambda i, cur: PassifsCog.autocomplete_personnages(i, cur))
    async def equip_cmd(self, itx: discord.Interaction, personnage: str):
        await itx.response.defer(ephemeral=True)  # réponse discrète

        p = trouver(personnage)  # tolérant (nom ou slug)
        if not p:
            # on retente exact sur la casse si besoin
            if personnage in PERSONNAGES:
                p = PERSONNAGES[personnage]
            else:
                return await itx.followup.send("❌ Personnage introuvable. Vérifie l’orthographe.", ephemeral=True)

        ok = await set_equipped_from_personnage(itx.user.id, p["nom"])
        if not ok:
            return await itx.followup.send("❌ Impossible d’équiper ce personnage (passif non mappé).", ephemeral=True)

        # embed de confirmation
        emb = discord.Embed(
            title=f"✅ Passif équipé : {p['passif']['nom']}",
            description=p["passif"]["effet"],
            color=discord.Color.green()
        )
        emb.set_author(name=p["nom"])
        if p.get("image"):
            emb.set_thumbnail(url=f"attachment://portrait.png")  # si tu préfères upload File
        # En pratique, on peut directement set_thumbnail(url=p["image"]) si c’est une URL publique
        if p.get("image", "").startswith("http"):
            emb.set_thumbnail(url=p["image"])

        await itx.followup.send(embed=emb, ephemeral=True)

    @staticmethod
    async def autocomplete_personnages(
        itx: discord.Interaction,
        current: str,
    ) -> List[app_commands.Choice[str]]:
        noms = get_tous_les_noms()
        if current:
            cur_low = current.lower()
            noms = [n for n in noms if cur_low in n.lower()]
        return [app_commands.Choice(name=n, value=n) for n in noms[:25]]

    # -------------- /passif --------------

    @app_commands.command(name="passif", description="Voir le passif actuellement équipé.")
    async def passif_cmd(self, itx: discord.Interaction):
        await itx.response.defer(ephemeral=True)
        code = await get_equipped_code(itx.user.id)
        if not code:
            return await itx.followup.send("ℹ️ Aucun personnage équipé. Utilise `/equip`.", ephemeral=True)

        # retrouve le personnage par code passif
        passif_nom = CODE_TO_PASSIF_NOM.get(code, "Passif inconnu")

        perso = None
        for p in PERSONNAGES.values():
            if p.get("passif", {}).get("nom") == passif_nom:
                perso = p
                break

        desc = ""
        title = passif_nom
        thumb = None
        author_name = itx.user.display_name

        if perso:
            desc = perso["passif"]["effet"]
            title = f"{perso['passif']['nom']}"
            author_name = perso["nom"]
            thumb = perso.get("image")

        emb = discord.Embed(
            title=title,
            description=desc or f"Code interne : `{code}`",
            color=discord.Color.blurple()
        )
        emb.set_author(name=author_name)
        if thumb:
            if thumb.startswith("http"):
                emb.set_thumbnail(url=thumb)
        await itx.followup.send(embed=emb, ephemeral=True)

    # -------------- /status --------------

    @app_commands.command(name="status", description="Voir vos effets/états actifs (poison, virus, regen, etc.).")
    async def status_cmd(self, itx: discord.Interaction):
        await itx.response.defer(ephemeral=True)

        rows = await list_effects(itx.user.id)
        if not rows:
            return await itx.followup.send("🧼 Aucun effet actif.", ephemeral=True)

        now = _now()
        lines: List[str] = []
        for eff_type, value, interval, next_ts, end_ts, source_id, meta_json in rows:
            label = EFFECT_LABELS.get(eff_type, eff_type)
            remain = max(0, end_ts - now)
            tick = f"• Tick: {interval//60} min" if interval > 0 else None
            src = f"• Source: <@{int(source_id)}>" if source_id and str(source_id).isdigit() and int(source_id) != 0 else None

            # value : dmg/soin par tick pour DOT/regen, ou pourcentage pour reduc/esquive
            if eff_type in ("poison", "virus", "infection", "brulure", "regen"):
                val_txt = f"• Valeur: {int(value)} / tick"
            else:
                # stats
                if eff_type.startswith("reduction"):
                    val_txt = f"• Réduction: {round(float(value)*100)} %"
                elif eff_type == "esquive":
                    val_txt = f"• Esquive: {round(float(value)*100)} %"
                elif eff_type == "immunite":
                    val_txt = "• Immunité: active"
                else:
                    val_txt = f"• Valeur: {value}"

            parts = [f"**{label}**", val_txt, f"• Reste: {_format_duration(remain)}"]
            if tick: parts.append(tick)
            if src: parts.append(src)

            lines.append("\n".join(parts))

        emb = discord.Embed(
            title=f"🩺 Effets actifs pour {itx.user.display_name}",
            description="\n\n".join(lines),
            color=discord.Color.teal()
        )
        await itx.followup.send(embed=emb, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(PassifsCog(bot))

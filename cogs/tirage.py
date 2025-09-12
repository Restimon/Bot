# cogs/tirage.py
import time
from typing import Dict, Tuple

import discord
from discord import app_commands, Embed, Colour, Interaction
from discord.ext import commands

from gacha_db import (
    init_gacha_db, can_draw_daily, stamp_daily,
    get_tickets, consume_ticket, add_personnage, get_collection
)

# on utilise ton module personnages
import personnage as PERSO

def _fmt_cooldown(seconds: int) -> str:
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    parts = []
    if h: parts.append(f"{h}h")
    if m: parts.append(f"{m}m")
    if s or not parts: parts.append(f"{s}s")
    return " ".join(parts)

def _embed_pull(user: discord.abc.User, rarete: str, p: Dict) -> Embed:
    desc = p.get("description", "")
    faction = p.get("faction", "?")
    passif = p.get("passif", {})
    passif_nom = passif.get("nom", "—")
    passif_effet = passif.get("effet", "")
    image = p.get("image")

    emb = Embed(
        title=f"🎰 Tirage — {p.get('nom', 'Inconnu')}",
        description=desc or "—",
        colour={
            "Commun": Colour.light_grey(),
            "Rare": Colour.blue(),
            "Épique": Colour.purple(),
            "Légendaire": Colour.gold()
        }.get(rarete, Colour.blurple())
    )
    emb.add_field(name="Rareté", value=rarete, inline=True)
    emb.add_field(name="Faction", value=faction, inline=True)
    emb.add_field(name="Passif", value=f"**{passif_nom}**\n{passif_effet}"[:1024], inline=False)
    if image:
        emb.set_thumbnail(url=f"attachment://card.png")  # si tu envoies un fichier
    emb.set_footer(text=f"GotValis • Collection de {user.display_name}")
    return emb

class Tirage(commands.Cog):
    """Système de tirage (gacha) : daily non-cumulable + tickets."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        await init_gacha_db()

    # ----------- Tirage Daily (non cumulable, cooldown 24h rolling) -----------
    @app_commands.command(name="tirage", description="Effectue ton tirage quotidien (non cumulable).")
    async def tirage(self, itx: Interaction):
        ok, remaining = await can_draw_daily(itx.user.id)
        if not ok:
            return await itx.response.send_message(
                f"⏳ Ton tirage quotidien n’est pas encore prêt. Reviens dans **{_fmt_cooldown(remaining)}**.",
                ephemeral=True
            )

        # Tirage via personnage.py
        rarete, p = PERSO.tirage_personnage()  # (rarete, dict)
        if not p:
            return await itx.response.send_message("❌ Aucun personnage disponible à tirer.", ephemeral=True)

        # Sauvegarde collection + timestamp cooldown
        await add_personnage(itx.user.id, p["nom"], 1)
        await stamp_daily(itx.user.id)

        # Envoi embed (avec image si tu veux l’attacher)
        files = []
        image_path = p.get("image")
        embed = _embed_pull(itx.user, rarete, p)
        if image_path and isinstance(image_path, str):
            try:
                files.append(discord.File(image_path, filename="card.png"))
            except Exception:
                # si le fichier n'est pas accessible, on ignore l'attachement
                pass

        await itx.response.send_message(embed=embed, files=files if files else None)

    # ----------- Tirage via Ticket -----------
    @app_commands.command(name="tirage_ticket", description="Utilise un ticket de tirage pour tirer un personnage.")
    async def tirage_ticket(self, itx: Interaction):
        # Consommer un ticket (économie/shop branchés plus tard pour en gagner)
        has = await consume_ticket(itx.user.id)
        if not has:
            return await itx.response.send_message(
                "🎟️ Tu n’as pas de **ticket**. (Tu pourras en acheter plus tard dans le shop.)",
                ephemeral=True
            )

        rarete, p = PERSO.tirage_personnage()
        if not p:
            return await itx.response.send_message("❌ Aucun personnage disponible à tirer.", ephemeral=True)

        await add_personnage(itx.user.id, p["nom"], 1)

        files = []
        image_path = p.get("image")
        embed = _embed_pull(itx.user, rarete, p)
        if image_path and isinstance(image_path, str):
            try:
                files.append(discord.File(image_path, filename="card.png"))
            except Exception:
                pass

        await itx.response.send_message(embed=embed, files=files if files else None)

    # ----------- Voir ses Tickets -----------
    @app_commands.command(name="tickets", description="Affiche combien de tickets de tirage tu possèdes.")
    async def tickets(self, itx: Interaction, user: discord.User | None = None):
        target = user or itx.user
        n = await get_tickets(target.id)
        await itx.response.send_message(
            f"🎟️ Tickets de {target.mention} : **{n}**.",
            ephemeral=(target.id == itx.user.id)
        )

    # ----------- Collection -----------
    @app_commands.command(name="collection", description="Affiche ta collection de personnages.")
    async def collection(self, itx: Interaction, user: discord.User | None = None):
        target = user or itx.user
        rows = await get_collection(target.id)
        if not rows:
            return await itx.response.send_message(f"{target.mention} n’a encore **aucun** personnage.", ephemeral=True)

        # on structure par rareté pour un affichage clean
        by_rarity: Dict[str, list[str]] = {"Commun": [], "Rare": [], "Épique": [], "Légendaire": []}
        for nom, qty in rows:
            p = PERSO.get_par_nom(nom)
            rarete = p.get("rarete") if p else "Commun"
            label = f"{nom} × **{qty}**"
            by_rarity.setdefault(rarete, []).append(label)

        emb = Embed(
            title=f"🗂️ Collection de {target.display_name}",
            colour=Colour.blurple()
        )
        for rarete in PERSO.RARETES:
            lst = by_rarity.get(rarete) or []
            if lst:
                emb.add_field(name=rarete, value="\n".join(lst)[:1024], inline=False)

        await itx.response.send_message(embed=emb, ephemeral=(target.id == itx.user.id))


async def setup(bot: commands.Bot):
    await bot.add_cog(Tirage(bot))

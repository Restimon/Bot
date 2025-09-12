# cogs/tirage.py
import discord
from discord import app_commands, Embed, Colour, Interaction
from discord.ext import commands

import personnage as PERSO
from gacha_db import (
    init_gacha_db,
    consume_ticket, get_tickets,
    add_personnage, get_collection
)

def _embed_pull(user: discord.abc.User, rarete: str, p: dict) -> Embed:
    desc = p.get("description", "")
    faction = p.get("faction", "?")
    passif = p.get("passif", {})
    passif_nom = passif.get("nom", "—")
    passif_effet = passif.get("effet", "")

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
    emb.set_footer(text=f"GotValis • Collection de {user.display_name}")
    return emb

class Tirage(commands.Cog):
    """Tirage via tickets + solde tickets + collection."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        await init_gacha_db()

    # ----------- /tirage : consomme 1 ticket et tire un perso -----------
    @app_commands.command(name="tirage", description="Utilise un ticket de tirage pour obtenir un personnage.")
    async def tirage(self, itx: Interaction):
        # Consommer 1 ticket
        ok = await consume_ticket(itx.user.id)
        if not ok:
            cur = await get_tickets(itx.user.id)
            return await itx.response.send_message(
                f"❌ Tu n’as pas de ticket. (Tickets actuels : **{cur}**) "
                f"→ utilise `/daily` ou achète-en via le shop.",
                ephemeral=True
            )

        # Tirage
        rarete, p = PERSO.tirage_personnage()
        if not p:
            return await itx.response.send_message("❌ Aucun personnage disponible à tirer.", ephemeral=True)

        await add_personnage(itx.user.id, p["nom"], 1)

        # Embed + image si dispo
        files = []
        embed = _embed_pull(itx.user, rarete, p)
        image_path = p.get("image")
        if image_path and isinstance(image_path, str):
            try:
                files.append(discord.File(image_path, filename="card.png"))
                embed.set_thumbnail(url="attachment://card.png")
            except Exception:
                pass

        await itx.response.send_message(embed=embed, files=files if files else None)

    # ----------- /tickets : solde de tickets -----------
    @app_commands.command(name="tickets", description="Affiche le nombre de tickets de tirage.")
    async def tickets(self, itx: Interaction, user: discord.User | None = None):
        target = user or itx.user
        n = await get_tickets(target.id)
    
        emb = Embed(
            title="🎟️ Tickets de tirage",
            description=(
                f"{target.mention} possède **{n}** ticket(s).\n\n"
                "💡 Tu peux en obtenir 1 chaque jour avec la commande `/daily`, "
                "ou en acheter dans le shop."
            ),
            colour=Colour.blurple()
        )
        emb.set_footer(text="GotValis • Inventaire")
    
        await itx.response.send_message(
            embed=emb,
            ephemeral=(target.id == itx.user.id)
        )

    # ----------- /collection : liste des personnages obtenus -----------
    @app_commands.command(name="collection", description="Affiche ta collection de personnages par rareté.")
    async def collection(self, itx: Interaction, user: discord.User | None = None):
        target = user or itx.user
        rows = await get_collection(target.id)  # [(nom, qty)]
        if not rows:
            return await itx.response.send_message(
                f"{target.mention} n’a encore **aucun** personnage.", ephemeral=True
            )

        by_rarity: dict[str, list[str]] = {r: [] for r in PERSO.RARETES}
        for nom, qty in rows:
            p = PERSO.get_par_nom(nom)
            rarete = p.get("rarete") if p else "Commun"
            by_rarity.setdefault(rarete, []).append(f"{nom} × **{qty}**")

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

# cogs/daily.py
import discord
from discord import app_commands, Embed, Colour, Interaction
from discord.ext import commands

from gacha_db import init_gacha_db, can_draw_daily, stamp_daily, add_personnage
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

def _embed_pull(user: discord.abc.User, rarete: str, p: dict) -> Embed:
    desc = p.get("description", "")
    faction = p.get("faction", "?")
    passif = p.get("passif", {})
    passif_nom = passif.get("nom", "—")
    passif_effet = passif.get("effet", "")
    image = p.get("image")

    emb = Embed(
        title=f"🎁 Daily — {p.get('nom', 'Inconnu')}",
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
        emb.set_thumbnail(url=f"attachment://card.png")
    emb.set_footer(text=f"GotValis • Daily de {user.display_name}")
    return emb

class Daily(commands.Cog):
    """Tirage quotidien (non cumulable, cooldown 24h)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        await init_gacha_db()

    @app_commands.command(name="daily", description="Effectue ton tirage quotidien (gratuit, non cumulable).")
    async def daily(self, itx: Interaction):
        ok, remaining = await can_draw_daily(itx.user.id)
        if not ok:
            return await itx.response.send_message(
                f"⏳ Ton daily n’est pas prêt. Reviens dans **{_fmt_cooldown(remaining)}**.",
                ephemeral=True
            )

        rarete, p = PERSO.tirage_personnage()
        if not p:
            return await itx.response.send_message("❌ Aucun personnage disponible à tirer.", ephemeral=True)

        await add_personnage(itx.user.id, p["nom"], 1)
        await stamp_daily(itx.user.id)

        files = []
        image_path = p.get("image")
        embed = _embed_pull(itx.user, rarete, p)
        if image_path and isinstance(image_path, str):
            try:
                files.append(discord.File(image_path, filename="card.png"))
            except Exception:
                pass

        await itx.response.send_message(embed=embed, files=files if files else None)

async def setup(bot: commands.Bot):
    await bot.add_cog(Daily(bot))

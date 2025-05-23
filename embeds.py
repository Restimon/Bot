import discord
from utils import OBJETS, GIFS

def build_embed_from_item(item, description, is_heal_other=False, is_crit=False):
    embed = discord.Embed(
        title=f"{item} Action de SomniCorp",
        description=description,
        color=discord.Color.green() if is_heal_other else discord.Color.red()
    )

    # Choix du GIF à afficher
    gif_url = None
    if is_crit:
        gif_url = GIFS.get("critique")
    elif item in GIFS:
        gif_url = GIFS[item]
    elif OBJETS.get(item, {}).get("type") == "soin" and is_heal_other:
        gif_url = GIFS.get("soin_autre")
    elif description.startswith("💨"):
        gif_url = GIFS.get("esquive")

    if gif_url:
        embed.set_image(url=gif_url)

    return embed

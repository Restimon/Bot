import discord
from utils import OBJETS

GIFS = {
    "❄️": "https://media4.giphy.com/media/v1.Y2lkPTc5MGI3NjExY3NlcTYyZDVkMjhpY3dpbmVhaXB2OXRoZGNxMHp2d3dnMmhldWR4OSZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/sTUe8s1481gY0/giphy.gif",
    "🪓": "https://media.giphy.com/media/oFVr84BOpjyiA/giphy.gif",
    "🔥": "https://i.gifer.com/MV3z.gif",
    "⚡": "https://act-webstatic.hoyoverse.com/upload/contentweb/2023/02/02/9ed221220865a923de00661f5f9e7dea_7010733949792563480.gif",
    "🔫": "https://media3.giphy.com/media/10ZuedtImbopos/giphy.gif",
    "🧨": "https://media.giphy.com/media/oe33xf3B50fsc/giphy.gif",
    "☠️": "https://media4.giphy.com/media/v1.Y2lkPTc5MGI3NjExYm1kMTg4OWw0Y2s0cjludThsajgycmlsbHNoM2Ixc3k0MTdncG1obSZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/e37RbTLYjfc1q/giphy.gif",
    "🦠": "https://media.giphy.com/media/7htcRg2IORvgKBKryu/giphy.gif",
    "🧪": "https://media.giphy.com/media/9lHsP26ijVJwylXsff/giphy.gif",
    "🧟": "https://media.giphy.com/media/10bKG23wIFlKmc/giphy.gif",
    "🍀": "https://i.makeagif.com/media/9-05-2023/UUHN2G.gif",
    "🩸": "https://media.giphy.com/media/jN07m6w9uuZAeh80z0/giphy.gif",
    "🩹": "https://media.giphy.com/media/EwKe1XdABwk2yvTyQt/giphy.gif",
    "💊": "https://64.media.tumblr.com/858f7aa3c8cee743d61a5ff4d73a378f/tumblr_n2mzr2nf7C1sji00bo1_500.gifv",
    "💕": "https://media.giphy.com/media/v1.Y2lkPWVjZjA1ZTQ3dG1pdXd6OXkyYnR4cXk0cjdxdDRxNGJyYWZjdG1wcTk1NWY2eGducSZlcD12MV9naWZzX3NlYXJjaCZjdD1n/1FqyIw2lMKT2U/giphy.gif",
    "💉": "https://media.giphy.com/media/s8oHUwsjS8w5OD7Sg7/giphy.gif",
    "🔍": "https://media.giphy.com/media/1fih1TYYBONo0Dkdmx/giphy.gif",
    "⭐️": "https://media.giphy.com/media/9tz1MAa6NzMDhXiD00/giphy.gif",
    "🪖": "https://media.giphy.com/media/VxHixRra5rtEMMw7b0/giphy.gif",
    "🛡": "https://media.giphy.com/media/rR7wrU76zfWnf7xBDR/giphy.gif",
    "👟": "https://media.giphy.com/media/EBiho5DrxUQ75JMcq7/giphy.gif",
    "soin_autre": "https://media.giphy.com/media/Mxb7h4hq6mJNzWNF5W/giphy.gif",
    "critique": "https://media.giphy.com/media/o2TqK6vEzhp96/giphy.gif",
    "esquive": "https://media.giphy.com/media/eIm624c8nnNbiG0V3g/giphy.gif"
}

def build_embed_from_item(item, description, is_heal_other=False, is_crit=False, disable_gif=False, custom_title=None):
    embed = discord.Embed(
        title=custom_title or f"{item} Action de GotValis",
        description=description,
        color=discord.Color.green() if is_heal_other or OBJETS.get(item, {}).get("type") == "soin" else discord.Color.red()
    )

    if disable_gif:
        return embed

    gif_url = None

    # On met en priorité le GIF de soin (toujours normal même si critique)
    if OBJETS.get(item, {}).get("type") == "soin":
        gif_url = GIFS.get("soin_autre") if is_heal_other else GIFS.get(item)

    # Sinon pour attaque critique on met le GIF critique
    elif is_crit:
        gif_url = GIFS.get("critique")

    # Cas spécial esquive
    elif description.startswith("💨"):
        gif_url = GIFS.get("esquive")

    # Sinon GIF standard de l'item si dispo
    elif item in GIFS:
        gif_url = GIFS[item]

    if gif_url:
        embed.set_image(url=gif_url)

    return embed

def build_embed_transmission_virale(from_user_mention, to_user_mention, pv_avant, pv_apres):
    return discord.Embed(
        title="💉 Transmission virale",
        description=(
            f"{from_user_mention} confirme une transmission virale : {to_user_mention} est désormais infecté.\n"
            f"🦠 Le virus a été retiré de {from_user_mention}, qui perd 2 PV ({pv_avant} → {pv_apres})."
        ),
        color=0x55ffff
    )

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

def build_embed_from_item(item, description, is_heal_other=False, is_crit=False):
    embed = discord.Embed(
        title=f"{item} Action de GotValis",
        description=description,
        color=discord.Color.green() if is_heal_other else discord.Color.red()
    )

    # Choix du GIF à afficher
    gif_url = None
    if is_crit and not is_heal_other:
        embed.set_image(url=GIFS.get("💥"))
    elif OBJETS.get(item, {}).get("type") == "soin":
        if is_heal_other:
            gif_url = GIFS.get("soin_autre")
        else:
            gif_url = GIFS.get(item)
    elif description.startswith("💨"):
        gif_url = GIFS.get("esquive")
    elif item in GIFS:
        gif_url = GIFS[item]

    if gif_url:
        embed.set_image(url=gif_url)

    return embed

def build_embed_transmission_virale(attacker, target, pv_avant, pv_apres):
    return discord.Embed(
        title="💉 Transmission virale",
        description=(
            f"{attacker} confirme une transmission virale : {target} est désormais infecté.\n"
            f"🦠 Le virus a été retiré de {attacker}, qui perd 2 PV ({pv_avant} → {pv_apres})."
        ),
        color=0x55ffff
    )

import discord
from utils import OBJETS

GIFS = {
    "❄️": "https://media4.giphy.com/media/v1.Y2lkPTc5MGI3NjExY3NlcTYyZDVkMjhpY3dpbmVhaXB2OXRoZGNxMHp2d3dnMmhldWR4OSZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/sTUe8s1481gY0/giphy.gif",
    "🪓": "https://media.giphy.com/media/oFVr84BOpjyiA/giphy.gif?cid=ecf05e47gwzwh637iu0dhwjgzh8hm1leeettft94zqx4qbxn&ep=v1_gifs_search&rid=giphy.gif&ct=g",
    "🔥": "https://i.gifer.com/MV3z.gif",
    "⚡": "https://act-webstatic.hoyoverse.com/upload/contentweb/2023/02/02/9ed221220865a923de00661f5f9e7dea_7010733949792563480.gif",
    "🔫": "https://media3.giphy.com/media/v1.Y2lkPTc5MGI3NjExc3NocHU2aGE5Nm0yM3NjdGF1OGR1MmRrZGp3d20ycGowcGM4Nm5ibyZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/10ZuedtImbopos/giphy.gif",
    "🧨": "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExenF3eHlsd2E5N3R3enNleHFoNzUwd2Iyc2NtdnBnZnprbjBjaWV1byZlcD12MV9naWZzX3NlYXJjaCZjdD1n/oe33xf3B50fsc/giphy.gif",
    "🦠": "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExYjN5aTJzYmhma2trYzhpcWpxaTQxMHE1dHEyZzcyZXlpMGFhNTI2eiZlcD12MV9naWZzX3NlYXJjaCZjdD1n/7htcRg2IORvgKBKryu/giphy.gif",
    "🧪": "https://media2.giphy.com/media/v1.Y2lkPTc5MGI3NjExbHFhOG0zaTQxaDQ5a2JndWVxMm0yc3BmOGRlaXVubDdqdGJheHNhdyZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/9lHsP26ijVJwylXsff/giphy.gif",
    "🧟": "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExZGcyNjVzYWwxamNhN29sOHFidGRtcWg0bnEweWR0bXE0dW9sbWI3bCZlcD12MV9naWZzX3NlYXJjaCZjdD1n/10bKG23wIFlKmc/giphy.gif",
    "🍀": "https://i.makeagif.com/media/9-05-2023/UUHN2G.gif",
    "🩸": "https://media.giphy.com/media/jN07m6w9uuZAeh80z0/giphy.gif?cid=ecf05e474yl44a4sx6ndpqcajubfga6xbcy4y5w8dgclucck&ep=v1_gifs_search&rid=giphy.gif&ct=g",
    "🩹": "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExcGk1b205enk4MXpzcWp0MjV5YjdrNHM0ODZheWxzOGRicTZ1eTJubiZlcD12MV9naWZzX3NlYXJjaCZjdD1n/EwKe1XdABwk2yvTyQt/giphy.gif",
    "💊": "https://64.media.tumblr.com/858f7aa3c8cee743d61a5ff4d73a378f/tumblr_n2mzr2nf7C1sji00bo1_500.gifv",
    "💉": "https://media.giphy.com/media/s8oHUwsjS8w5OD7Sg7/giphy.gif?cid=ecf05e47x77gai11gsj891f8jfzuntwv0detkk5p8vci8ig3&ep=v1_gifs_search&rid=giphy.gif&ct=g",
    "🔍": "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExZHpjbGI0dHRueHAwemhvY2Ztd2NjdHVqdnZka2lueHM3c2E3amtmMCZlcD12MV9naWZzX3NlYXJjaCZjdD1n/1fih1TYYBONo0Dkdmx/giphy.gif",
    "⭐️": "https://media4.giphy.com/media/v1.Y2lkPTc5MGI3NjExYm5od3Z4YXpubGRib3FkNTF5bTJiejczejFoOXpzemZxaXhkZmhpayZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/9tz1MAa6NzMDhXiD00/giphy.gif",
    "🪖": "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExcWFqa2Uzd25uM3dsMjd0eGs4a2xtdTJpaW0wajFrZ3Nlc3RjanM2eiZlcD12MV9naWZzX3NlYXJjaCZjdD1n/VxHixRra5rtEMMw7b0/giphy.gif",
    "🛡": "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExMDBmZzY3bXdpeWNncnVnMHNieW45dHVpZnRpOWM1bW9qcDhtYm5kMSZlcD12MV9naWZzX3NlYXJjaCZjdD1n/rR7wrU76zfWnf7xBDR/giphy.gif",
    "👟": "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExenJtZmFoem13aGwxNTVwYzVrc3k0cG00enBkZ3lxeHV2MTVjeTBoNSZlcD12MV9naWZzX3NlYXJjaCZjdD1n/EBiho5DrxUQ75JMcq7/giphy.gif",
    "☠️": "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExMDdqb2R0eWJvZzh4eXJuZXNuYmJjZDZzeWxtZDF3Zjg2bmpsMHpsbCZlcD12MV9naWZzX3NlYXJjaCZjdD1n/qtkfPuvX4wrSuW5Q4T/giphy.gif",
    "soin_autre": "https://media2.giphy.com/media/v1.Y2lkPTc5MGI3NjExcDVwc21sMTQ5MGF2bjRrazdmdHJpMmFoNGgzeGxtazF4Mnl6MHByNyZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/Mxb7h4hq6mJNzWNF5W/giphy.gif",
    "critique": "https://media0.giphy.com/media/v1.Y2lkPTc5MGI3NjExcnRsZDZzNmUxM3N4OHVqbXhmOWUxbzVjOGkyeTR2cW1tMHlzamxnbCZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/o2TqK6vEzhp96/giphy.gif",
    "esquive": "https://media2.giphy.com/media/v1.Y2lkPTc5MGI3NjExNHdzZDd6eHhyMHZqdmZnMGg5ZXoybnMwM3g5NzgwbXVuNjFqNjI4dCZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/eIm624c8nnNbiG0V3g/giphy.gif"
}

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

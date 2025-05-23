import discord

def build_embed_from_item(item_emoji, description, is_heal_other=False, is_crit=False):
    embed = discord.Embed(
        title=f"{item_emoji} Action",
        description=description,
        color=discord.Color.green() if "soigne" in description or "protégé" in description else discord.Color.red()
    )

    if is_heal_other:
        embed.set_footer(text="Soin sur une autre personne")
    if is_crit:
        embed.set_footer(text="Coup critique !")

    return embed

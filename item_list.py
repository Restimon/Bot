from discord import app_commands
from discord.ext import commands
import discord
from utils import OBJETS

@bot.tree.command(name="item", description="Voir les objets disponibles")
@app_commands.describe(option="Option à afficher")
async def item_slash(interaction: discord.Interaction, option: str):
    if option.lower() != "liste":
        await interaction.response.send_message("❌ Utilisez `/item liste` pour voir tous les objets.", ephemeral=True)
        return

    await interaction.response.defer(thinking=True)

    objets_par_page = 10
    objets = list(OBJETS.items())
    total_pages = (len(objets) + objets_par_page - 1) // objets_par_page

    embeds = []
    for i in range(total_pages):
        start = i * objets_par_page
        end = start + objets_par_page
        objets_page = objets[start:end]

        embed = discord.Embed(
            title=f"📦 Liste des objets (Page {i+1}/{total_pages})",
            description="Voici la liste complète des objets disponibles :",
            color=discord.Color.blurple()
        )
        for nom, data in objets_page:
            desc = data.get("description", "Aucune description.")
            embed.add_field(name=nom, value=desc, inline=False)

        embeds.append(embed)

    current_page = 0
    message = await interaction.followup.send(embed=embeds[current_page], ephemeral=True)

    if total_pages <= 1:
        return

    await message.add_reaction("⬅️")
    await message.add_reaction("➡️")

    def check(reaction, user):
        return user == interaction.user and str(reaction.emoji) in ["⬅️", "➡️"] and reaction.message.id == message.id

    while True:
        try:
            reaction, user = await bot.wait_for("reaction_add", timeout=60.0, check=check)
            if str(reaction.emoji) == "⬅️" and current_page > 0:
                current_page -= 1
                await message.edit(embed=embeds[current_page])
            elif str(reaction.emoji) == "➡️" and current_page < total_pages - 1:
                current_page += 1
                await message.edit(embed=embeds[current_page])
            await message.remove_reaction(reaction.emoji, user)
        except asyncio.TimeoutError:
            break

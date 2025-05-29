import discord
from discord import app_commands
from discord.ext import commands
from utils import OBJETS
import asyncio

def generate_description(obj):
    typ = obj.get("type")
    if typ == "attaque":
        return f"Inflige {obj.get('degats')} dégâts. (Crit {int(obj.get('crit', 0)*100)}%)"
    if typ == "attaque_chaine":
        return f"Attaque en chaîne : 24 + 2×12 dégâts. (Crit {int(obj.get('crit', 0)*100)}%)"
    if typ == "virus":
        return "Virus : 5 dégâts initiaux, puis 5/h pendant 6h."
    if typ == "poison":
        return "Poison : 3 dégâts toutes les 30 min pendant 3h."
    if typ == "infection":
        return "Infection : 5 dégâts initiaux + 2/30min pendant 3h. 25 % de propagation."
    if typ == "soin":
        return f"Restaure {obj.get('soin')} PV. (Crit {int(obj.get('crit', 0)*100)}%)"
    if typ == "regen":
        return "Régénère 3 PV toutes les 30 min pendant 3h."
    if typ == "mysterybox":
        return "Boîte surprise : 1 à 3 objets aléatoires."
    if typ == "vol":
        return "Vole un objet aléatoire à un autre joueur."
    if typ == "vaccin":
        return "Utilisable via /heal pour soigner du virus."
    if typ == "bouclier":
        return "Ajoute un bouclier de 20 PV."
    if typ == "esquive+":
        return "Augmente les chances d’esquive pendant 3h."
    if typ == "reduction":
        return "Réduit les dégâts subis de moitié pendant 4h."
    if typ == "immunite":
        return "Immunité : ignore tous les dégâts pendant 2h."
    return "❓ Effet inconnu."

def register_item_command(bot: commands.Bot):
    @bot.tree.command(name="item", description="Voir tous les objets disponibles")
    async def item_liste(interaction: discord.Interaction):
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
                desc = generate_description(data)
                embed.add_field(name=nom, value=desc, inline=False)

            embeds.append(embed)

        current_page = 0
        message = await interaction.followup.send(embed=embeds[current_page], ephemeral=True)

        if total_pages <= 1:
            return

        await message.add_reaction("⬅️")
        await message.add_reaction("➡️")

        def check(reaction, user):
            return (
                user == interaction.user
                and str(reaction.emoji) in ["⬅️", "➡️"]
                and reaction.message.id == message.id
            )

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

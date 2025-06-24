import discord
from discord import app_commands
from discord.ext import commands

from economy import retirer_gotcoins, ajouter_gotcoins, get_gotcoins
from storage import inventaire
from data import sauvegarder
from personnage import PERSONNAGES

ITEMS_CATALOGUE = {
    "❄️": {"achat": 2, "vente": 0},
    "🪓": {"achat": 6, "vente": 1},
    "🔥": {"achat": 10, "vente": 2},
    "⚡": {"achat": 20, "vente": 5},
    "🔫": {"achat": 30, "vente": 7},
    "🧨": {"achat": 40, "vente": 10},
    "☠️": {"achat": 60, "vente": 12},
    "🦠": {"achat": 40, "vente": 20},
    "🧪": {"achat": 30, "vente": 15},
    "🧟": {"achat": 55, "vente": 27},
    "🍀": {"achat": 4, "vente": 1},
    "🩸": {"achat": 12, "vente": 3},
    "🩹": {"achat": 18, "vente": 4},
    "💊": {"achat": 30, "vente": 7},
    "💕": {"achat": 25, "vente": 5},
    "📦": {"achat": 32, "vente": 8},
    "🔍": {"achat": 28, "vente": 7},
    "💉": {"achat": 34, "vente": 8},
    "🛡": {"achat": 36, "vente": 9},
    "👟": {"achat": 28, "vente": 7},
    "🪖": {"achat": 32, "vente": 8},
    "⭐️": {"achat": 44, "vente": 11},
    "🎟️": {"achat": 200, "vente": 0}
}

RARETE_PRIX_VENTE = {
    "commun": 100,
    "rare": 200,
    "epique": 300,
    "legendaire": 500
}

class Shop(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="shop", description="Affiche les objets disponibles à l'achat.")
    async def shop(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🛒 Boutique GotValis",
            description="Voici les objets disponibles à l'achat :",
            color=discord.Color.green()
        )
        for item, data in ITEMS_CATALOGUE.items():
            embed.add_field(name=f"{item}", value=f"Achat : {data['achat']} GC", inline=True)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="acheter", description="Achète un objet avec tes GotCoins.")
    @app_commands.describe(item="Emoji de l'objet à acheter", quantite="Quantité à acheter (par défaut : 1)")
    async def acheter(self, interaction: discord.Interaction, item: str, quantite: int = 1):
        user = interaction.user
        guild_id = str(interaction.guild_id)
        user_id = str(user.id)

        if item not in ITEMS_CATALOGUE:
            await interaction.response.send_message("❌ Cet objet n'existe pas dans la boutique.", ephemeral=True)
            return

        prix_total = ITEMS_CATALOGUE[item]["achat"] * quantite
        solde = get_gotcoins(guild_id, user_id)

        if solde < prix_total:
            await interaction.response.send_message(f"❌ Tu n'as pas assez de GotCoins. Il te faut {prix_total} GC.", ephemeral=True)
            return

        retirer_gotcoins(guild_id, user_id, prix_total)
        ajouter_gotcoins(guild_id, "gotvalis", prix_total)
        inventaire.setdefault(guild_id, {}).setdefault(user_id, {}).setdefault(item, 0)
        inventaire[guild_id][user_id][item] += quantite
        sauvegarder()

        await interaction.response.send_message(f"✅ Tu as acheté {quantite}x {item} pour {prix_total} GC.", ephemeral=True)

    @app_commands.command(name="vendre", description="Vend un objet ou un personnage.")
    @app_commands.describe(objet="Emoji de l'objet à vendre ou nom du personnage", quantite="Quantité à vendre (objets seulement)")
    async def vendre(self, interaction: discord.Interaction, objet: str, quantite: int = 1):
        user = interaction.user
        guild_id = str(interaction.guild_id)
        user_id = str(user.id)
        inventaire_user = inventaire.get(guild_id, {}).get(user_id, {})

        if objet in ITEMS_CATALOGUE:
            if quantite <= 0 or inventaire_user.get(objet, 0) < quantite:
                await interaction.response.send_message("❌ Tu n'as pas assez de cet objet à vendre.", ephemeral=True)
                return

            montant = ITEMS_CATALOGUE[objet]["vente"] * quantite
            inventaire_user[objet] -= quantite
            if inventaire_user[objet] <= 0:
                del inventaire_user[objet]
            ajouter_gotcoins(guild_id, user_id, montant)
            sauvegarder()
            await interaction.response.send_message(f"✅ Tu as vendu {quantite}x {objet} pour {montant} GC.", ephemeral=True)

        else:
            nom_normalise = objet.lower()
            for perso in PERSONNAGES.values():
                if perso["nom"].lower() == nom_normalise:
                    rarete = perso["rarete"].lower()
                    montant = RARETE_PRIX_VENTE.get(rarete, 0)
                    perso_list = inventaire_user.get("personnages", [])
                    if perso["nom"] not in perso_list:
                        await interaction.response.send_message("❌ Tu ne possèdes pas ce personnage.", ephemeral=True)
                        return
                    perso_list.remove(perso["nom"])
                    ajouter_gotcoins(guild_id, user_id, montant)
                    sauvegarder()
                    await interaction.response.send_message(f"✅ Tu as vendu {perso['nom']} ({rarete.title()}) pour {montant} GC.", ephemeral=True)
                    return

            await interaction.response.send_message("❌ Cet objet ou personnage est inconnu.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Shop(bot))

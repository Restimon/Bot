# shop.py
import discord
from discord import app_commands
from discord.ext import commands

from economy import retirer_gotcoins, ajouter_gotcoins, get_gotcoins
from storage import get_user_data  # ← on utilise la vraie API (inventaire = liste)
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

        if quantite <= 0:
            await interaction.response.send_message("❌ Quantité invalide.", ephemeral=True)
            return

        prix_total = ITEMS_CATALOGUE[item]["achat"] * quantite
        solde = get_gotcoins(guild_id, user_id)

        if solde < prix_total:
            await interaction.response.send_message(
                f"❌ Tu n'as pas assez de GotCoins. Il te faut {prix_total} GC.",
                ephemeral=True
            )
            return

        # Paiement
        retirer_gotcoins(guild_id, user_id, prix_total)
        # Créditer la "banque" (si tu tiens ce flux)
        ajouter_gotcoins(guild_id, "gotvalis", prix_total)

        # Ajout dans l'inventaire (liste)
        inv, _, _ = get_user_data(guild_id, user_id)
        inv.extend([item] * quantite)
        sauvegarder()

        await interaction.response.send_message(
            f"✅ Tu as acheté {quantite}x {item} pour {prix_total} GC.",
            ephemeral=True
        )

    @app_commands.command(name="vendre", description="Vend un objet ou un personnage.")
    @app_commands.describe(objet="Emoji de l'objet à vendre ou nom du personnage", quantite="Quantité à vendre (objets seulement)")
    async def vendre(self, interaction: discord.Interaction, objet: str, quantite: int = 1):
        user = interaction.user
        guild_id = str(interaction.guild_id)
        user_id = str(user.id)
        inv, _, _ = get_user_data(guild_id, user_id)

        # --- Vente d'OBJET (emoji) ---
        if objet in ITEMS_CATALOGUE:
            if quantite <= 0:
                await interaction.response.send_message("❌ Quantité invalide.", ephemeral=True)
                return

            # Compter combien l'utilisateur en a dans SA LISTE
            possedes = sum(1 for i in inv if i == objet)
            if possedes < quantite:
                await interaction.response.send_message(
                    "❌ Tu n'as pas assez de cet objet à vendre.",
                    ephemeral=True
                )
                return

            montant = ITEMS_CATALOGUE[objet]["vente"] * quantite

            # Retirer 'quantite' occurrences de l'emoji dans la liste
            a_retirer = quantite
            new_inv = []
            for i in inv:
                if i == objet and a_retirer > 0:
                    a_retirer -= 1
                else:
                    new_inv.append(i)
            # Remplacer le contenu de la liste en place
            inv.clear()
            inv.extend(new_inv)

            # Créditer
            ajouter_gotcoins(guild_id, user_id, montant)
            sauvegarder()

            await interaction.response.send_message(
                f"✅ Tu as vendu {quantite}x {objet} pour {montant} GC.",
                ephemeral=True
            )
            return

        # --- Vente de PERSONNAGE (par nom) ---
        nom_normalise = objet.strip().lower()
        perso = next((p for p in PERSONNAGES.values() if p["nom"].lower() == nom_normalise), None)

        if not perso:
            await interaction.response.send_message("❌ Cet objet ou personnage est inconnu.", ephemeral=True)
            return

        # Trouver un item {"personnage": "Nom"} dans la liste d'inventaire
        index = next((idx for idx, it in enumerate(inv)
                      if isinstance(it, dict) and it.get("personnage") == perso["nom"]), None)

        if index is None:
            await interaction.response.send_message("❌ Tu ne possèdes pas ce personnage.", ephemeral=True)
            return

        rarete = perso["rarete"].lower()
        montant = RARETE_PRIX_VENTE.get(rarete, 0)

        # Retirer 1 exemplaire du personnage
        inv.pop(index)
        ajouter_gotcoins(guild_id, user_id, montant)
        sauvegarder()

        await interaction.response.send_message(
            f"✅ Tu as vendu {perso['nom']} ({rarete.title()}) pour {montant} GC.",
            ephemeral=True
        )

async def setup(bot):
    await bot.add_cog(Shop(bot))

# --- compat : certains main.py appellent encore register_shop_commands(bot)
def register_shop_commands(bot):
    """
    Compatibilité avec les anciens main.py qui appellent register_shop_commands(bot).
    Enregistre le Cog Shop, ce qui enregistre aussi ses slash commands.
    """
    try:
        bot.add_cog(Shop(bot))  # discord.py ≥2.x : add_cog est synchrone
    except TypeError:
        # Si l’environnement attend une coroutine, on bascule en tâche asynchrone
        import asyncio
        asyncio.create_task(bot.add_cog(Shop(bot)))

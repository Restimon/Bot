# shop.py
import discord
from discord import app_commands
from discord.ext import commands

from economy import retirer_gotcoins, ajouter_gotcoins, get_gotcoins
from storage import get_user_data, get_collection
from data import sauvegarder
from personnage import PERSONNAGES

# Catalogue d'objets achetables/vendables
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
    "🎟️": {"achat": 200, "vente": 0},  # Ticket de tirage (cumulable, consommé à l'usage)
}

# Prix de vente des personnages par rareté
# (clé normalisée en minuscules sans accents)
RARETE_PRIX_VENTE = {
    "commun": 100,
    "rare": 200,
    "epique": 300,
    "legendaire": 500,
}


def _normalize(s: str) -> str:
    """normalise 'Épique' -> 'epique', 'Légendaire' -> 'legendaire'"""
    if not isinstance(s, str):
        return ""
    s = s.strip().lower()
    # remplacements d'accents minimaux utilisés ici
    s = (
        s.replace("é", "e")
         .replace("è", "e")
         .replace("ê", "e")
         .replace("à", "a")
         .replace("ï", "i")
         .replace("î", "i")
         .replace("ô", "o")
         .replace("ù", "u")
         .replace("ç", "c")
    )
    return s


class Shop(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ======================
    # /shop
    # ======================
    @app_commands.command(name="shop", description="Affiche les objets disponibles à l'achat.")
    async def shop(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🛒 Boutique GotValis",
            description="Objets disponibles à l’achat (prix par unité) :",
            color=discord.Color.green(),
        )

        # on regroupe 4 par ligne pour lisibilité
        items = list(ITEMS_CATALOGUE.items())
        chunk = 4
        for i in range(0, len(items), chunk):
            block = items[i:i+chunk]
            value = "\n".join(f"{it} — **{data['achat']}** GC" for it, data in block)
            embed.add_field(name="\u200b", value=value, inline=True)

        embed.set_footer(text="Utilise /acheter pour acheter, /vendre pour revendre.")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ======================
    # /acheter
    # ======================
    @app_commands.command(name="acheter", description="Achète un objet avec tes GotCoins.")
    @app_commands.describe(item="Emoji de l'objet à acheter", quantite="Quantité (défaut : 1)")
    async def acheter(self, interaction: discord.Interaction, item: str, quantite: int = 1):
        await interaction.response.defer(ephemeral=True)

        user = interaction.user
        guild_id = str(interaction.guild_id)
        user_id = str(user.id)

        if item not in ITEMS_CATALOGUE:
            await interaction.followup.send("❌ Cet objet n'existe pas dans la boutique.")
            return

        if quantite <= 0:
            await interaction.followup.send("❌ Quantité invalide.")
            return

        prix_total = ITEMS_CATALOGUE[item]["achat"] * quantite
        solde = get_gotcoins(guild_id, user_id)

        if solde < prix_total:
            await interaction.followup.send(
                f"❌ Solde insuffisant. Il te faut **{prix_total} GC** (tu as {solde})."
            )
            return

        # Paiement
        retirer_gotcoins(guild_id, user_id, prix_total)

        # Ajout dans l'inventaire (liste d’emojis)
        inv, _, _ = get_user_data(guild_id, user_id)
        inv.extend([item] * quantite)

        sauvegarder()
        await interaction.followup.send(f"✅ Achat **{quantite}× {item}** pour **{prix_total} GC**.")

    # ======================
    # /vendre
    # ======================
    @app_commands.command(name="vendre", description="Vend un objet (emoji) ou un personnage (par nom).")
    @app_commands.describe(
        objet="Emoji de l'objet à vendre ou nom du personnage",
        quantite="Quantité (pour les OBJETS uniquement, par défaut : 1)"
    )
    async def vendre(self, interaction: discord.Interaction, objet: str, quantite: int = 1):
        await interaction.response.defer(ephemeral=True)

        user = interaction.user
        guild_id = str(interaction.guild_id)
        user_id = str(user.id)
        inv, _, _ = get_user_data(guild_id, user_id)

        # --- Vente d'OBJET (emoji) ---
        if objet in ITEMS_CATALOGUE:
            if quantite <= 0:
                await interaction.followup.send("❌ Quantité invalide.")
                return

            possedes = sum(1 for i in inv if i == objet)
            if possedes < quantite:
                await interaction.followup.send("❌ Tu n'as pas assez de cet objet à vendre.")
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
            inv.clear()
            inv.extend(new_inv)

            # Créditer le joueur
            if montant > 0:
                ajouter_gotcoins(guild_id, user_id, montant)

            sauvegarder()
            await interaction.followup.send(f"✅ Vente **{quantite}× {objet}** pour **{montant} GC**.")
            return

        # --- Vente de PERSONNAGE (par nom) ---
        # On cherche un perso par NOM exact (insensible à la casse/accents simplifiés)
        nom_requis_norm = _normalize(objet)
        perso = None
        for p in PERSONNAGES.values():
            if _normalize(p["nom"]) == nom_requis_norm:
                perso = p
                break

        if not perso:
            await interaction.followup.send("❌ Cet objet ou personnage est inconnu.")
            return

        # Accès à la collection (dict {nom: count})
        collection = get_collection(guild_id, user_id)
        count = collection.get(perso["nom"], 0)
        if count <= 0:
            await interaction.followup.send("❌ Tu ne possèdes pas ce personnage.")
            return

        # Prix selon rareté
        rarete_norm = _normalize(perso.get("rarete", ""))
        montant = RARETE_PRIX_VENTE.get(rarete_norm, 0)

        # Décrémenter la collection
        if count == 1:
            del collection[perso["nom"]]
        else:
            collection[perso["nom"]] = count - 1

        # Créditer
        if montant > 0:
            ajouter_gotcoins(guild_id, user_id, montant)

        sauvegarder()
        await interaction.followup.send(
            f"✅ Tu as vendu **{perso['nom']}** ({perso['rarete']}) pour **{montant} GC**."
        )


async def setup(bot):
    await bot.add_cog(Shop(bot))


def register_shop_commands(bot):
    """
    Compat pour les main.py qui appellent register_shop_commands(bot).
    """
    import asyncio
    cog = Shop(bot)
    try:
        result = bot.add_cog(cog)
        if asyncio.iscoroutine(result):
            asyncio.create_task(result)
    except TypeError:
        asyncio.create_task(bot.add_cog(cog))

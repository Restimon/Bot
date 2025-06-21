import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timedelta

from storage import get_collection
from personnage import get_personnages_trie_par_rarete_et_faction
from data import personnages_equipés, derniere_equip, sauvegarder

class Equiper(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="equiper", description="Équipe un personnage pour activer son passif.")
    @app_commands.describe(index="Numéro du personnage à équiper (voir /collection)")
    async def equiper(self, interaction: discord.Interaction, index: int):
        await interaction.response.defer(ephemeral=True)
        guild_id = str(interaction.guild_id)
        user_id = str(interaction.user.id)

        # Vérification du cooldown
        now = datetime.utcnow()
        last_used = derniere_equip.get(guild_id, {}).get(user_id)
        if last_used:
            last_dt = datetime.fromisoformat(last_used)
            if now - last_dt < timedelta(hours=24):
                remaining = timedelta(hours=24) - (now - last_dt)
                h = remaining.seconds // 3600
                m = (remaining.seconds % 3600) // 60
                await interaction.followup.send(f"⏳ Tu dois attendre encore {h}h {m}min avant de pouvoir changer de personnage.", ephemeral=True)
                return

        # Récupération collection
        collection = get_collection(guild_id, user_id)
        if not collection:
            await interaction.followup.send("❌ Tu n’as aucun personnage dans ta collection.", ephemeral=True)
            return

        # Construction liste complète
        full_list = []
        for perso in get_personnages_trie_par_rarete_et_faction():
            nom = perso["nom"]
            count = collection.get(nom, 0)
            full_list.extend([nom] * count)

        if index < 1 or index > len(full_list):
            await interaction.followup.send(f"❌ Numéro invalide. Tu as {len(full_list)} personnage(s).", ephemeral=True)
            return

        nom_perso = full_list[index - 1]
        personnages_equipés.setdefault(guild_id, {})[user_id] = nom_perso
        derniere_equip.setdefault(guild_id, {})[user_id] = now.isoformat()
        sauvegarder()

        await interaction.followup.send(f"✅ Tu as équipé **{nom_perso}**. Son passif est maintenant actif.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Equiper(bot))

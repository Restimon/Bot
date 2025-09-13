# cogs/help_cog.py
from __future__ import annotations
import discord
from discord.ext import commands
from discord import app_commands

PUBLIC_COMMANDS = {
    "/info": "📇 Affiche ton profil GotValis (PV, PB, tickets, or, perso équipé, classement).",
    "/inv": "🎒 Ouvre ton inventaire (objets, quantités, tickets, GoldValis).",
    "/tickets": "🎟️ Montre ton solde de tickets.",
    "/daily": "🗓️ Récupère ton paquet quotidien (ticket + items + or).",
    "/tirage": "🎰 Utilise un ticket pour invoquer un personnage.",
    "/use": "🧰 Utilise un objet utilitaire.",
    "/heal": "💉 Soigne une cible avec un objet de soin.",
    "/fight": "⚔️ Attaque une cible avec un objet offensif.",
    "/status": "🔎 Liste tes effets actifs (poison, virus, infection, etc.).",
    "/help": "📚 Ce manuel crypté GotValis.",
}

COMMANDS_LIST = list(PUBLIC_COMMANDS.keys())

async def help_autocomplete(interaction: discord.Interaction, current: str):
    current_lower = (current or "").lower()
    choices = []
    for name in COMMANDS_LIST:
        if current_lower in name or current_lower in PUBLIC_COMMANDS[name].lower():
            choices.append(app_commands.Choice(name=name, value=name))
        if len(choices) >= 25:
            break
    return choices

class HelpCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="help", description="Manuel crypté GotValis : trouvez la commande qu’il vous faut.")
    @app_commands.describe(command="Commande à expliquer (auto-complétion).")
    @app_commands.autocomplete(command=help_autocomplete)
    async def help_cmd(self, inter: discord.Interaction, command: str | None = None):
        if command is None or command not in PUBLIC_COMMANDS:
            # Vue d’ensemble
            embed = discord.Embed(
                title="📚 Manuel crypté — Réseau GotValis",
                description="Liste des interfaces civiles autorisées.",
                color=discord.Color.blurple(),
            )
            for name, desc in PUBLIC_COMMANDS.items():
                embed.add_field(name=name, value=desc, inline=False)
            embed.set_footer(text="Modules administratifs non listés.")
            await inter.response.send_message(embed=embed, ephemeral=True)
            return

        # Fiche détaillée
        embed = discord.Embed(
            title=f"ℹ️ Aide : {command}",
            description=PUBLIC_COMMANDS[command],
            color=discord.Color.blurple(),
        )
        embed.add_field(
            name="Contexte RP",
            value=(
                "Vous consultez un terminal **GotValis**. Les interfaces exposées sont filtrées.\n"
                "Les actions de combat et d’économie sont surveillées, chaque requête est tracée."
            ),
            inline=False,
        )
        await inter.response.send_message(embed=embed, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(HelpCog(bot))

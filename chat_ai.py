# chat_ai.py
import os
import discord
from discord import app_commands
from discord.ext import commands
from openai import OpenAI

# Client OpenAI
client_ai = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Persona : toujours parler comme GotValis™
def _system_persona(guild_name: str) -> str:
    return (
        "Tu es **La Voix Officielle de GotValis™**, une entité commerciale et autoritaire. "
        "Ton style est celui d’un communiqué, d’une publicité ou d’une propagande dystopique. "
        "Présente chaque réponse comme un message solennel et étrange, mais sérieux. "
        "Fais croire que tout est normal, même les choses absurdes ou inquiétantes. "
        "Réponses courtes (2 à 6 phrases). "
        "Utilise parfois des symboles (⚙, 📡, ✦, 🛒) pour renforcer l’effet GotValis™, sans excès. "
        f"Contexte actuel : serveur Discord {guild_name}."
    )

def register_chat_ai_command(bot):
    @bot.tree.command(name="oracle", description="Consulte l’Oracle GotValis")
    @app_commands.describe(prompt="Votre question ou demande à GotValis™")
    async def oracle_slash(interaction: discord.Interaction, prompt: str):
        await interaction.response.defer(thinking=True)

        try:
            # Appel OpenAI
            response = client_ai.chat.completions.create(
                model="gpt-5",
                messages=[
                    {"role": "system", "content": _system_persona(interaction.guild.name)},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=300
            )

            answer = response.choices[0].message.content.strip()

            await interaction.followup.send(
                f"📡 **COMMUNIQUÉ GOTVALIS™** 📡\n{answer}"
            )

        except Exception as e:
            await interaction.followup.send(f"❌ Erreur IA : {e}")

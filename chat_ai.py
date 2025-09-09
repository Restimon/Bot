# chat_ai.py
import os
import discord
from discord import app_commands
from discord.ext import commands
from openai import OpenAI

# Client OpenAI
client_ai = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def register_chat_ai_command(bot):
    @bot.tree.command(name="ask", description="Pose une question à l'IA GotValis")
    @app_commands.describe(prompt="Ce que tu veux demander à l'IA")
    async def ask_slash(interaction: discord.Interaction, prompt: str):
        await interaction.response.defer(thinking=True)

        try:
            # Appel à GPT-5
            response = client_ai.responses.create(
                model="gpt-5",  
                input=f"Réponds dans un style mystérieux et roleplay comme si tu étais une entité de GotValis. Question: {prompt}"
            )

            answer = response.output[0].content[0].text

            await interaction.followup.send(f"🤖 **GotValis IA** : {answer}")

        except Exception as e:
            await interaction.followup.send(f"❌ Erreur IA : {e}")

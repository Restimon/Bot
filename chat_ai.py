# chat_ai.py
import os
import asyncio
import discord
from discord import app_commands
from discord.ext import commands

# On essaie d'importer la lib. Si absente, on degradera proprement.
try:
    from openai import OpenAI
except Exception:
    OpenAI = None

_CLIENT = None

def _ensure_client():
    """Crée/renvoie le client OpenAI, ou lève une erreur claire s'il manque."""
    global _CLIENT
    if _CLIENT is not None:
        return _CLIENT

    if OpenAI is None:
        raise RuntimeError(
            "Le module 'openai' n'est pas installé. "
            "Ajoute `openai>=1.51.0` dans requirements.txt et redeploie."
        )

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "La variable d'environnement OPENAI_API_KEY est manquante. "
            "Ajoute-la dans Render (Dashboard → Environment)."
        )

    _CLIENT = OpenAI(api_key=api_key)
    return _CLIENT

async def generate_oracle_reply(guild_name: str, prompt: str, tone: str = "normal", reason: str | None = None) -> str:
    """
    Génère une réponse RP "GotValis".
    tone: "normal" ou "threat"
    """
    # Message système + style
    persona_base = (
        "Tu es GOTVALIS™, entité mystérieuse corporatiste. "
        "Style: solennel, légèrement menaçant, techno-mystique, RP. "
        "Parle en français. Réponses concises (2-5 phrases)."
    )

    if tone == "threat":
        persona_base += (
            " Si l'utilisateur provoque ou trolle, tu émets un avertissement ferme, "
            "suggérant des 'conséquences de conformité', sans violence réelle ni menace illégale."
        )

    if reason:
        persona_base += f" Contexte modération: {reason}."

    # Prompt final
    full_prompt = (
        f"{persona_base}\n"
        f"Contexte serveur: {guild_name}\n"
        f"Question/texte utilisateur: {prompt}\n"
        "Réponds dans l’univers de GotValis™ avec une mise en garde subtile si nécessaire."
    )

    # Si la lib/clé manque, on renvoie un message RP fallback
    try:
        client = _ensure_client()
    except Exception as e:
        # Fallback RP local si OpenAI non dispo
        if tone == "threat":
            return ("« Votre signal cognitif a franchi le seuil d’alarme. "
                    "Poursuivre sur cette trajectoire déclenchera des audits de conformité. "
                    "Recalibrez votre langage et reprenez une respiration contrôlée. »")
        return ("« Les circuits oraculaires sont momentanément isolés. "
                "GotValis™ entend toutefois votre requête… patientez le temps d’un battement quantique. »")

    # Appel Responses API (modèle à ta convenance)
    try:
        resp = client.responses.create(
            model="gpt-5",  # ou "gpt-4.1-mini" si indisponible
            input=full_prompt,
        )
        # Accès texte robuste (structure Responses API)
        # La plupart du temps: resp.output[0].content[0].text
        # On tente proprement:
        txt = None
        try:
            txt = resp.output[0].content[0].text
        except Exception:
            # Fallback plus large: on cherche un champ texte plausible
            if hasattr(resp, "output") and resp.output:
                for block in resp.output:
                    if hasattr(block, "content") and block.content:
                        for c in block.content:
                            if hasattr(c, "text") and c.text:
                                txt = c.text
                                break
                    if txt:
                        break
        if not txt:
            txt = "« Les augures se brouillent. Le Verbe reprendra quand la trame sera stable. »"
        return txt.strip()
    except Exception:
        # Fallback RP en cas d'erreur API
        if tone == "threat":
            return ("« Vos impulsions cognitives sont notées. "
                    "Poursuivre l’irrespect compromettra votre accès au confort collectif. »")
        return ("« Les oracles sont saturés. GotValis™ conserve votre requête en mémoire élastique. »")

def register_chat_ai_command(bot: commands.Bot):
    @bot.tree.command(name="ask", description="Pose une question à l'IA GotValis")
    @app_commands.describe(prompt="Ce que tu veux demander à l'IA")
    async def ask_slash(interaction: discord.Interaction, prompt: str):
        await interaction.response.defer(thinking=True, ephemeral=False)
        try:
            reply = await generate_oracle_reply(interaction.guild.name, prompt, tone="normal")
            await interaction.followup.send(f"📡 **COMMUNIQUÉ GOTVALIS™** 📡\n{reply}")
        except Exception as e:
            await interaction.followup.send(f"❌ Erreur IA : {e}", ephemeral=True)

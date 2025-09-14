# cogs/chat_ai.py
from __future__ import annotations

import os
import re
import asyncio
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

# ─────────────────────────────────────────────────────────────
# OpenAI client (avec fallback si non dispo)
# ─────────────────────────────────────────────────────────────
try:
    from openai import OpenAI
except Exception:
    OpenAI = None  # lib non installée

_CLIENT: Optional["OpenAI"] = None


def _ensure_client() -> "OpenAI":
    """
    Crée/renvoie le client OpenAI, ou lève une erreur claire s'il manque.
    """
    global _CLIENT
    if _CLIENT is not None:
        return _CLIENT

    if OpenAI is None:
        raise RuntimeError(
            "Le module 'openai' n'est pas installé. "
            "Ajoute `openai>=1.51.0` dans requirements.txt puis redeploie."
        )

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "La variable d'environnement OPENAI_API_KEY est manquante. "
            "Ajoute-la dans ton hébergeur (ex: Render → Environment)."
        )

    _CLIENT = OpenAI(api_key=api_key)
    return _CLIENT


async def generate_oracle_reply(
    guild_name: str,
    prompt: str,
    tone: str = "normal",
    reason: str | None = None,
) -> str:
    """
    Génère une réponse RP "GotValis".
    tone ∈ {"normal", "threat"} → "threat" = agressif/punitif (sans violence).
    """
    persona = (
        "Tu es GOTVALIS™, entité corporatiste mystérieuse. "
        "Style: solennel, techno-mystique, légèrement menaçant, en RP. "
        "Réponds en français. 2 à 5 phrases, percutantes."
    )
    if tone == "threat":
        persona += (
            " L'utilisateur a un comportement troll/hostile : "
            "ta réponse devient sèche et intimidante, évoque des 'audits de conformité' "
            "et des 'protocoles disciplinaires', sans jamais menacer de violence réelle."
        )
    if reason:
        persona += f" Motif modération: {reason}."

    # Prompt final
    system_msg = persona
    user_msg = (
        f"Contexte serveur: {guild_name}\n"
        f"Message utilisateur: {prompt}\n"
        "Réponds immédiatement, sans préambule superflu."
    )

    # Fallback local si l’API n’est pas dispo
    try:
        client = _ensure_client()
    except Exception:
        if tone == "threat":
            return ("Votre flux s'écarte des protocoles. Un audit de conformité sera ouvert si vous persistez. "
                    "Restez dans le périmètre autorisé.")
        return ("Les oracles sont momentanément isolés. GotValis™ a reçu votre impulsion cognitive. Réessayez.")

    # Appel Chat Completions (stable dans openai>=1)
    try:
        resp = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.7,
            max_tokens=250,
        )
        out = (resp.choices[0].message.content or "").strip()
        if not out:
            out = "Les augures se brouillent. La trame se resynchronise."
        return out
    except Exception:
        if tone == "threat":
            return ("Signal reçu. Votre insistance sera journalisée et examinée. "
                    "Restez dans le périmètre de courtoisie attendu.")
        return ("Les circuits oraculaires sont saturés. La file des réponses est en cours de purge.")


# ─────────────────────────────────────────────────────────────
# Cog
# ─────────────────────────────────────────────────────────────
class ChatAI(commands.Cog):
    """
    Déclencheurs :
      - /ask
      - ?ai …  |  !ai …
      - mention du bot
      - reply à un message du bot
      - DM au bot
    Détection de troll → ton 'threat'.
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.prefixes = ("?ai", "!ai")

    # ---------- Slash ----------
    @app_commands.command(name="ask", description="Pose une question à l'IA GotValis™")
    @app_commands.describe(prompt="Ce que tu veux demander")
    async def ask_slash(self, interaction: discord.Interaction, prompt: str):
        await interaction.response.defer(thinking=True)
        tone = "threat" if self._is_troll(prompt) else "normal"
        guild_name = interaction.guild.name if interaction.guild else "DM"
        reply = await generate_oracle_reply(guild_name, prompt, tone=tone)
        await interaction.followup.send(f"📡 **COMMUNIQUÉ GOTVALIS™** 📡\n{reply}")

    # ---------- Events ----------
    @commands.Cog.listener()
    async def on_message(self, msg: discord.Message):
        # ignorer bots & soi-même
        if msg.author.bot or msg.author.id == getattr(self.bot.user, "id", None):
            return

        content = (msg.content or "").strip()
        if not content:
            return

        # DM → tout message déclenche l'IA
        if isinstance(msg.channel, discord.DMChannel):
            await self._handle_ai_request(msg, content)
            return

        if not msg.guild:
            return

        lowered = content.lower()

        # 1) Préfixes texte
        if lowered.startswith(self.prefixes):
            prompt = content
            for p in self.prefixes:
                if lowered.startswith(p):
                    prompt = content[len(p):].strip(" :,-")
                    break
            await self._handle_ai_request(msg, prompt)
            return

        # 2) Mention du bot
        if self.bot.user and self.bot.user in msg.mentions:
            prompt = self._strip_bot_mention(content, self.bot.user.id).strip() or content
            await self._handle_ai_request(msg, prompt)
            return

        # 3) Reply à un message du bot
        if msg.reference and msg.reference.resolved:
            ref_msg = msg.reference.resolved
            if isinstance(ref_msg, discord.Message) and ref_msg.author and ref_msg.author.id == self.bot.user.id:
                await self._handle_ai_request(msg, content)
                return

    # ---------- Helpers ----------
    async def _handle_ai_request(self, msg: discord.Message, raw_text: str, tone: str | None = None):
        if not raw_text:
            return
        detected_threat = self._is_troll(raw_text)
        tone = tone or ("threat" if detected_threat else "normal")

        try:
            async with msg.channel.typing():
                reply = await generate_oracle_reply(
                    msg.guild.name if msg.guild else "DM",
                    raw_text,
                    tone=tone,
                    reason="troll détecté" if detected_threat else None,
                )
        except Exception:
            reply = "Les antennes cognitives ont trébuché. Reprenez, avec clarté."

        await msg.reply(f"📡 **COMMUNIQUÉ GOTVALIS™** 📡\n{reply}", mention_author=False)

    def _strip_bot_mention(self, text: str, bot_id: int) -> str:
        # Retire <@id> ou <@!id> en tête + ponctuations usuelles
        pattern = rf"^<@!?{bot_id}>\s*[:,\-–—]*\s*"
        return re.sub(pattern, "", text, flags=re.IGNORECASE)

    def _is_troll(self, text: str) -> bool:
        """
        Heuristique simple pour repérer troll/hostilité.
        - insultes & grossièretés communes
        - full CAPS long
        - spam ponctuation
        - provocations directes
        """
        t = text.strip()
        lt = t.lower()

        bad_words = [
            "fdp", "tg", "ta gueule", "noob", "nul à chier",
            "merde", "connard", "connasse", "abruti", "idiot",
            "imbécile", "crève", "dégage", "pute", "sale", "débile",
        ]
        if any(w in lt for w in bad_words):
            return True

        if len(t) >= 8:
            letters = [c for c in t if c.isalpha()]
            if letters:
                up_ratio = sum(1 for c in letters if c.isupper()) / len(letters)
                if up_ratio > 0.8:
                    return True

        if re.search(r"[!?]{3,}", t):
            return True

        triggers = [
            "tu sers à rien", "t'es nul", "t es nul", "ferme-la", "ferme la",
            "t'es con", "t es con", "ridicule", "je te déteste", "je te hais",
        ]
        if any(ph in lt for ph in triggers):
            return True

        return False


# ─────────────────────────────────────────────────────────────
# Setup extension
# ─────────────────────────────────────────────────────────────
async def setup(bot: commands.Bot):
    await bot.add_cog(ChatAI(bot))

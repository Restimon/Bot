# chat_ai.py
import os
import re
import asyncio
import discord
from discord import app_commands
from discord.ext import commands

# --- OpenAI client (optionnel, fallback prévu si absent) ---
try:
    from openai import OpenAI
except Exception:  # lib non installée
    OpenAI = None

_CLIENT = None


def _ensure_client():
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
            "ta réponse devient sèche et intimidante, évoque des 'audits de conformité', "
            "des 'protocoles disciplinaires', sans menacer de violence réelle."
        )
    if reason:
        persona += f" Contexte modération: {reason}."

    full_prompt = (
        f"{persona}\n\n"
        f"Contexte serveur: {guild_name}\n"
        f"Message utilisateur: {prompt}\n"
        "Réponds immédiatement, sans préambule superflu."
    )

    # Fallback local si OpenAI indisponible
    try:
        client = _ensure_client()
    except Exception:
        if tone == "threat":
            return ("Votre flux s'écarte des protocoles. "
                    "Poursuivre ainsi déclenchera un audit de conformité. "
                    "Corrigez le tir, maintenant.")
        return ("Les oracles sont momentanément isolés. "
                "GotValis™ a reçu votre impulsion cognitive. Réessayez.")

    try:
        resp = client.responses.create(
            model="gpt-5",  # adapte si besoin
            input=full_prompt,
        )
        txt = None
        try:
            txt = resp.output[0].content[0].text
        except Exception:
            # récupération prudente
            if getattr(resp, "output", None):
                for block in resp.output:
                    if getattr(block, "content", None):
                        for c in block.content:
                            if getattr(c, "text", None):
                                txt = c.text
                                break
                    if txt:
                        break
        if not txt:
            txt = "Les augures se brouillent. Le Verbe reprendra quand la trame sera stable."
        return txt.strip()
    except Exception:
        if tone == "threat":
            return ("Signal reçu. Votre insistance sera journalisée et examinée. "
                    "Restez dans le périmètre de courtoisie attendu.")
        return ("Les circuits oraculaires sont saturés. "
                "La file de réponses est en cours de purge.")


# ---------------------------
# Cog: intercepte le chat
# ---------------------------
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

    # ---------------------------
    # Slash command
    # ---------------------------
    @app_commands.command(name="ask", description="Pose une question à l'IA GotValis™")
    @app_commands.describe(prompt="Ce que tu veux demander")
    async def ask_slash(self, interaction: discord.Interaction, prompt: str):
        await interaction.response.defer(thinking=True)
        tone = "threat" if self._is_troll(prompt) else "normal"
        reply = await generate_oracle_reply(interaction.guild.name if interaction.guild else "DM", prompt, tone=tone)
        await interaction.followup.send(f"📡 **COMMUNIQUÉ GOTVALIS™** 📡\n{reply}")

    # ---------------------------
    # Events
    # ---------------------------
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

        # Si pas dans un serveur, ignorer
        if not msg.guild:
            return

        # 1) Préfixes textuels
        lowered = content.lower()
        if lowered.startswith(self.prefixes):
            # retire le préfixe utilisé
            for p in self.prefixes:
                if lowered.startswith(p):
                    prompt = content[len(p):].strip(" :,-")
                    break
            await self._handle_ai_request(msg, prompt)
            return

        # 2) Mention directe du bot
        if self.bot.user and self.bot.user in msg.mentions:
            # on retire la mention pour ne garder que le prompt
            prompt = self._strip_bot_mention(content, self.bot.user.id).strip()
            # si rien après la mention → utiliser le message brut
            if not prompt:
                prompt = content
            await self._handle_ai_request(msg, prompt)
            return

        # 3) Reply à un message du bot
        if msg.reference and msg.reference.resolved:
            ref_msg = msg.reference.resolved
            if isinstance(ref_msg, discord.Message) and ref_msg.author and ref_msg.author.id == self.bot.user.id:
                await self._handle_ai_request(msg, content)
                return

    # ---------------------------
    # Helpers
    # ---------------------------
    async def _handle_ai_request(self, msg: discord.Message, raw_text: str, tone: str | None = None):
        """
        Détecte troll → passe en 'threat'. Envoie la réponse.
        """
        if not raw_text:
            return
        detected_threat = self._is_troll(raw_text)
        tone = tone or ("threat" if detected_threat else "normal")

        # petit indicateur de saisie
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
        """
        Retire <@id> ou <@!id> en début de message (et espaces/punct).
        """
        patterns = [
            rf"^<@!?{bot_id}>\s*[:,\-–—]*\s*",
        ]
        out = text
        for pat in patterns:
            out = re.sub(pat, "", out, flags=re.IGNORECASE)
        return out

    def _is_troll(self, text: str) -> bool:
        """
        Heuristique simple pour repérer troll/hostilité.
        - insultes & grossièretés communes
        - full CAPS long
        - spam ponctuation
        """
        t = text.strip()

        # 1) insultes / toxic words (liste courte, extensible)
        bad_words = [
            "fdp", "tg", "ta gueule", "clochard", "clocharde", "noob", "nul à chier",
            "merde", "connard", "connasse", "abruti", "idiot", "imbécile",
            "crève", "dégage", "suce", "pute", "sale", "débile",
        ]
        lt = t.lower()
        if any(w in lt for w in bad_words):
            return True

        # 2) ALL CAPS prolongé (forte intensité)
        if len(t) >= 8:
            letters = [c for c in t if c.isalpha()]
            if letters:
                up_ratio = sum(1 for c in letters if c.isupper()) / len(letters)
                if up_ratio > 0.8:
                    return True

        # 3) spam ponctuation agressive
        if re.search(r"[!?]{3,}", t):
            return True

        # 4) provocations directes
        triggers = [
            "tu sers à rien", "t'es nul", "t es nul", "ferme-la", "ferme la", "réponds espèce de",
            "t'es con", "t es con", "ridicule", "je te déteste", "je te hais",
        ]
        if any(ph in lt for ph in triggers):
            return True

        return False


# ---------------------------
# Hooks d’installation
# ---------------------------
async def setup(bot: commands.Bot):
    """Chargement via extensions (await bot.load_extension)."""
    await bot.add_cog(ChatAI(bot))


def register_chat_ai_command(bot: commands.Bot):
    """
    Compat si tu préfères enregistrer via fonction.
    (Ajoute le Cog + la commande slash /ask automatiquement.)
    """
    async def _add():
        await bot.add_cog(ChatAI(bot))
    try:
        res = _add()
        if asyncio.iscoroutine(res):
            asyncio.create_task(res)
    except Exception:
        asyncio.create_task(_add())

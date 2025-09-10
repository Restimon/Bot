# chat_ai.py
# ✨ IA "GotValis™" — répond via /ask et aux messages (mention, DM, ou préfixes ?ai/!ai)
import os
import re
import asyncio
import discord
from discord import app_commands
from discord.ext import commands

# ── Client OpenAI (robuste aux environnements incomplets) ─────────────────────
try:
    from openai import OpenAI
except Exception:
    OpenAI = None

_CLIENT = None

def _ensure_client():
    """
    Crée/renvoie le client OpenAI ou lève une erreur claire s'il manque.
    Compatible avec OPENAI_API_KEY (+ OPENAI_BASE_URL facultatif).
    """
    global _CLIENT
    if _CLIENT is not None:
        return _CLIENT

    if OpenAI is None:
        raise RuntimeError(
            "Le module 'openai' n'est pas installé. "
            "Ajoute `openai>=1.51.0` à requirements.txt puis redeploie."
        )

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY est manquant. Ajoute la variable d'environnement "
            "dans ton hébergeur (ex: Render → Environment)."
        )

    base_url = os.getenv("OPENAI_BASE_URL")  # optionnel (proxy/azure/etc.)
    if base_url:
        _CLIENT = OpenAI(api_key=api_key, base_url=base_url)
    else:
        _CLIENT = OpenAI(api_key=api_key)
    return _CLIENT


# ── Génération de réponse GotValis ────────────────────────────────────────────
_GOTVALIS_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")  # override possible

def _build_persona(tone: str = "normal", reason: str | None = None) -> str:
    persona = (
        "Tu es **GOTVALIS™**, une entité corporatiste techno-mystique. "
        "Parle en **français**, dans un style **solennel**, légèrement **menaçant**, "
        "précis et concis (2 à 5 phrases). Reste RP, sans menace illégale ni violence réelle."
    )
    if tone == "threat":
        persona += (
            " Si l'utilisateur trolle, émet un avertissement ferme sur des 'audits de conformité', "
            "sans menacer ni humilier."
        )
    if reason:
        persona += f" Contexte modération: {reason}."
    return persona

async def generate_oracle_reply(guild_name: str | None, prompt: str, tone: str = "normal", reason: str | None = None) -> str:
    """
    Génère une réponse RP signée GotValis. Utilise OpenAI Responses API (fallback local si indispo).
    """
    system_msg = _build_persona(tone=tone, reason=reason)
    context = f"Contexte serveur: {guild_name or 'DM'}"

    # Fallback local si client/clé absents
    try:
        client = _ensure_client()
    except Exception:
        if tone == "threat":
            return ("« Votre signal dépasse les seuils. Restez conforme, ou des audits internes "
                    "viendront rationaliser vos habitudes. »")
        return ("« Les oracles sont momentanément isolés. GotValis™ persiste, vous n’êtes pas ignoré. »")

    # Appel API (Responses) — extraction robuste du texte
    try:
        # On privilégie Responses API (plus résilient multi-sorties)
        resp = client.responses.create(
            model=_GOTVALIS_MODEL,
            input=(
                f"{system_msg}\n"
                f"{context}\n"
                f"Question/texte utilisateur: {prompt}\n"
                "Réponds en 2–5 phrases, RP, dans l’univers GotValis™."
            ),
        )
        # Chemin direct pratique
        txt = getattr(resp, "output_text", None)
        if not txt:
            # Extraction plus défensive si output_text manquant
            out = getattr(resp, "output", None) or []
            for block in out:
                for c in getattr(block, "content", []) or []:
                    if getattr(c, "text", None):
                        txt = c.text
                        break
                if txt:
                    break
        return (txt or "« Les augures se brouillent. Requête en file de restauration. »").strip()
    except Exception:
        # Fallback Completions (au cas où Responses ne serait pas dispo côté proxy)
        try:
            chat = client.chat.completions.create(
                model=_GOTVALIS_MODEL,
                messages=[
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": f"{context}\n{prompt}"},
                ],
                temperature=0.6,
            )
            return (chat.choices[0].message.content or "").strip()
        except Exception:
            if tone == "threat":
                return ("« Votre émission verbale est sous surveillance. "
                        "Poursuivre sur cette pente déclenchera des contrôles. »")
            return ("« Les trames sont saturées. GotValis™ traitera votre message quand la fibre cesse de brûler. »")


# ── Cog : répond aux messages + slash /ask ───────────────────────────────────
MENTION_RE = re.compile(r"<@!?\d+>")

class ChatAI(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Anti spam simple: cooldown utilisateur (en secondes)
        self.user_cooldowns: dict[int, float] = {}
        self.cooldown_secs = 8

    def _rate_limited(self, user_id: int) -> bool:
        now = asyncio.get_event_loop().time()
        last = self.user_cooldowns.get(user_id, 0.0)
        if now - last < self.cooldown_secs:
            return True
        self.user_cooldowns[user_id] = now
        return False

    async def _handle_prompt(self, message: discord.Message, prompt: str, tone: str = "normal"):
        async with message.channel.typing():
            reply = await generate_oracle_reply(
                getattr(message.guild, "name", None),
                prompt.strip(),
                tone=tone
            )
        await message.reply(f"📡 **COMMUNIQUÉ GOTVALIS™** 📡\n{reply}", mention_author=False)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Ignorer soi-même et les bots
        if message.author.bot:
            return

        # DM → toujours répondre
        if isinstance(message.channel, discord.DMChannel):
            if self._rate_limited(message.author.id):
                return
            await self._handle_prompt(message, message.content)
            return

        # Guild: répond si mentionné OU préfixe ?ai/!ai
        content = message.content.strip()
        bot_id = self.bot.user.id if self.bot.user else None

        mentioned = False
        if bot_id and self.bot.user.mentioned_in(message):
            # éviter les mentions dans des chaînes sans réelle invocation
            mentioned = True

        if mentioned:
            # Retire la mention du prompt
            prompt = MENTION_RE.sub("", content).strip()
            if not prompt:
                prompt = "Analyse ce canal et présente-toi brièvement."
            if self._rate_limited(message.author.id):
                return
            await self._handle_prompt(message, prompt)
            return

        # Préfixes légers
        lowered = content.lower()
        if lowered.startswith("?ai ") or lowered == "?ai":
            if self._rate_limited(message.author.id):
                return
            await self._handle_prompt(message, content[3:].strip())
            return
        if lowered.startswith("!ai ") or lowered == "!ai":
            if self._rate_limited(message.author.id):
                return
            await self._handle_prompt(message, content[3:].strip())
            return


# ── Slash command /ask (optionnel mais pratique) ─────────────────────────────
def register_chat_ai_command(bot: commands.Bot):
    @bot.tree.command(name="ask", description="Pose une question à l'IA GotValis™ (RP)")
    @app_commands.describe(prompt="Ta question / requête")
    async def ask_slash(interaction: discord.Interaction, prompt: str):
        await interaction.response.defer(thinking=True, ephemeral=False)
        try:
            reply = await generate_oracle_reply(
                getattr(interaction.guild, "name", None),
                prompt,
                tone="normal"
            )
            await interaction.followup.send(f"📡 **COMMUNIQUÉ GOTVALIS™** 📡\n{reply}")
        except Exception as e:
            await interaction.followup.send(f"❌ Erreur IA : {e}", ephemeral=True)


# ── Setup extension (load_extension) ─────────────────────────────────────────
async def setup(bot: commands.Bot):
    # Ajoute le Cog pour les réponses au chat
    await bot.add_cog(ChatAI(bot))
    # Enregistre aussi la commande /ask pour ceux qui préfèrent le slash
    register_chat_ai_command(bot)

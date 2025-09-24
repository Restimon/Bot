# cogs/chat_ai.py
from __future__ import annotations

import os
import re
import time
import random
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

# ========= CONFIG =========
OWNER_ID = 123456789012345678  # <-- ⚠️ Mets ICI l'ID du "chef" du bot
AI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# Cooldowns (anti-spam)
MSG_COOLDOWN_SEC = 8          # ne pas re-générer une réponse au même user trop souvent
PUNISH_COOLDOWN_SEC = 60      # délai mini entre deux sanctions sur un même user
PUNISH_MIN, PUNISH_MAX = 1, 4 # dégâts en cas de troll

# Déclencheurs troll de base (restent sobres)
TROLL_WORDS = [
    "fdp", "tg", "ta gueule", "clochard", "clocharde", "noob", "nul à chier",
    "merde", "connard", "connasse", "abruti", "idiot", "imbécile",
    "crève", "dégage", "pute", "sale", "débile",
]

TROLL_PHRASES = [
    "tu sers à rien", "t'es nul", "t es nul", "ferme-la", "ferme la",
    "réponds espèce de", "t'es con", "t es con", "je te déteste", "je te hais",
]

# ========= Helpers OpenAI =========
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


async def _openai_generate(text: str) -> str:
    """
    Appel OpenAI minimaliste avec fallback sobre si indispo.
    """
    try:
        client = _ensure_client()
        resp = client.responses.create(
            model=AI_MODEL,
            input=text,
        )
        # Extraction robuste du texte
        try:
            return resp.output[0].content[0].text.strip()
        except Exception:
            pass
        if getattr(resp, "output", None):
            for block in resp.output:
                if getattr(block, "content", None):
                    for c in block.content:
                        if getattr(c, "text", None):
                            return c.text.strip()
        return "Réponse momentanément indisponible."
    except Exception:
        return "Réponse momentanément indisponible."

# ========= Persona / Prompting =========
def build_persona(
    *,
    guild_name: str,
    user_is_owner: bool,
    user_above_bot: bool,
    is_troll: bool,
    reason: str | None = None,
) -> str:
    """
    Construit un persona sobre selon le contexte hiérarchique + troll.
    """
    base = (
        "Tu es GOTVALIS™, assistant du serveur, style sobre, professionnel, concis. "
        "Réponds en français, en 1 à 3 phrases, sans emojis, sans astérisques, sans en-tête décoratif."
    )

    if user_is_owner:
        base += (
            " L'interlocuteur est ton supérieur direct : adopte un ton respectueux, loyal, "
            "orienté opération, sans ironie."
        )
    elif user_above_bot:
        base += (
            " L'interlocuteur a un rôle supérieur à toi : reste respectueux, "
            "professionnel, avec une taquinerie subtile et rare (jamais agressive)."
        )
    else:
        base += (
            " L'interlocuteur est un membre standard : réponds fermement mais courtoisement, "
            "en restant utile et clair."
        )

    if is_troll:
        base += (
            " Contexte: message agressif/troll. Reste factuel, sec et cadrant, "
            "en parlant de règles, conformité et logs. Pas de menace de violence."
        )

    if reason:
        base += f" Note modération: {reason}."

    base += f" Contexte serveur: {guild_name}."
    return base


def build_prompt(persona: str, user_msg: str) -> str:
    return (
        f"{persona}\n\n"
        f"Message utilisateur: {user_msg}\n"
        "Réponds directement, sans préambule."
    )

# ========= Détection troll =========
def is_troll_text(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    lt = t.lower()
    if any(w in lt for w in TROLL_WORDS):
        return True
    if any(ph in lt for ph in TROLL_PHRASES):
        return True
    # spam ponctuation / caps
    letters = [c for c in lt if c.isalpha()]
    if letters:
        up_ratio = sum(1 for c in letters if c.isupper()) / len(letters)
        if up_ratio > 0.85:
            return True
    if re.search(r"[!?]{4,}", lt):
        return True
    return False


async def generate_reply(
    guild_name: str,
    user_msg: str,
    *,
    user_is_owner: bool,
    user_above_bot: bool,
    is_troll: bool,
    reason: str | None = None,
) -> str:
    persona = build_persona(
        guild_name=guild_name,
        user_is_owner=user_is_owner,
        user_above_bot=user_above_bot,
        is_troll=is_troll,
        reason=reason,
    )
    prompt = build_prompt(persona, user_msg)
    txt = await _openai_generate(prompt)

    # Fallback local si OpenAI a répondu trop pauvrement
    if not txt or txt == "Réponse momentanément indisponible.":
        if is_troll:
            return "Rappel : ce salon est modéré. Merci de rester correct. Des logs sont conservés."
        if user_is_owner:
            return "Présent. Je peux assister la modération, le suivi des stats et l’automatisation."
        if user_above_bot:
            return "Je fournis suivi, outils et rapports. Prêt à épauler l’équipe, sans faire d’ombre."
        return "J’assiste la communauté : réponses, stats, automatisations et rappels."
    return txt

# ========= Économie / Dégâts =========
async def punish_and_credit(bot: commands.Bot, target: discord.Member, reason: str) -> int:
    """
    Inflige 1–4 dégâts et crédite l'équivalent en coins au bot.
    Retourne les dégâts infligés (0 si impossible).
    """
    dmg = random.randint(PUNISH_MIN, PUNISH_MAX)

    # Inflige les dégâts (best-effort)
    dealt = 0
    try:
        from stats_db import deal_damage  # type: ignore
        res = await deal_damage(int(bot.user.id), int(target.id), int(dmg))
        # res peut contenir absorbed, etc. On comptabilise au moins dmg
        dealt = int(dmg)
    except Exception:
        dealt = 0  # si no stats_db

    # Créditer les coins au bot
    try:
        from economy_db import add_balance  # type: ignore
        await add_balance(int(bot.user.id), int(dmg), reason="ai_moderation")
    except Exception:
        pass

    return dealt

# ========= Le COG =========
class ChatAI(commands.Cog):
    """
    Déclencheurs :
      - /ask
      - ?ai …  |  !ai …
      - mention du bot
      - reply à un message du bot
      - DM au bot

    Détection de troll → ton cadrant + sanction (CD).
    Réponses SANS en-tête “Communiqué”.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.prefixes = ("?ai", "!ai")
        self._last_msg_at: dict[int, float] = {}      # user_id -> ts dernière réponse AI
        self._last_punish_at: dict[int, float] = {}   # user_id -> ts dernière sanction

    # ----- Slash -----
    @app_commands.command(name="ask", description="Poser une question à l’IA GotValis™ (réponse sobre).")
    @app_commands.describe(prompt="Ce que tu veux demander")
    async def ask_slash(self, interaction: discord.Interaction, prompt: str):
        await interaction.response.defer(thinking=True)

        member = interaction.user
        guild = interaction.guild
        if not guild:
            # DM → pas de hiérarchie, pas de sanction
            reply = await generate_reply(
                guild_name="DM",
                user_msg=prompt,
                user_is_owner=(member.id == OWNER_ID),
                user_above_bot=False,
                is_troll=is_troll_text(prompt),
                reason=None,
            )
            return await interaction.followup.send(reply)

        user_is_owner = (member.id == OWNER_ID)
        user_above_bot = False
        try:
            me = guild.me
            if isinstance(member, discord.Member) and me and me.top_role and member.top_role:
                user_above_bot = (member.top_role.position > me.top_role.position)
        except Exception:
            pass

        hostile = is_troll_text(prompt)
        reply = await generate_reply(
            guild_name=guild.name,
            user_msg=prompt,
            user_is_owner=user_is_owner,
            user_above_bot=user_above_bot,
            is_troll=hostile,
            reason="hostile" if hostile else None,
        )
        await interaction.followup.send(reply)

        # Sanction (pas sur l’OWNER, ni si supérieur hiérarchique)
        if hostile and not user_is_owner and not user_above_bot:
            now = time.time()
            last = self._last_punish_at.get(member.id, 0)
            if now - last >= PUNISH_COOLDOWN_SEC:
                dealt = await punish_and_credit(self.bot, member, "ai_troll")
                self._last_punish_at[member.id] = now
                if dealt > 0:
                    try:
                        await interaction.followup.send(f"(Sanction : {dealt} dégâts appliqués.)", ephemeral=True)
                    except Exception:
                        pass

    # ----- Events -----
    @commands.Cog.listener()
    async def on_message(self, msg: discord.Message):
        if msg.author.bot:
            return
        content = (msg.content or "").strip()
        if not content:
            return

        # DM → on répond sans hiérarchie, anti-spam simple
        if isinstance(msg.channel, discord.DMChannel):
            if not self._passes_cooldown(msg.author.id):
                return
            await self._handle_ai_request(msg, content, guild=None)
            return

        guild = msg.guild
        if not guild:
            return

        lowered = content.lower()

        # Triggers
        prompt = None
        if lowered.startswith(self.prefixes):
            for p in self.prefixes:
                if lowered.startswith(p):
                    prompt = content[len(p):].strip(" :,-")
                    break
        elif self.bot.user and self.bot.user in msg.mentions:
            prompt = self._strip_bot_mention(content, self.bot.user.id).strip() or content
        elif (msg.reference and isinstance(msg.reference.resolved, discord.Message)
              and msg.reference.resolved.author
              and msg.reference.resolved.author.id == getattr(self.bot.user, "id", None)):
            prompt = content

        if not prompt:
            return

        if not self._passes_cooldown(msg.author.id):
            return

        await self._handle_ai_request(msg, prompt, guild=guild)

    # ----- Core handler -----
    async def _handle_ai_request(self, msg: discord.Message, raw_text: str, guild: discord.Guild | None):
        member = msg.author
        hostile = is_troll_text(raw_text)

        user_is_owner = (member.id == OWNER_ID)
        user_above_bot = False
        if guild:
            try:
                me = guild.me
                if isinstance(member, discord.Member) and me and me.top_role and member.top_role:
                    user_above_bot = (member.top_role.position > me.top_role.position)
            except Exception:
                pass

        try:
            async with msg.channel.typing():
                reply = await generate_reply(
                    guild_name=(guild.name if guild else "DM"),
                    user_msg=raw_text,
                    user_is_owner=user_is_owner,
                    user_above_bot=user_above_bot,
                    is_troll=hostile,
                    reason="hostile" if hostile else None,
                )
        except Exception:
            reply = "Reçu. J’opère, sobrement."

        await msg.reply(reply, mention_author=False)

        # Sanction si hostile (hors OWNER et supérieurs)
        if hostile and guild and not user_is_owner and not user_above_bot:
            now = time.time()
            last = self._last_punish_at.get(member.id, 0)
            if now - last >= PUNISH_COOLDOWN_SEC:
                dealt = await punish_and_credit(self.bot, member, "ai_troll")
                self._last_punish_at[member.id] = now
                if dealt > 0:
                    try:
                        await msg.channel.send(f"(Sanction : {dealt} dégâts appliqués.)", delete_after=8)
                    except Exception:
                        pass

    # ----- Utils -----
    def _strip_bot_mention(self, text: str, bot_id: int) -> str:
        patterns = [rf"^<@!?{bot_id}>\s*[:,\-–—]*\s*"]
        out = text
        for pat in patterns:
            out = re.sub(pat, "", out, flags=re.IGNORECASE)
        return out

    def _passes_cooldown(self, user_id: int) -> bool:
        now = time.time()
        last = self._last_msg_at.get(user_id, 0.0)
        if now - last < MSG_COOLDOWN_SEC:
            return False
        self._last_msg_at[user_id] = now
        return True


async def setup(bot: commands.Bot):
    await bot.add_cog(ChatAI(bot))

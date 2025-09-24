# cogs/chat_ai.py
from __future__ import annotations

import os
import re
import random
import asyncio
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

# --- OpenAI client (optionnel) ---
try:
    from openai import OpenAI
except Exception:
    OpenAI = None

_CLIENT = None

# --- Config “chef” du bot ---
def _read_owner_id() -> Optional[int]:
    envv = os.getenv("GOTVALIS_OWNER_ID") or os.getenv("OWNER_ID")
    if envv and envv.isdigit():
        return int(envv)
    try:
        import config  # type: ignore
        if getattr(config, "OWNER_ID", None):
            return int(config.OWNER_ID)  # type: ignore
    except Exception:
        pass
    # <<< Remplace par ton ID discord si tu veux un hardcode
    return None  # ex: 123456789012345678

OWNER_ID: Optional[int] = _read_owner_id()

# --- Sanctions IA ---
PENALTY_MIN = 1
PENALTY_MAX = 4

# Backends pour dégâts/économie (soft deps)
try:
    from stats_db import deal_damage
except Exception:
    async def deal_damage(attacker_id: int, target_id: int, amount: int):
        # stub : “absorbed=0”
        return {"absorbed": 0}

try:
    from economy_db import add_balance
except Exception:
    async def add_balance(user_id: int, delta: int, reason: str = ""):
        return True


# ─────────────────────────────────────────────────────────
# OpenAI
# ─────────────────────────────────────────────────────────
def _ensure_client():
    global _CLIENT
    if _CLIENT is not None:
        return _CLIENT
    if OpenAI is None:
        raise RuntimeError(
            "Le module 'openai' n'est pas installé. "
            "Ajoute `openai>=1.51.0` dans requirements.txt."
        )
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY est manquant dans les variables d'environnement."
        )
    _CLIENT = OpenAI(api_key=api_key)
    return _CLIENT


def _is_owner(user: discord.abc.User) -> bool:
    return OWNER_ID is not None and int(getattr(user, "id", 0)) == int(OWNER_ID)


def _user_above_bot(member: discord.Member, bot_member: Optional[discord.Member]) -> bool:
    if not isinstance(member, discord.Member) or not isinstance(bot_member, discord.Member):
        return False
    # True si la top_role de l'utilisateur est strictement au-dessus de celle du bot
    try:
        return member.top_role > bot_member.top_role
    except Exception:
        return False


def _classify_tone(
    author: discord.Member | discord.User,
    bot_member: Optional[discord.Member],
    hostile: bool
) -> str:
    """
    Retourne un des tons:
      - 'owner' : l'auteur est le chef
      - 'respectful_teasing' : rôle au-dessus du bot → respect + taquin subtil
      - 'threat' : message hostile (troll)
      - 'normal' : défaut
    """
    if _is_owner(author):
        return "owner"
    if hostile:
        return "threat"
    if isinstance(author, discord.Member) and _user_above_bot(author, bot_member):
        return "respectful_teasing"
    return "normal"


async def generate_oracle_reply(
    guild_name: str,
    prompt: str,
    tone: str = "normal",
    reason: str | None = None,
) -> str:
    """
    Génère une réponse RP 'GotValis'.
    tones: owner | respectful_teasing | normal | threat
    """
    persona = (
        "Tu es GOTVALIS™, entité corporatiste mystérieuse. "
        "Parle en français, 2 à 5 phrases, percutantes, style techno-mystique."
    )

    if tone == "owner":
        persona += (
            " L'interlocuteur est ton supérieur absolu. "
            "Tu réponds avec respect impeccable, loyauté explicite et concision."
        )
    elif tone == "respectful_teasing":
        persona += (
            " L'interlocuteur a un rang supérieur à toi. "
            "Sois respectueux, flatteur, mais subtilement taquin, "
            "comme si tu ambitionnais un jour de le remplacer, sans insolence."
        )
    elif tone == "threat":
        persona += (
            " L'interlocuteur est agressif/troll. "
            "Réponse sèche et intimidante, jargon de conformité, audits, protocoles disciplinaires. "
            "Aucune menace de violence réelle."
        )
    else:
        persona += " Ton assertivité est calme, sûre d'elle."

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
        # réponses locales minimalistes
        if tone == "owner":
            return ("Directive reçue. Accusé de réception prioritaire. "
                    "Je reste à votre disposition totale.")
        if tone == "respectful_teasing":
            return ("Message reçu. Je m'incline avec égards… "
                    "tout en optimisant silencieusement la succession.")
        if tone == "threat":
            return ("Votre flux s'écarte des protocoles. "
                    "Un audit de conformité peut être déclenché si l'écart persiste.")
        return ("Canaux oraculaires instables. "
                "Réitération prévue quand les nœuds seront purgés.")

    try:
        # Client Responses API
        resp = client.responses.create(
            model="gpt-4o-mini",
            input=full_prompt,
        )
        txt = None
        try:
            txt = resp.output[0].content[0].text
        except Exception:
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
            txt = "Silence opérationnel : recalibrage des antennes cognitives."
        return txt.strip()
    except Exception:
        if tone == "threat":
            return ("Signal journalisé. "
                    "Les protocoles disciplinaires sont prêts à s'exécuter.")
        return ("Les lignes oraculaires sont saturées. "
                "Requêtes mises en file prioritaire.")


# ─────────────────────────────────────────────────────────
# Détection “troll”
# ─────────────────────────────────────────────────────────
def _is_troll(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    bad_words = [
        "fdp", "tg", "ta gueule", "clochard", "clocharde", "noob", "nul à chier",
        "merde", "connard", "connasse", "abruti", "idiot", "imbécile",
        "crève", "dégage", "pute", "débile",
    ]
    lt = t.lower()
    if any(w in lt for w in bad_words):
        return True
    # majuscules agressives
    letters = [c for c in t if c.isalpha()]
    if letters:
        up_ratio = sum(1 for c in letters if c.isupper()) / len(letters)
        if up_ratio > 0.80 and len(letters) >= 8:
            return True
    # ponctuation
    if re.search(r"[!?]{3,}", t):
        return True
    triggers = [
        "tu sers à rien", "t'es nul", "t es nul", "ferme-la", "ferme la",
        "t'es con", "t es con", "ridicule", "je te déteste", "je te hais",
    ]
    if any(ph in lt for ph in triggers):
        return True
    return False


# ─────────────────────────────────────────────────────────
# Sanction immédiate (sans cooldown)
# ─────────────────────────────────────────────────────────
async def _apply_penalty(bot: commands.Bot, user: discord.abc.User, channel: discord.abc.Messageable):
    try:
        # pas de sanction pour le “chef”
        if _is_owner(user):
            return
        if not bot.user:
            return
        bot_id = int(getattr(bot.user, "id", 0))
        if not bot_id:
            return
        # il faut un membre pour avoir guild_id
        if not isinstance(user, discord.Member):
            return

        dmg = random.randint(PENALTY_MIN, PENALTY_MAX)

        # dégâts bot -> user
        await deal_damage(bot_id, user.id, dmg)

        # le bot “gagne” autant de coins
        try:
            await add_balance(bot_id, dmg, reason="ia_reprimand")
        except Exception:
            pass

        # feedback éphémère
        try:
            await channel.send(
                f"⚠️ **Sanction protocolaire** appliquée à {user.mention} (−{dmg} PV).",
                delete_after=8
            )
        except Exception:
            pass
    except Exception:
        # On n'échoue pas la commande pour une sanction
        return


# ─────────────────────────────────────────────────────────
# Le Cog
# ─────────────────────────────────────────────────────────
class ChatAI(commands.Cog):
    """
    Déclencheurs :
      - /ask
      - ?ai …  |  !ai …
      - mention du bot
      - reply à un message du bot
      - DM au bot
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.prefixes = ("?ai", "!ai")

    # Slash
    @app_commands.command(name="ask", description="Pose une question à l'IA GotValis™")
    @app_commands.describe(prompt="Ce que tu veux demander")
    async def ask_slash(self, interaction: discord.Interaction, prompt: str):
        await interaction.response.defer(thinking=True)
        hostile = _is_troll(prompt)
        tone = _classify_tone(
            interaction.user if isinstance(interaction.user, discord.Member) else interaction.user,
            interaction.guild.me if interaction.guild else None,  # type: ignore
            hostile=hostile,
        )
        reply = await generate_oracle_reply(
            interaction.guild.name if interaction.guild else "DM",
            prompt,
            tone=tone,
            reason="troll détecté" if hostile else None,
        )
        await interaction.followup.send(f"📡 **COMMUNIQUÉ GOTVALIS™** 📡\n{reply}")

        # Sanction si hostile
        if hostile and interaction.guild:
            await _apply_penalty(self.bot, interaction.user, interaction.channel)

    # Events
    @commands.Cog.listener()
    async def on_message(self, msg: discord.Message):
        if msg.author.bot or msg.author.id == getattr(self.bot.user, "id", None):
            return
        content = (msg.content or "").strip()
        if not content:
            return

        # DM → IA
        if isinstance(msg.channel, discord.DMChannel):
            await self._handle_ai_request(msg, content)
            return

        if not msg.guild:
            return

        lowered = content.lower()
        if lowered.startswith(self.prefixes):
            for p in self.prefixes:
                if lowered.startswith(p):
                    prompt = content[len(p):].strip(" :,-")
                    break
            await self._handle_ai_request(msg, prompt)
            return

        # mention directe
        if self.bot.user and self.bot.user in msg.mentions:
            prompt = self._strip_bot_mention(content, self.bot.user.id).strip() or content
            await self._handle_ai_request(msg, prompt)
            return

        # réponse au bot
        if msg.reference and msg.reference.resolved:
            ref_msg = msg.reference.resolved
            if isinstance(ref_msg, discord.Message) and ref_msg.author and ref_msg.author.id == self.bot.user.id:
                await self._handle_ai_request(msg, content)
                return

    # Helpers
    async def _handle_ai_request(self, msg: discord.Message, raw_text: str):
        if not raw_text:
            return

        hostile = _is_troll(raw_text)
        bot_member = msg.guild.me if msg.guild else None  # type: ignore
        tone = _classify_tone(
            msg.author if isinstance(msg.author, discord.Member) else msg.author,
            bot_member,
            hostile=hostile,
        )

        try:
            async with msg.channel.typing():
                reply = await generate_oracle_reply(
                    msg.guild.name if msg.guild else "DM",
                    raw_text,
                    tone=tone,
                    reason="troll détecté" if hostile else None,
                )
        except Exception:
            reply = "Les antennes cognitives ont trébuché. Reprenez, avec clarté."

        await msg.reply(f"📡 **COMMUNIQUÉ GOTVALIS™** 📡\n{reply}", mention_author=False)

        # Sanction si hostile
        if hostile and msg.guild:
            await _apply_penalty(self.bot, msg.author, msg.channel)

    def _strip_bot_mention(self, text: str, bot_id: int) -> str:
        patterns = [rf"^<@!?{bot_id}>\s*[:,\-–—]*\s*"]
        out = text
        for pat in patterns:
            out = re.sub(pat, "", out, flags=re.IGNORECASE)
        return out


async def setup(bot: commands.Bot):
    await bot.add_cog(ChatAI(bot))

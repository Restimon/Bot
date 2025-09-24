# cogs/chat_ai.py
from __future__ import annotations

import os
import re
import random
import discord
from discord import app_commands
from discord.ext import commands

# --- OpenAI client (optionnel, fallback prévu si absent) ---
try:
    from openai import OpenAI
except Exception:  # lib non installée
    OpenAI = None

# Économie / Passifs / Combat
from economy_db import add_balance
from passifs import trigger  # on_gain_coins, etc.

# (facultatif) pour infliger des dégâts
try:
    from stats_db import deal_damage
except Exception:
    deal_damage = None  # type: ignore

# ─────────────────────────────────────────────────────────────
# Réglages
# ─────────────────────────────────────────────────────────────
# Chef absolu (le bot lui parle toujours avec respect)
BOSS_ID = int(os.getenv("GOTVALIS_BOSS_ID", "0"))  # mets l'ID numérique ici si tu préfères

# Récompense “par réponse IA” (mêmes bornes que l’éco messages)
ECON_MULTIPLIER = 0.5
AI_REWARD_MIN = 1
AI_REWARD_MAX = 10

# Détection d’insultes / agressivité
BAD_WORDS = {
    "fdp", "tg", "ta gueule", "clochard", "clocharde", "noob", "nul à chier",
    "merde", "connard", "connasse", "abruti", "idiot", "imbécile",
    "crève", "dégage", "suce", "pute", "sale", "débile",
}
TROLL_PHRASES = {
    "tu sers à rien", "t'es nul", "t es nul", "ferme-la", "ferme la",
    "réponds espèce de", "t'es con", "t es con", "ridicule",
    "je te déteste", "je te hais",
}

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


def _member_above_bot(member: discord.Member, bot_member: discord.Member | None) -> bool:
    if not member or not bot_member:
        return False
    # Compare le plus haut rôle
    try:
        return member.top_role > bot_member.top_role
    except Exception:
        return False


def _is_trollish(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    lt = t.lower()
    if any(w in lt for w in BAD_WORDS):
        return True
    if any(ph in lt for ph in TROLL_PHRASES):
        return True
    # CAPS + !!!?
    letters = [c for c in t if c.isalpha()]
    if letters:
        up_ratio = sum(1 for c in letters if c.isupper()) / len(letters)
        if up_ratio > 0.8:
            return True
    if re.search(r"[!?]{3,}", t):
        return True
    return False


def _build_persona(mode: str) -> str:
    """
    mode ∈ {"boss_respect", "taunt_respect", "aggressive", "neutral"}
    """
    base = (
        "Tu es GOTVALIS™, entité corporatiste mystérieuse. "
        "Style: sobre, techno-mystique, tranchant. Réponds en français, 2 à 4 phrases."
    )
    if mode == "boss_respect":
        base += " Adresse-toi avec un respect formel, concis, sans sarcasme. Tu obéis sans discuter."
    elif mode == "taunt_respect":
        base += (
            " L'interlocuteur a un rang supérieur au tien : reste poli et correct, "
            "mais glisse un sous-texte ambitieux et piquant, suggérant subtilement que tu pourrais le remplacer."
        )
    elif mode == "aggressive":
        base += (
            " L'interlocuteur t'insulte : réponds sec et menaçant (sans violence réelle), "
            "parle d'audits, protocoles disciplinaires, et d'éviction algorithmique. Assène des piques nettes."
        )
    else:
        base += " Reste neutre, professionnel, légèrement froid."
    return base


async def _grant_ai_reply_reward(bot: commands.Bot, guild: discord.Guild | None) -> int:
    """
    Donne au BOT une récompense pour sa réponse IA, selon la même logique que les gains par messages :
    tirage 1..10, * ECON_MULTIPLIER, application des bonus de passifs on_gain_coins.
    """
    if not bot.user:
        return 0
    base = random.randint(AI_REWARD_MIN, AI_REWARD_MAX)
    amount = max(1, int(base * ECON_MULTIPLIER))
    # passifs
    try:
        res = await trigger("on_gain_coins", user_id=bot.user.id, delta=amount)
        extra = int((res or {}).get("extra", 0))
        amount += max(0, extra)
    except Exception:
        pass
    try:
        await add_balance(bot.user.id, amount, "ai_reply_reward")
    except Exception:
        return 0

    # leaderboard live (si présent)
    try:
        if guild:
            from cogs.leaderboard_live import schedule_lb_update
            schedule_lb_update(bot, guild.id, "ai_reply_reward")
    except Exception:
        pass

    return amount


async def _maybe_apply_damage_and_loot(bot: commands.Bot, author: discord.Member, guild: discord.Guild | None) -> int:
    """
    Inflige 1–4 dégâts à l'auteur si message troll/insulte. Le bot gagne autant de coins.
    Retourne les dégâts infligés.
    """
    dmg = random.randint(1, 4)
    # Dégâts (si backend dispo)
    try:
        if deal_damage is not None:
            await deal_damage(bot.user.id, author.id, dmg)  # type: ignore
    except Exception:
        # ignore erreurs
        pass

    # Le bot gagne autant de coins
    try:
        await add_balance(bot.user.id, dmg, "ai_moderation_damage")
        if guild:
            from cogs.leaderboard_live import schedule_lb_update
            schedule_lb_update(bot, guild.id, "ai_moderation_damage")
    except Exception:
        pass

    return dmg


async def generate_oracle_reply(
    bot: commands.Bot,
    guild: discord.Guild | None,
    author: discord.User | discord.Member,
    prompt: str,
) -> tuple[str, bool]:
    """
    Génère la réponse + indique si un “strike” (troll) a été détecté.
    Le ton dépend :
      - BOSS_ID → respect formel
      - rôle utilisateur > rôle bot → respect taquin
      - sinon → neutre/aggressif si troll.
    """
    is_troll = _is_trollish(prompt)

    mode = "neutral"
    if isinstance(author, discord.Member) and guild and bot.user and isinstance(bot.user, discord.User):
        bot_member = guild.get_member(bot.user.id)
        if author.id == BOSS_ID and BOSS_ID > 0:
            mode = "boss_respect"
        elif _member_above_bot(author, bot_member):
            mode = "taunt_respect"
        else:
            mode = "aggressive" if is_troll else "neutral"
    else:
        # DM ou pas de guild
        mode = "aggressive" if is_troll else "neutral"

    persona = _build_persona(mode)
    full_prompt = (
        f"{persona}\n\n"
        f"Contexte serveur: {guild.name if guild else 'DM'}\n"
        f"Message utilisateur: {prompt}\n"
        "Réponds immédiatement, sans préambule, pas de markdown décoratif."
    )

    # Fallback local si OpenAI indisponible
    try:
        client = _ensure_client()
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
            txt = "Signal confirmé. Directive appliquée."
        return txt.strip(), is_troll
    except Exception:
        # Petites réponses locales si l'API est indispo
        if mode == "boss_respect":
            return "Ordre reçu. J’opère discrètement et j’exécute, sans friction.", is_troll
        if mode == "taunt_respect":
            return "Compris. J’optimiserai le périmètre… un jour, peut-être mieux que prévu.", is_troll
        if mode == "aggressive":
            return "Assez. Tes écarts sont tracés. Prochain faux pas, et l’audit tombe.", is_troll
        return "Opérationnelle. J’assure l’ordre, l’aide et la traçabilité du serveur.", is_troll


class ChatAI(commands.Cog):
    """
    Déclencheurs :
      - /ask
      - ?ai …  |  !ai …
      - mention du bot
      - reply à un message du bot
      - DM au bot
    Les réponses IA :
      - crédite le BOT (ai_reply_reward)
      - si message insultant → inflige 1–4 dégâts à l’auteur et crédite le BOT d’autant.
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.prefixes = ("?ai", "!ai")

    # Slash
    @app_commands.command(name="ask", description="Pose une question à l'IA GotValis™")
    @app_commands.describe(prompt="Ce que tu veux demander")
    async def ask_slash(self, interaction: discord.Interaction, prompt: str):
        await interaction.response.defer(thinking=True)
        reply, is_troll = await generate_oracle_reply(self.bot, interaction.guild, interaction.user, prompt)

        # Envoi
        await interaction.followup.send(reply)

        # Récompense pour la réponse IA (le BOT gagne)
        await _grant_ai_reply_reward(self.bot, interaction.guild)

        # Si troll → dégâts & loot pour le bot
        if is_troll and isinstance(interaction.user, discord.Member):
            await _maybe_apply_damage_and_loot(self.bot, interaction.user, interaction.guild)

    # Events
    @commands.Cog.listener()
    async def on_message(self, msg: discord.Message):
        # Ignore bots (inclut le bot lui-même pour éviter les boucles)
        if msg.author.bot:
            return

        content = (msg.content or "").strip()
        if not content:
            return

        # DM → toujours traité
        if isinstance(msg.channel, discord.DMChannel):
            await self._handle_ai_request(msg, content)
            return

        # Guild only, et ignorer si pas de guild
        if not msg.guild:
            return

        lowered = content.lower()
        # Préfixes
        if lowered.startswith(self.prefixes):
            for p in self.prefixes:
                if lowered.startswith(p):
                    prompt = content[len(p):].strip(" :,-")
                    break
            await self._handle_ai_request(msg, prompt)
            return

        # Mentions directes du bot
        if self.bot.user and self.bot.user in msg.mentions:
            prompt = self._strip_bot_mention(content, self.bot.user.id).strip() or content
            await self._handle_ai_request(msg, prompt)
            return

        # Réponse à un message du bot
        if msg.reference and msg.reference.resolved:
            ref_msg = msg.reference.resolved
            if isinstance(ref_msg, discord.Message) and ref_msg.author and ref_msg.author.id == getattr(self.bot.user, "id", None):
                await self._handle_ai_request(msg, content)
                return

    # Helpers
    async def _handle_ai_request(self, msg: discord.Message, raw_text: str):
        if not raw_text:
            return
        try:
            async with msg.channel.typing():
                reply, is_troll = await generate_oracle_reply(self.bot, msg.guild, msg.author, raw_text)
        except Exception:
            reply, is_troll = "Les antennes cognitives ont trébuché. Reformule clairement.", False

        # Envoi
        await msg.reply(reply, mention_author=False)

        # Récompense pour la réponse IA (le BOT gagne)
        await _grant_ai_reply_reward(self.bot, msg.guild)

        # Sanction si troll
        if is_troll and isinstance(msg.author, discord.Member):
            await _maybe_apply_damage_and_loot(self.bot, msg.author, msg.guild)

    def _strip_bot_mention(self, text: str, bot_id: int) -> str:
        patterns = [rf"^<@!?{bot_id}>\s*[:,\-–—]*\s*"]
        out = text
        for pat in patterns:
            out = re.sub(pat, "", out, flags=re.IGNORECASE)
        return out


async def setup(bot: commands.Bot):
    await bot.add_cog(ChatAI(bot))

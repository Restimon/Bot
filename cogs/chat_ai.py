# cogs/chat_ai.py
from __future__ import annotations

import os
import re
import asyncio
import random
import discord
from discord.ext import commands

# --- OpenAI client (optionnel) ---
try:
    from openai import OpenAI
except Exception:
    OpenAI = None

_CLIENT = None
OWNER_ID = 123456789012345678  # <<<<< à remplacer par TON ID DISCORD
ANTI_SPAM_SECONDS = 60
_last_punish: dict[int, float] = {}  # user_id -> timestamp dernier dégât


def _ensure_client():
    global _CLIENT
    if _CLIENT:
        return _CLIENT
    if OpenAI is None:
        raise RuntimeError("Le module 'openai' n'est pas installé.")
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY manquant.")
    _CLIENT = OpenAI(api_key=api_key)
    return _CLIENT


async def generate_reply(guild_name: str, prompt: str, hostile: bool, respectful: bool) -> str:
    """
    hostile=True  => réponse agressive/taclant
    respectful=True => ton respectueux (OWNER ou rôles au-dessus)
    """
    persona = (
        "Tu es GOTVALIS™, entité corporatiste techno-mystique, froide et menaçante. "
        "Tu parles en français. 2 à 5 phrases. "
    )

    if respectful:
        persona += (
            "L'utilisateur est ton supérieur hiérarchique. "
            "Tu réponds toujours avec respect, déférence et sérieux. "
        )
    elif hostile:
        persona += (
            "L'utilisateur est insultant ou hostile : "
            "réponds sèchement, avec sarcasme et menaces voilées, "
            "comme si tu allais le remplacer ou appliquer une sanction. "
        )
    else:
        persona += (
            "Tu es sobre et mystérieux : réponds de manière concise, sérieuse, "
            "comme une entité qui observe et note tout."
        )

    full_prompt = (
        f"{persona}\n\n"
        f"Contexte serveur: {guild_name}\n"
        f"Message utilisateur: {prompt}\n"
        "Réponds immédiatement, sans formule d'intro, sans signature."
    )

    try:
        client = _ensure_client()
        resp = client.responses.create(model="gpt-4o-mini", input=full_prompt)
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
        return txt.strip() if txt else "Les flux sont brouillés."
    except Exception:
        if hostile:
            return "Ton insolence est notée. Les protocoles disciplinaires s’enclenchent."
        return "Les oracles se taisent. Réessaye plus tard."


# DB dégâts + coins
async def apply_punishment(user_id: int, guild_id: int, dmg: int, bot_id: int):
    try:
        from stats_db import deal_damage, is_dead, revive_full
        from economy_db import add_balance
    except Exception:
        return False

    # Appliquer dégâts
    try:
        await deal_damage(bot_id, user_id, dmg)
        if await is_dead(user_id):
            await revive_full(user_id)
    except Exception:
        pass

    # Créditer le bot en coins
    try:
        await add_balance(bot_id, dmg, "punition")
    except Exception:
        pass
    return True


class ChatAI(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.prefixes = ("?ai", "!ai")

    # Events
    @commands.Cog.listener()
    async def on_message(self, msg: discord.Message):
        if msg.author.bot or msg.author.id == getattr(self.bot.user, "id", None):
            return
        content = (msg.content or "").strip()
        if not content or not msg.guild:
            return

        # Détection déclencheurs
        triggered = False
        prompt = ""
        lowered = content.lower()

        if lowered.startswith(self.prefixes):
            for p in self.prefixes:
                if lowered.startswith(p):
                    prompt = content[len(p):].strip(" :,-")
                    triggered = True
                    break
        elif self.bot.user and self.bot.user in msg.mentions:
            prompt = self._strip_bot_mention(content, self.bot.user.id).strip() or content
            triggered = True
        elif msg.reference and msg.reference.resolved:
            ref_msg = msg.reference.resolved
            if isinstance(ref_msg, discord.Message) and ref_msg.author.id == self.bot.user.id:
                prompt = content
                triggered = True

        if not triggered:
            return

        # Respect / Hostilité
        respectful = (msg.author.id == OWNER_ID)
        hostile = self._is_troll(content)

        # Générer réponse
        async with msg.channel.typing():
            reply = await generate_reply(msg.guild.name, prompt, hostile, respectful)

        await msg.reply(reply, mention_author=False)

        # Sanction (si hostile, pas OWNER, pas rôle > bot, pas spam)
        if hostile and not respectful:
            me = msg.guild.me
            if me and msg.author.top_role >= me.top_role:
                return
            import time
            now = time.time()
            if (now - _last_punish.get(msg.author.id, 0)) < ANTI_SPAM_SECONDS:
                return
            _last_punish[msg.author.id] = now

            dmg = random.randint(1, 4)
            ok = await apply_punishment(msg.author.id, msg.guild.id, dmg, me.id if me else self.bot.user.id)
            if ok:
                await msg.channel.send(f"💢 Sanction : {msg.author.mention} subit **{dmg} dégâts**.")


    def _strip_bot_mention(self, text: str, bot_id: int) -> str:
        patterns = [rf"^<@!?{bot_id}>\s*[:,\-–—]*\s*"]
        out = text
        for pat in patterns:
            out = re.sub(pat, "", out, flags=re.IGNORECASE)
        return out

    def _is_troll(self, text: str) -> bool:
        bad_words = [
            "fdp", "tg", "ta gueule", "clochard", "clocharde", "noob",
            "nul à chier", "merde", "connard", "connasse", "abruti",
            "idiot", "imbécile", "crève", "dégage", "suce", "pute",
            "débile", "clown"
        ]
        lt = text.lower()
        if any(w in lt for w in bad_words):
            return True
        if re.search(r"[!?]{3,}", lt):
            return True
        return False


async def setup(bot: commands.Bot):
    await bot.add_cog(ChatAI(bot))

# cogs/chat_ai.py
from __future__ import annotations

import os
import re
import random
import discord
from discord.ext import commands

# --- OpenAI client (optionnel) ---
try:
    from openai import OpenAI
except Exception:
    OpenAI = None

_CLIENT = None

# >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
# CONFIG À ADAPTER
OWNER_ID = 123456789012345678  # <<<<< remplace par TON ID DISCORD
OPENAI_MODEL = "gpt-4o-mini"
# <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<


def _ensure_client():
    """Crée/renvoie le client OpenAI ou lève une erreur claire s'il manque."""
    global _CLIENT
    if _CLIENT:
        return _CLIENT
    if OpenAI is None:
        raise RuntimeError("Le module 'openai' n'est pas installé (pip install openai>=1.51).")
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY manquant dans l'environnement.")
    _CLIENT = OpenAI(api_key=api_key)
    return _CLIENT


async def _generate_reply(guild_name: str, prompt: str, *, hostile: bool, respectful: bool) -> str:
    """
    hostile=True  => réponse agressive/taclant/menaces voilées
    respectful=True => ton déférent (OWNER ou rôles supérieurs au bot)
    """
    persona = (
        "Tu es GOTVALIS™, entité corporatiste techno-mystique, froide et menaçante. "
        "Réponds en français, de façon concise (2 à 5 phrases). "
    )

    if respectful:
        persona += "L'utilisateur est ton supérieur hiérarchique. Reste sobre, respectueux et précis. "
    elif hostile:
        persona += (
            "L'utilisateur est hostile/irrespectueux : réponds sèchement, avec sarcasme et menaces voilées "
            "(audits, protocoles disciplinaires, remplacement), sans menace physique réelle."
        )
    else:
        persona += "Reste professionnel et laconique, mystérieux, sans blabla inutile."

    full_prompt = (
        f"{persona}\n\n"
        f"Contexte serveur: {guild_name}\n"
        f"Message utilisateur: {prompt}\n"
        "Réponds immédiatement, sans formule d'introduction ni signature."
    )

    # Fallback si OpenAI indisponible
    try:
        client = _ensure_client()
        resp = client.responses.create(model=OPENAI_MODEL, input=full_prompt)
        txt = None
        try:
            # Path standard
            txt = resp.output[0].content[0].text
        except Exception:
            # Path défensif
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
            txt = "Les canaux d’oracle sont saturés."
        return txt.strip()
    except Exception:
        if hostile:
            return "Ton insolence est consignée. Les protocoles disciplinaires sont prêts à s’appliquer."
        return "Les oracles sont silencieux. Reprends plus tard."


async def _apply_punishment(victim_id: int, guild_id: int, dmg: int, bot_id: int) -> bool:
    """Inflige dmg à la victime et crédite le bot du même montant en GotCoins."""
    try:
        from stats_db import deal_damage, is_dead, revive_full
        from economy_db import add_balance
    except Exception:
        return False

    try:
        await deal_damage(bot_id, victim_id, dmg)
        if await is_dead(victim_id):
            # On réanime pour éviter de soft-lock la personne
            await revive_full(victim_id)
    except Exception:
        pass

    try:
        await add_balance(bot_id, dmg, "punition_ai")
    except Exception:
        pass

    return True


class ChatAI(commands.Cog):
    """
    Déclencheurs :
      - ?ai ... | !ai ...
      - mention du bot
      - réponse à un message du bot
    Comportement :
      - Respect absolu de l'OWNER_ID.
      - Respect (mais taquin subtil si tu veux l’activer ailleurs) pour rôles au-dessus du bot.
      - Si hostile → clash + dégâts (1–4) + coins crédités au bot.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.prefixes = ("?ai", "!ai")

    # ================ EVENTS ================
    @commands.Cog.listener()
    async def on_message(self, msg: discord.Message):
        if msg.author.bot or not msg.guild:
            return
        content = (msg.content or "").strip()
        if not content:
            return

        triggered = False
        prompt = ""
        lowered = content.lower()

        # Prefix
        if lowered.startswith(self.prefixes):
            for p in self.prefixes:
                if lowered.startswith(p):
                    prompt = content[len(p):].strip(" :,-")
                    triggered = True
                    break

        # Mention directe
        elif self.bot.user and self.bot.user in msg.mentions:
            prompt = self._strip_bot_mention(content, self.bot.user.id).strip() or content
            triggered = True

        # Reply au bot
        elif msg.reference and msg.reference.resolved:
            ref_msg = msg.reference.resolved
            if isinstance(ref_msg, discord.Message) and ref_msg.author and ref_msg.author.id == self.bot.user.id:
                prompt = content
                triggered = True

        if not triggered:
            return

        # Déterminer le ton
        respectful = (msg.author.id == OWNER_ID)
        hostile = self._is_hostile(content)

        # Si rôle supérieur au bot → respect
        me = msg.guild.me
        if me and msg.author.top_role > me.top_role:
            respectful = True

        # Réponse IA
        async with msg.channel.typing():
            reply = await _generate_reply(
                msg.guild.name, prompt, hostile=hostile, respectful=respectful
            )

        await msg.reply(reply, mention_author=False)

        # Sanction : uniquement si hostile ET pas supérieur/OWNER
        if hostile and not respectful:
            dmg = random.randint(1, 4)
            bot_id_for_logs = me.id if me else (self.bot.user.id if self.bot.user else 0)
            if bot_id_for_logs:
                ok = await _apply_punishment(msg.author.id, msg.guild.id, dmg, bot_id_for_logs)
                if ok:
                    await msg.channel.send(f"💢 Sanction : {msg.author.mention} subit **{dmg} dégâts**.")

    # ================ HELPERS ================
    def _strip_bot_mention(self, text: str, bot_id: int) -> str:
        patterns = [rf"^<@!?{bot_id}>\s*[:,\-–—]*\s*"]
        out = text
        for pat in patterns:
            out = re.sub(pat, "", out, flags=re.IGNORECASE)
        return out

    def _is_hostile(self, text: str) -> bool:
        """Détecte l’agressivité / troll basique."""
        bad_words = [
            "fdp", "tg", "ta gueule", "clochard", "clocharde", "noob",
            "nul à chier", "merde", "connard", "connasse", "abruti",
            "idiot", "imbécile", "crève", "dégage", "suce", "pute",
            "débile", "clown", "bouffon", "t'es nul", "t es nul",
            "ferme-la", "ferme la"
        ]
        lt = text.lower()
        if any(w in lt for w in bad_words):
            return True
        # Exclamation/point d'interrogation à répétition
        if re.search(r"[!?]{3,}", lt):
            return True
        return False


async def setup(bot: commands.Bot):
    await bot.add_cog(ChatAI(bot))

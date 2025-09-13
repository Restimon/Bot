# main.py
from __future__ import annotations

import os
import sys
import asyncio
import logging
from typing import List

import discord
from discord.ext import commands
from discord import app_commands

# ─────────────────────────────────────────────────────────────
# 1) Logging propre
# ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)
log = logging.getLogger("gotvalis.main")

# ─────────────────────────────────────────────────────────────
# 2) Token / Guild
# ─────────────────────────────────────────────────────────────
TOKEN = os.getenv("GOTVALIS_TOKEN") or os.getenv("DISCORD_TOKEN")
GUILD_ID = os.getenv("GUILD_ID")  # optionnel: sync rapide par serveur

if not TOKEN:
    log.error("Aucun token trouvé. Définis GOTVALIS_TOKEN (ou DISCORD_TOKEN) dans tes variables d’environnement.")
    sys.exit(1)

# ─────────────────────────────────────────────────────────────
# 3) Intents
# ─────────────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True        # utile pour tes systèmes par messages
intents.members = True                # utile pour profils, joins etc.
intents.guilds = True
intents.reactions = True
intents.voice_states = True           # pour l’économie vocale

# ─────────────────────────────────────────────────────────────
# 4) Bot
# ─────────────────────────────────────────────────────────────
# main.py (extrait) — remplace ta classe Bot par ceci:

class GotValisBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix=commands.when_mentioned_or("!"),
            intents=intents,
            help_command=None,
        )
        self.initial_extensions = [
            # charge uniquement ce qui existe chez toi; sinon commente la ligne
            "cogs.info_cog",
            "cogs.help_cog",
            "cogs.inventory_cog",
            "cogs.shop_cog",
            "cogs.daily_cog",
            "cogs.gacha_cog",
            "cogs.economy_cog",
            "cogs.ravitaillement",
            "cogs.supply_special",
            "cogs.combat_cog",
            "cogs.leaderboard_cog",
            "cogs.admin_cog",
            # socials:
            "cogs.social.love",
            "cogs.social.hug",
            "cogs.social.kiss",
            "cogs.social.lick",
            "cogs.social.pat",
            "cogs.social.punch",
            "cogs.social.slap",
            "cogs.social.bite",
        ]

    async def setup_hook(self) -> None:
        from data import storage
        await storage.init_storage()  # crée /persistent/data.json si absent

        # charger les cogs
        for ext in self.initial_extensions:
            try:
                await self.load_extension(ext)
                log.info("Extension OK: %s", ext)
            except Exception as e:
                log.error("Extension KO: %s → %s", ext, e)

        # sync slash
        await self._sync_app_commands()

    async def _sync_app_commands(self):
        try:
            if GUILD_ID:
                guild = discord.Object(id=int(GUILD_ID))
                self.tree.copy_global_to(guild=guild)
                await self.tree.sync(guild=guild)
                log.info("Slash commands synchronisées (guild: %s)", GUILD_ID)
            else:
                await self.tree.sync()
                log.info("Slash commands synchronisées (globales).")
        except Exception as e:
            log.exception("Erreur de sync: %s", e)

    async def on_ready(self):
        log.info("Connecté en tant que %s (%s)", self.user, self.user.id)
        await self.change_presence(
            activity=discord.Activity(type=discord.ActivityType.watching, name="le réseau GotValis"),
            status=discord.Status.online
        )

bot = GotValisBot()

# ─────────────────────────────────────────────────────────────
# 5) Petite commande admin: /resync pour resynchroniser sur demande
# ─────────────────────────────────────────────────────────────
class DevCog(commands.Cog):
    def __init__(self, bot: GotValisBot):
        self.bot = bot

    @app_commands.default_permissions(administrator=True)
    @app_commands.command(name="resync", description="(Admin) Resynchronise les commandes slash.")
    async def resync(self, inter: discord.Interaction):
        await inter.response.defer(ephemeral=True, thinking=True)
        try:
            await self.bot._sync_app_commands()
            await inter.followup.send("✅ Slash commands resynchronisées.", ephemeral=True)
        except Exception as e:
            await inter.followup.send(f"❌ Erreur: `{e}`", ephemeral=True)

async def _add_dev_cog():
    try:
        await bot.add_cog(DevCog(bot))
    except Exception as e:
        log.error("Impossible d’ajouter DevCog: %s", e)

# ─────────────────────────────────────────────────────────────
# 6) Entrée
# ─────────────────────────────────────────────────────────────
async def main():
    async with bot:
        await _add_dev_cog()
        await bot.start(TOKEN)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Arrêt demandé (Ctrl+C).")

# main.py
from __future__ import annotations

import os
import sys
import asyncio
import logging
import importlib.util
from typing import List

import discord
from discord.ext import commands
from discord import app_commands

# ─────────────────────────────────────────────────────────────
# 0) Logging
# ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)
log = logging.getLogger("gotvalis.main")

# ─────────────────────────────────────────────────────────────
# 1) Token / Guild
# ─────────────────────────────────────────────────────────────
TOKEN = os.getenv("GOTVALIS_TOKEN") or os.getenv("DISCORD_TOKEN")
GUILD_ID_ENV = os.getenv("GUILD_ID")  # facultatif: sync rapide par serveur
GUILD_ID = int(GUILD_ID_ENV) if GUILD_ID_ENV and GUILD_ID_ENV.isdigit() else None

if not TOKEN:
    log.error("Aucun token. Définis GOTVALIS_TOKEN (ou DISCORD_TOKEN) dans l'environnement.")
    sys.exit(1)

# ─────────────────────────────────────────────────────────────
# 2) Intents
# ─────────────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True
intents.reactions = True
intents.voice_states = True

# ─────────────────────────────────────────────────────────────
# 3) Utilitaires
# ─────────────────────────────────────────────────────────────
def _spec_exists(mod: str) -> bool:
    """Vérifie si un module/extension Python existe avant load_extension."""
    try:
        return importlib.util.find_spec(mod) is not None
    except Exception:
        return False

# ─────────────────────────────────────────────────────────────
# 4) Bot
# ─────────────────────────────────────────────────────────────
class GotValisBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix=commands.when_mentioned_or("!"),
            intents=intents,
            help_command=None,
        )
        # Liste d’extensions (charge seulement si présentes)
        self.initial_extensions: List[str] = [
            # Core game
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
            # Social (nécessitent un setup(interaction) dans chaque fichier)
            "cogs.social.love",
            "cogs.social.hug",
            "cogs.social.kiss",
            "cogs.social.lick",
            "cogs.social.pat",
            "cogs.social.punch",
            "cogs.social.slap",
            "cogs.social.bite",
        ]

    # S'exécute APRÈS login/avant ready → parfait pour init DB + charger cogs + sync
    async def setup_hook(self) -> None:
        # 4.1 Init du stockage JSON (tickets/CD/config) si tu l’utilises
        try:
            from data import storage  # type: ignore
            await storage.init_storage()
            log.info("Storage initialisé (data.json prêt).")
        except Exception as e:
            log.warning("Storage JSON non initialisé: %s", e)

        # 4.2 Init des bases SQLite (économie/inventaire/stats/effets)
        try:
            from economy_db import init_economy_db  # type: ignore
            await init_economy_db()
            log.info("SQLite OK: economy_db")
        except Exception as e:
            log.warning("SQLite KO: economy_db → %s", e)

        try:
            from inventory_db import init_inventory_db  # type: ignore
            await init_inventory_db()
            log.info("SQLite OK: inventory_db")
        except Exception as e:
            log.warning("SQLite KO: inventory_db → %s", e)

        # Optionnels selon ton projet
        try:
            from stats_db import init_stats_db  # type: ignore
            await init_stats_db()
            log.info("SQLite OK: stats_db")
        except Exception as e:
            log.warning("SQLite KO: stats_db → %s", e)

        try:
            from effects_db import init_effects_db  # type: ignore
            await init_effects_db()
            log.info("SQLite OK: effects_db")
        except Exception as e:
            log.warning("SQLite KO: effects_db → %s", e)

        # 4.3 Charger les cogs existants (skip propre si absent/malspec)
        for ext in self.initial_extensions:
            if not _spec_exists(ext):
                log.error("Extension absente (skip): %s", ext)
                continue
            try:
                await self.load_extension(ext)
                log.info("Extension OK: %s", ext)
            except Exception as e:
                log.error("Extension KO: %s → %s", ext, e)

        # 4.4 Sync slash (guild ciblée si GUILD_ID fourni, sinon global)
        await self._sync_app_commands()

        # 4.5 (Optionnel) Présence initiale sécurisée après login/ws prêt
        # On ne fait PAS de change_presence ici si le WS n’est pas prêt.
        # on_ready s’en charge proprement.

    async def _sync_app_commands(self):
        try:
            if GUILD_ID:
                guild = discord.Object(id=GUILD_ID)
                self.tree.copy_global_to(guild=guild)
                await self.tree.sync(guild=guild)
                log.info("Slash synchronisées (guild: %s)", GUILD_ID)
            else:
                await self.tree.sync()
                log.info("Slash synchronisées (globales).")
        except Exception as e:
            log.exception("Erreur de sync: %s", e)

    async def on_ready(self):
        # Appelé quand le WS est prêt → on peut changer la présence sans erreur.
        log.info("Connecté en tant que %s (%s)", self.user, getattr(self.user, "id", "?"))
        try:
            await self.change_presence(
                activity=discord.Activity(type=discord.ActivityType.watching, name="le réseau GotValis"),
                status=discord.Status.online
            )
        except Exception as e:
            log.warning("Impossible de changer la présence maintenant: %s", e)

bot = GotValisBot()

# ─────────────────────────────────────────────────────────────
# 5) Petite commande admin: /resync pour resynchroniser
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
    # Ajoute DevCog avant le démarrage
    async with bot:
        await _add_dev_cog()
        await bot.start(TOKEN)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Arrêt demandé (Ctrl+C).")

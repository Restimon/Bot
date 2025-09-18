# main.py
from __future__ import annotations

import os
import sys
import asyncio
import logging
import importlib
import importlib.util
import pathlib
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
# 1) PYTHONPATH (racine du projet)
# ─────────────────────────────────────────────────────────────
ROOT = pathlib.Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ─────────────────────────────────────────────────────────────
# 2) Token / Guild
# ─────────────────────────────────────────────────────────────
TOKEN = os.getenv("GOTVALIS_TOKEN") or os.getenv("DISCORD_TOKEN")
GUILD_ID_ENV = os.getenv("GUILD_ID")
GUILD_ID = int(GUILD_ID_ENV) if (GUILD_ID_ENV and GUILD_ID_ENV.isdigit()) else None

if not TOKEN:
    log.error("Aucun token. Définis GOTVALIS_TOKEN (ou DISCORD_TOKEN) dans l'environnement.")
    raise SystemExit(1)

# ─────────────────────────────────────────────────────────────
# 3) Intents
# ─────────────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True
intents.reactions = True
intents.voice_states = True

# ─────────────────────────────────────────────────────────────
# 4) Helpers
# ─────────────────────────────────────────────────────────────
def spec_exists(module_path: str) -> bool:
    """True si l’extension/module Python existe (importable)."""
    try:
        return importlib.util.find_spec(module_path) is not None
    except Exception:
        return False

async def try_init_db(mod_name: str, init_func: str) -> None:
    """
    Importe dynamiquement un module et appelle sa fonction d'init si dispo.
    Ex: await try_init_db('economy_db', 'init_economy_db')
    """
    if not spec_exists(mod_name):
        log.warning("SQLite KO: %s → module introuvable", mod_name)
        return
    try:
        mod = importlib.import_module(mod_name)
        fn = getattr(mod, init_func, None)
        if fn is None:
            log.warning("SQLite KO: %s → fonction %s absente", mod_name, init_func)
            return
        await fn()
        log.info("SQLite OK: %s.%s", mod_name, init_func)
    except Exception as e:
        log.warning("SQLite KO: %s → %s", mod_name, e)

# ─────────────────────────────────────────────────────────────
# 5) Bot
# ─────────────────────────────────────────────────────────────
class GotValisBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix=commands.when_mentioned_or("!"),
            intents=intents,
            help_command=None,
        )
        # Extensions à charger si elles existent
        self.initial_extensions: List[str] = [
            # Core
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
            "cogs.chat_ai",
            # Social (chaque fichier doit avoir async def setup(bot): …)
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
        # 5.1 Storage JSON (optionnel)
        try:
            if spec_exists("data.storage"):
                from data import storage  # type: ignore
                await storage.init_storage()
                log.info("Storage initialisé (data.json prêt).")
            else:
                log.info("data/storage.py absent : skip storage JSON.")
        except Exception as e:
            log.warning("Storage JSON non initialisé: %s", e)

        # 5.2 SQLite (si présents à la racine du projet)
        await try_init_db("economy_db", "init_economy_db")
        await try_init_db("inventory_db", "init_inventory_db")
        await try_init_db("stats_db", "init_stats_db")
        await try_init_db("effects_db", "init_effects_db")

        # 5.3 Charger les cogs existants
        for ext in self.initial_extensions:
            if not spec_exists(ext):
                log.error("Extension absente (skip): %s", ext)
                continue
            try:
                await self.load_extension(ext)
                log.info("Extension OK: %s", ext)
            except Exception as e:
                log.error("Extension KO: %s → %s", ext, e)

        # 5.4 Sync slash
        await self.sync_slash()

    async def sync_slash(self) -> None:
        try:
            if GUILD_ID:
                guild = discord.Object(id=GUILD_ID)
                # Copie des globales dans la guilde cible pour publication instantanée
                self.tree.copy_global_to(guild=guild)
                cmds = await self.tree.sync(guild=guild)
                log.info("Slash synchronisées (guild: %s, %d cmds).", GUILD_ID, len(cmds))
            else:
                cmds = await self.tree.sync()
                log.info("Slash synchronisées (globales, %d cmds).", len(cmds))
        except Exception as e:
            log.exception("Erreur de sync: %s", e)

    async def on_ready(self):
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
# 6) DEV / ADMIN COG : sync & debug des slashs (slash + préfixe)
# ─────────────────────────────────────────────────────────────
class DevCog(commands.Cog):
    def __init__(self, bot: GotValisBot):
        self.bot = bot

    # ----- SLASH -----
    @app_commands.default_permissions(administrator=True)
    @app_commands.command(name="resync", description="(Admin) Resynchronise les commandes slash (global ou GUILD_ID).")
    async def resync(self, inter: discord.Interaction):
        await inter.response.defer(ephemeral=True, thinking=True)
        try:
            await self.bot.sync_slash()
            await inter.followup.send("✅ Slash commands resynchronisées.", ephemeral=True)
        except Exception as e:
            await inter.followup.send(f"❌ Erreur: `{e}`", ephemeral=True)

    @app_commands.default_permissions(administrator=True)
    @app_commands.command(name="sync_here", description="(Admin) Force la sync des slashs uniquement dans CE serveur.")
    async def sync_here(self, inter: discord.Interaction):
        if not inter.guild:
            await inter.response.send_message("❌ À utiliser dans un serveur.", ephemeral=True)
            return
        await inter.response.defer(ephemeral=True)
        try:
            synced = await self.bot.tree.sync(guild=discord.Object(id=inter.guild.id))
            names = ", ".join(sorted(f"/{c.name}" for c in synced))
            await inter.followup.send(f"✅ Sync locale OK ({len(synced)} cmds) : {names}", ephemeral=True)
        except Exception as e:
            await inter.followup.send(f"❌ Sync locale KO: `{type(e).__name__}: {e}`", ephemeral=True)

    @app_commands.default_permissions(administrator=True)
    @app_commands.command(name="list_cmds", description="(Admin) Liste les slashs disponibles dans CE serveur.")
    async def list_cmds(self, inter: discord.Interaction):
        if not inter.guild:
            await inter.response.send_message("❌ À utiliser dans un serveur.", ephemeral=True)
            return
        await inter.response.defer(ephemeral=True)
        try:
            cmds = await self.bot.tree.fetch_commands(guild=discord.Object(id=inter.guild.id))
            if not cmds:
                await inter.followup.send("ℹ️ Aucune commande publiée ici.", ephemeral=True)
                return
            lines = [f"• /{c.name} — {c.description or '(sans description)'}" for c in cmds]
            await inter.followup.send("\n".join(lines), ephemeral=True)
        except Exception as e:
            await inter.followup.send(f"❌ Impossible de lister : `{type(e).__name__}: {e}`", ephemeral=True)

    # ----- PRÉFIXE (bypass slash s'ils ne sont pas publiés) -----
    @commands.command(name="sync_here")
    @commands.has_permissions(administrator=True)
    async def sync_here_prefix(self, ctx: commands.Context):
        """Publie/maj les slash commands dans CE serveur."""
        try:
            synced = await self.bot.tree.sync(guild=discord.Object(id=ctx.guild.id))
            await ctx.reply(f"✅ Sync locale OK ({len(synced)} cmds). Réessaie les slashs (ex: /inv).", mention_author=False)
        except Exception as e:
            await ctx.reply(f"❌ Sync KO: `{type(e).__name__}: {e}`", mention_author=False)

    @commands.command(name="list_cmds")
    @commands.has_permissions(administrator=True)
    async def list_cmds_prefix(self, ctx: commands.Context):
        """Liste les slash commands publiées dans CE serveur."""
        try:
            cmds = await self.bot.tree.fetch_commands(guild=discord.Object(id=ctx.guild.id))
            if not cmds:
                await ctx.reply("ℹ️ Aucune slash command publiée ici.", mention_author=False)
                return
            lines = [f"• /{c.name} — {c.description or '(sans description)'}" for c in cmds]
            await ctx.reply("\n".join(lines), mention_author=False)
        except Exception as e:
            await ctx.reply(f"❌ Impossible de lister: `{type(e).__name__}: {e}`", mention_author=False)

async def _add_dev_cog():
    try:
        await bot.add_cog(DevCog(bot))
    except Exception as e:
        log.error("Impossible d’ajouter DevCog: %s", e)

# ─────────────────────────────────────────────────────────────
# 7) Entrée
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

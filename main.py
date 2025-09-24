# main.py
from __future__ import annotations

import os
import sys
import asyncio
import logging
import importlib
import importlib.util
import pathlib
from typing import List, Optional

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
# 1) PYTHONPATH racine
# ─────────────────────────────────────────────────────────────
ROOT = pathlib.Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ─────────────────────────────────────────────────────────────
# 2) Token / Guild IDs (multi-guild possible)
# ─────────────────────────────────────────────────────────────
def _read_token() -> str:
    tok = os.getenv("GOTVALIS_TOKEN") or os.getenv("DISCORD_TOKEN")
    if tok:
        return tok.strip()
    # fallback token.txt ou config.TOKEN
    tokfile = ROOT / "token.txt"
    if tokfile.exists():
        t = tokfile.read_text(encoding="utf-8").strip()
        if t:
            return t
    try:
        import config  # type: ignore
        if getattr(config, "TOKEN", None):
            return str(config.TOKEN).strip()
    except Exception:
        pass
    raise RuntimeError("Aucun token. Définis GOTVALIS_TOKEN (ou DISCORD_TOKEN), ou place un token dans token.txt.")

def _read_guild_ids() -> List[int]:
    # compat: GUILD_ID (un seul) / GUILD_IDS (liste séparée par virgules)
    out: List[int] = []
    one = os.getenv("GUILD_ID")
    many = os.getenv("GUILD_IDS")
    if one and one.isdigit():
        out.append(int(one))
    if many:
        for part in many.split(","):
            part = part.strip()
            if part.isdigit():
                out.append(int(part))
    # unique
    return list(dict.fromkeys(out))

TOKEN = _read_token()
TARGET_GUILDS = _read_guild_ids()  # vide => sync globale

# ─────────────────────────────────────────────────────────────
# 3) Intents
# ─────────────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.guilds = True
intents.members = True           # requis pour itérer les membres (ticks passifs / vocaux)
intents.messages = True
intents.message_content = True   # pour économie on_message
intents.reactions = True
intents.voice_states = True      # économie vocale

# ─────────────────────────────────────────────────────────────
# 4) Helpers import/init
# ─────────────────────────────────────────────────────────────
def spec_exists(module_path: str) -> bool:
    try:
        return importlib.util.find_spec(module_path) is not None
    except Exception:
        return False

async def try_init_db(mod_name: str, init_func: str) -> None:
    if not spec_exists(mod_name):
        log.info("Init DB: %s absent (skip)", mod_name)
        return
    try:
        mod = importlib.import_module(mod_name)
        fn = getattr(mod, init_func, None)
        if not fn:
            log.info("Init DB: %s.%s absent (skip)", mod_name, init_func)
            return
        await fn()
        log.info("Init DB OK: %s.%s", mod_name, init_func)
    except Exception as e:
        log.warning("Init DB KO: %s.%s → %s", mod_name, init_func, e)

# ─────────────────────────────────────────────────────────────
# 5) Bot
# ─────────────────────────────────────────────────────────────
# On liste large : seules les extensions présentes seront chargées
INITIAL_EXTENSIONS = [
    # Core / système
    "cogs.equip_cog",
    "cogs.passifs_cog",

    # Combat (si tu gardes /fight ici)
    "cogs.combat_cog",

    # ⬇️ AJOUTE CES DEUX LIGNES ⬇️
    "cogs.use_cog",
    "cogs.heal_cog",

    "cogs.daily_cog",
    "cogs.economie",
    "cogs.economy_cog",
    "cogs.shop_cog",
    "cogs.inventory_cog",
    "cogs.invocation_cog",
    "cogs.leaderboard_live",
    "cogs.admin_cog",
    "cogs.info_cog",
    "cogs.help_cog",
    "cogs.ravitaillement",
    "cogs.supply_special",
    "cogs.chat_ai",
    "cogs.stats_co",
    # Social
    "cogs.social.love",
    "cogs.social.hug",
    "cogs.social.kiss",
    "cogs.social.lick",
    "cogs.social.pat",
    "cogs.social.punch",
    "cogs.social.slap",
    "cogs.social.bite",
]

class GotValisBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix=commands.when_mentioned_or("!"),
            intents=intents,
            help_command=None,
            allowed_mentions=discord.AllowedMentions.none(),
        )
        self._half_hour_task: Optional[asyncio.Task] = None
        self._hourly_task: Optional[asyncio.Task] = None
        self._effects_loop_started = False  # flag lu par certains cogs

    async def setup_hook(self) -> None:
        # 5.1 Storage JSON (si présent)
        try:
            if spec_exists("data.storage"):
                from data import storage  # type: ignore
                await storage.init_storage()
                log.info("Storage JSON OK (data.json).")
            else:
                log.info("Storage JSON absent (data/storage.py).")
        except Exception as e:
            log.warning("Storage JSON KO: %s", e)

        # 5.2 Init SQLite (si modules présents)
        await try_init_db("economy_db", "init_economy_db")
        await try_init_db("inventory_db", "init_inventory_db")
        await try_init_db("stats_db", "init_stats_db")
        await try_init_db("effects_db", "init_effects_db")
        await try_init_db("shields_db", "init_shields_db")
        await try_init_db("tickets_db", "init_tickets_db")
        await try_init_db("passifs", "init_passifs_db")  # ← important pour les passifs

        # 5.3 Charger les extensions existantes
        for ext in INITIAL_EXTENSIONS:
            if not spec_exists(ext):
                log.info("Extension absente (skip): %s", ext)
                continue
            try:
                await self.load_extension(ext)
                log.info("Extension OK: %s", ext)
            except Exception as e:
                log.error("Extension KO: %s → %s", ext, e)

        # 5.4 Sync slash
        await self.sync_slash()

        # 5.5 Boucles passifs (ticks périodiques)
        self._half_hour_task = asyncio.create_task(self._half_hour_loop())
        self._hourly_task = asyncio.create_task(self._hourly_loop())

    async def sync_slash(self) -> None:
        try:
            if TARGET_GUILDS:
                for gid in TARGET_GUILDS:
                    guild = discord.Object(id=gid)
                    self.tree.copy_global_to(guild=guild)
                    synced = await self.tree.sync(guild=guild)
                    log.info("Slash sync OK (guild=%s) — %d cmds.", gid, len(synced))
            else:
                synced = await self.tree.sync()
                log.info("Slash sync globale OK — %d cmds.", len(synced))
        except Exception as e:
            log.exception("Erreur de sync slash: %s", e)

    async def on_ready(self):
        log.info("Connecté en tant que %s (%s)", self.user, getattr(self.user, "id", "?"))
        try:
            await self.change_presence(
                activity=discord.Activity(type=discord.ActivityType.playing, name="GotValis — /equip"),
                status=discord.Status.online
            )
        except Exception as e:
            log.warning("Presence KO: %s", e)

    # ─────────────────────────────────────────────────────────
    # Boucles passifs
    # ─────────────────────────────────────────────────────────
    async def _iter_all_unique_user_ids(self) -> List[int]:
        uids: List[int] = []
        seen = set()
        for g in self.guilds:
            for m in g.members:
                if m.bot:
                    continue
                if m.id not in seen:
                    seen.add(m.id)
                    uids.append(m.id)
        return uids

    async def _half_hour_loop(self):
        await self.wait_until_ready()
        log.info("Passifs: boucle demi-heure démarrée")
        while not self.is_closed():
            try:
                if spec_exists("passifs"):
                    from passifs import trigger  # import tardif
                    uids = await self._iter_all_unique_user_ids()
                    for uid in uids:
                        try:
                            await trigger("on_half_hour_tick", user_id=uid)
                        except Exception:
                            pass
                        await asyncio.sleep(0)  # yield
            except Exception as e:
                log.warning("Half-hour loop error: %r", e)
            await asyncio.sleep(30 * 60)

    async def _hourly_loop(self):
        await self.wait_until_ready()
        log.info("Passifs: boucle horaire démarrée")
        while not self.is_closed():
            try:
                if spec_exists("passifs"):
                    from passifs import trigger
                    uids = await self._iter_all_unique_user_ids()
                    for uid in uids:
                        try:
                            await trigger("on_hourly_tick", user_id=uid)
                        except Exception:
                            pass
                        await asyncio.sleep(0)
            except Exception as e:
                log.warning("Hourly loop error: %r", e)
            await asyncio.sleep(60 * 60)

    # ─────────────────────────────────────────────────────────
    # Gestion basique des erreurs de slash
    # ─────────────────────────────────────────────────────────
    async def on_tree_error(self, interaction: discord.Interaction, error: Exception):
        log.error("Slash error (%s): %r", getattr(interaction.command, 'name', '?'), error)
        try:
            if interaction.response.is_done():
                await interaction.followup.send("❌ Une erreur est survenue.", ephemeral=True)
            else:
                await interaction.response.send_message("❌ Une erreur est survenue.", ephemeral=True)
        except Exception:
            pass


bot = GotValisBot()

# ─────────────────────────────────────────────────────────────
# 6) Dev/Admin: commandes de maintenance
# ─────────────────────────────────────────────────────────────
class DevCog(commands.Cog):
    def __init__(self, bot: GotValisBot):
        self.bot = bot

    # -------- SLASH (admin) --------
    @app_commands.default_permissions(administrator=True)
    @app_commands.command(name="resync", description="(Admin) Resynchronise les slashs (globales ou par guild).")
    async def resync(self, inter: discord.Interaction):
        await inter.response.defer(ephemeral=True, thinking=True)
        try:
            await self.bot.sync_slash()
            await inter.followup.send("✅ Slash resynchronisées.", ephemeral=True)
        except Exception as e:
            await inter.followup.send(f"❌ Erreur: `{e}`", ephemeral=True)

    @app_commands.default_permissions(administrator=True)
    @app_commands.command(name="sync_here", description="(Admin) Force la sync des slashs uniquement ici.")
    async def sync_here(self, inter: discord.Interaction):
        if not inter.guild:
            return await inter.response.send_message("❌ À utiliser dans un serveur.", ephemeral=True)
        await inter.response.defer(ephemeral=True)
        try:
            synced = await self.bot.tree.sync(guild=discord.Object(id=inter.guild.id))
            names = ", ".join(sorted(f"/{c.name}" for c in synced))
            await inter.followup.send(f"✅ Sync locale OK ({len(synced)}): {names}", ephemeral=True)
        except Exception as e:
            await inter.followup.send(f"❌ Sync locale KO: `{type(e).__name__}: {e}`", ephemeral=True)

    @app_commands.default_permissions(administrator=True)
    @app_commands.command(name="list_cmds", description="(Admin) Liste les slashs publiées ici.")
    async def list_cmds(self, inter: discord.Interaction):
        if not inter.guild:
            return await inter.response.send_message("❌ À utiliser dans un serveur.", ephemeral=True)
        await inter.response.defer(ephemeral=True)
        try:
            cmds = await self.bot.tree.fetch_commands(guild=discord.Object(id=inter.guild.id))
            if not cmds:
                return await inter.followup.send("ℹ️ Aucune commande ici.", ephemeral=True)
            lines = [f"• /{c.name} — {c.description or '(sans description)'}" for c in cmds]
            await inter.followup.send("\n".join(lines), ephemeral=True)
        except Exception as e:
            await inter.followup.send(f"❌ Impossible de lister : `{type(e).__name__}: {e}`", ephemeral=True)

    # -------- PRÉFIXÉ (admin) --------
    @commands.command(name="sync_here")
    @commands.has_permissions(administrator=True)
    async def sync_here_prefix(self, ctx: commands.Context):
        try:
            synced = await self.bot.tree.sync(guild=discord.Object(id=ctx.guild.id))
            await ctx.reply(f"✅ Sync locale OK ({len(synced)}).", mention_author=False)
        except Exception as e:
            await ctx.reply(f"❌ Sync KO: `{type(e).__name__}: {e}`", mention_author=False)

    @commands.command(name="list_cmds")
    @commands.has_permissions(administrator=True)
    async def list_cmds_prefix(self, ctx: commands.Context):
        try:
            cmds = await self.bot.tree.fetch_commands(guild=discord.Object(id=ctx.guild.id))
            if not cmds:
                return await ctx.reply("ℹ️ Aucune slash command publiée ici.", mention_author=False)
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
async def _amain():
    async with bot:
        await _add_dev_cog()
        await bot.start(TOKEN)

if __name__ == "__main__":
    try:
        asyncio.run(_amain())
    except KeyboardInterrupt:
        log.info("Arrêt demandé (Ctrl+C).")

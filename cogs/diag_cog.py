from __future__ import annotations
import asyncio
from typing import List, Dict, Any
import aiosqlite
import discord
from discord.ext import commands
from discord import app_commands

TABLES_EXPECTED = [
    "player_equipment", "passive_counters",   # passifs.py
    "wallets", "wallet_logs",                 # economy_db
    # Les autres tables dépendent de ton implémentation :
    # adapte si besoin (inventory/effects/hp/shield, etc.)
]

COMMANDS_EXPECTED = [
    "equip","unequip","passif","whois",
    "fight","heal","use",
    "daily","wallet","give","top","earnings",
    "shop","buy","sell"
]

COGS_EXPECTED = {"EquipCog","CombatCog","DailyCog","Economie","ShopCog"}

OBJET_TYPES_MIN = {"attaque","soin","regen","poison","infection","virus","bouclier","vaccin","mysterybox","vol"}

class DiagCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="gv_diag", description="Diagnostic GotValis (admin seulement).")
    @app_commands.default_permissions(administrator=True)
    async def gv_diag(self, itx: discord.Interaction):
        await itx.response.defer(ephemeral=True)
        ok = "✅"
        ko = "❌"
        warn = "⚠️"

        lines: List[str] = []

        # 1) Cogs chargés
        loaded = set(self.bot.cogs.keys())
        miss_cogs = COGS_EXPECTED - loaded
        lines.append(f"**Cogs**: {ok} {sorted(loaded)}" if not miss_cogs
                     else f"**Cogs**: {ko} manquants={sorted(miss_cogs)}")

        # 2) Slash commands présentes
        cmds = [c.name for c in self.bot.tree.get_commands()]
        miss_cmds = [c for c in COMMANDS_EXPECTED if c not in cmds]
        lines.append(f"**Slash**: {ok} {sorted(cmds)}" if not miss_cmds
                     else f"**Slash**: {ko} manquantes={sorted(miss_cmds)}")

        # 3) Intents
        mc = getattr(self.bot.intents, "message_content", False)
        lines.append(f"**Intents**: message_content={'ON' if mc else 'OFF'} {'✅' if mc else '❌'}")

        # 4) DB: tables
        missing_tables: List[str] = []
        try:
            async with aiosqlite.connect("gotvalis.sqlite3") as db:
                for t in TABLES_EXPECTED:
                    async with db.execute(
                        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                        (t,)
                    ) as cur:
                        row = await cur.fetchone()
                        if not row:
                            missing_tables.append(t)
        except Exception as e:
            lines.append(f"**DB**: {ko} erreur d’accès: {e}")
        else:
            lines.append(f"**DB**: {ok} tables ok" if not missing_tables
                         else f"**DB**: {ko} tables manquantes={missing_tables}")

        # 5) passifs.trigger + alias
        try:
            import passifs
            trig = getattr(passifs, "trigger", None)
            if not callable(trig):
                lines.append(f"**passifs.trigger**: {ko} non trouvé")
            else:
                # ping rapide des alias utilisés par combat_cog
                async def _chk(ev: str, **ctx: Any) -> bool:
                    try:
                        res = await trig(ev, **ctx)
                        return isinstance(res, dict)
                    except Exception:
                        return False

                t1 = await _chk("before_damage", attacker_id=0, target_id=0, base_damage=1, is_crit=False, crit_multiplier=1.0, emoji="(t)", meta={})
                t2 = await _chk("before_heal", user_id=0, target_id=0, base_heal=1, emoji="(t)", meta={})
                t3 = await _chk("before_apply_effect", applier_id=0, target_id=0, effect_type="infection", value=1, interval=60, duration=60, emoji="(t)", meta={})
                t4 = await _chk("on_use_after", user_id=0, emoji="(t)")

                if all([t1,t2,t3,t4]):
                    lines.append(f"**passifs.trigger (alias)**: {ok}")
                else:
                    bad = []
                    if not t1: bad.append("before_damage")
                    if not t2: bad.append("before_heal")
                    if not t3: bad.append("before_apply_effect")
                    if not t4: bad.append("on_use_after")
                    lines.append(f"**passifs.trigger (alias)**: {ko} {bad}")
        except Exception as e:
            lines.append(f"**passifs.import**: {ko} {e}")

        # 6) OBJETS: au moins un de chaque type “clé”
        try:
            from utils import OBJETS
            have_types = {str(v.get("type")) for v in OBJETS.values() if isinstance(v, dict)}
            missing_types = [t for t in OBJET_TYPES_MIN if t not in have_types]
            lines.append(f"**OBJETS**: {ok} types={sorted(have_types)}" if not missing_types
                         else f"**OBJETS**: {warn} types manquants={sorted(missing_types)}")
        except Exception as e:
            lines.append(f"**OBJETS**: {ko} {e}")

        # 7) effects_loop lancé ?
        loop_started = bool(getattr(self.bot, "_effects_loop_started", False))
        lines.append(f"**effects_loop**: {'ON ' + ok if loop_started else 'OFF ' + warn}")

        # 8) leaderboard live hook (optionnel)
        try:
            import importlib
            lb = importlib.import_module("cogs.leaderboard_live")
            has_fn = hasattr(lb, "schedule_lb_update")
            lines.append(f"**leaderboard_live**: {'présent ' + ok if has_fn else 'module/fonction absente ' + warn}")
        except Exception:
            lines.append(f"**leaderboard_live**: {warn} non trouvé (optionnel)")

        e = discord.Embed(title="🧪 Diagnostic GotValis", colour=discord.Colour.blurple(),
                          description="\n".join(f"• {ln}" for ln in lines))
        await itx.followup.send(embed=e, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(DiagCog(bot))

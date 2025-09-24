# cogs/effects_cog.py
from __future__ import annotations

import asyncio
import discord
from discord.ext import commands

# Boucle & broadcaster fournis par le backend des effets
from effects_db import effects_loop, set_broadcaster


class EffectsCog(commands.Cog):
    """
    Branche un broadcaster d'effets (ticks DoT/HoT).
    ⚠️ Ne démarre PAS une deuxième boucle si le combat_cog l’a déjà lancée.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # On branche notre broadcaster : effects_db nous appellera avec (guild_id, channel_id, payload)
        set_broadcaster(self._broadcast)

    # --------------------------------------------------------------------- #
    # Broadcaster : reçoit un payload "libre" défini côté effects_db.
    # On prend en charge :
    # - payload["type"] == "shield_broken" OU payload["shield_broken"] == True
    #     champs utiles: user_id, cause in {"poison","infection","brulure"}
    # - payload "générique" : title, lines, color, image, footer, fields
    # --------------------------------------------------------------------- #
    async def _broadcast(self, guild_id: int, channel_id: int, payload: dict):
        try:
            guild = self.bot.get_guild(int(guild_id))
            if not guild:
                return
            ch = guild.get_channel(int(channel_id))
            if not isinstance(ch, (discord.TextChannel, discord.Thread)):
                return

            # --- Cas spécial : bouclier détruit (aligné avec /fight)
            if payload.get("type") == "shield_broken" or payload.get("shield_broken"):
                uid = payload.get("user_id")
                member = None
                if uid:
                    try:
                        member = guild.get_member(int(uid))
                    except Exception:
                        member = None

                who = member.mention if member else (f"<@{uid}>" if uid else "Quelqu'un")
                cause = str(payload.get("cause") or "").strip().lower()
                cause_txt = ""
                if cause == "poison":
                    cause_txt = " sous l'effet du poison."
                elif cause == "infection":
                    cause_txt = " sous l'effet de l'infection."
                elif cause == "brulure":
                    cause_txt = " sous l'effet de la brûlure."

                emb = discord.Embed(
                    title="🛡️ Bouclier détruit",
                    description=f"Le bouclier de {who} a été **détruit**{cause_txt}",
                    color=discord.Color.blurple()
                )
                await ch.send(embed=emb)
                return

            # --- Cas générique : message/tick standard
            title = str(payload.get("title") or "GotValis")
            lines = payload.get("lines") or []
            try:
                color_val = int(payload.get("color")) if "color" in payload else discord.Color.blurple().value
            except Exception:
                color_val = discord.Color.blurple().value

            embed = discord.Embed(
                title=title,
                description="\n".join(map(str, lines)) if lines else discord.Embed.Empty,
                color=color_val
            )

            # Image optionnelle
            img = str(payload.get("image") or payload.get("gif") or "")
            if img.startswith("http"):
                embed.set_image(url=img)

            # Footer optionnel
            footer = str(payload.get("footer") or "")
            if footer:
                embed.set_footer(text=footer)

            # Fields optionnels: [{"name": "...", "value":"...", "inline": True/False}, ...]
            fields = payload.get("fields")
            if isinstance(fields, (list, tuple)):
                for f in fields:
                    try:
                        name = str(f.get("name", ""))
                        value = str(f.get("value", ""))
                        inline = bool(f.get("inline", False))
                        if name or value:
                            embed.add_field(name=name or "​", value=value or "​", inline=inline)
                    except Exception:
                        continue

            await ch.send(embed=embed)

        except Exception:
            # On avale les erreurs pour ne pas casser la boucle d'effets
            return

    # --------------------------------------------------------------------- #
    # Démarrage conditionnel de la boucle des effets
    # --------------------------------------------------------------------- #
    @commands.Cog.listener()
    async def on_ready(self):
        # Démarre la boucle UNIQUEMENT si aucune autre boucle ne tourne déjà
        # (combat_cog la démarre aussi et pose le flag _effects_loop_started)
        if getattr(self.bot, "_effects_loop_started", False):
            return

        async def providers():
            # Ici, on ne fournit pas de couples (guild_id, channel_id) par défaut.
            # D'autres cogs (ex: combat_cog) peuvent "remember" les salons cibles pour les ticks.
            return []

        self.bot._effects_loop_started = True
        asyncio.create_task(effects_loop(get_targets=providers, interval=60))


async def setup(bot: commands.Bot):
    await bot.add_cog(EffectsCog(bot))

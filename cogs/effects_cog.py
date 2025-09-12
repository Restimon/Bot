# cogs/effects_cog.py
import discord
from discord.ext import commands, tasks
from effects_db import effects_loop, set_broadcaster

class EffectsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        set_broadcaster(self._broadcast)

    async def _broadcast(self, guild_id: int, channel_id: int, payload: dict):
        guild = self.bot.get_guild(guild_id)
        if not guild: return
        ch = guild.get_channel(channel_id)
        if not ch: return
        embed = discord.Embed(title=payload.get("title",""), description="\n".join(payload.get("lines", [])), color=payload.get("color", 0))
        await ch.send(embed=embed)

    @commands.Cog.listener()
    async def on_ready(self):
        # Démarre la boucle effets (une seule fois)
        if not hasattr(self.bot, "_effects_task"):
            # retourne la liste des (guild_id, channel_id) où poster les ticks
            def providers():
                # TODO: remplace par ton stockage réel des salons combat par serveur
                # fallback: rien => pas de broadcast mais les ticks s'appliquent quand même
                return []
            self.bot._effects_task = self.bot.loop.create_task(effects_loop(providers))

async def setup(bot):
    await bot.add_cog(EffectsCog(bot))

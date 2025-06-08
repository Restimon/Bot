import discord
from storage import leaderboard, hp
from embeds import build_embed_from_item
from leaderboard_utils import update_leaderboard
from data import leaderboard
from economy_utils import get_gotcoins

async def build_leaderboard_embed(bot: discord.Client, guild: discord.Guild) -> discord.Embed:
    medals = ["🥇", "🥈", "🥉"]
    guild_id = str(guild.id)
    server_lb = leaderboard.get(guild_id, {})

    # Trié par GotCoins
    sorted_lb = sorted(
        server_lb.items(),
        key=lambda x: get_gotcoins(x[1]),
        reverse=True
    )

    lines = []
    for rank, (uid, stats) in enumerate(sorted_lb[:10]):
        member = guild.get_member(int(uid))
        if not member:
            continue

        total_gotcoins = get_gotcoins(stats)
        prefix = medals[rank] if rank < len(medals) else f"{rank + 1}."

        lines.append(
            f"{prefix} **{member.display_name}** → 💰 **{total_gotcoins} GotCoins**"
        )

    embed = discord.Embed(
        title=f"🏆 Classement de richesse - GotValis",
        description="\n".join(lines) if lines else "*Aucun joueur valide trouvé.*",
        color=discord.Color.gold()
    )

    embed.add_field(
        name="📊 Nombre de citoyens actifs",
        value=f"{len(server_lb)} joueurs enregistrés",
        inline=False
    )

    embed.set_footer(text="💰 Les GotCoins représentent votre richesse accumulée.")
    return embed

import discord
from utils import leaderboard

async def build_leaderboard_embed(bot: discord.Client, guild: discord.Guild) -> discord.Embed:
    medals = ["🥇", "🥈", "🥉"]
    guild_id = str(guild.id)
    server_lb = leaderboard.get(guild_id, {})

    # Trier par total (dégâts + soin)
    sorted_lb = sorted(server_lb.items(), key=lambda x: x[1]['degats'] + x[1]['soin'], reverse=True)

    lines = []
    rank = 0
    for uid, stats in sorted_lb:
        member = guild.get_member(int(uid))
        if not member:
            continue

        if rank >= 10:
            break

        total = stats["degats"] + stats["soin"]
        prefix = medals[rank] if rank < len(medals) else f"{rank + 1}."
        lines.append(f"{prefix} **{member.display_name}** → 🗡️ {stats['degats']} | 💚 {stats['soin']} = **{total}** points")
        rank += 1

    embed = discord.Embed(
        title=f"🏆 Classement de {guild.name}",
        description="\n".join(lines) if lines else "*Aucun joueur valide trouvé.*",
        color=discord.Color.gold()
    )
    embed.set_footer(text="Classement propre à ce serveur.")
    return embed

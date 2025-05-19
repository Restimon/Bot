import discord
from utils import leaderboard

async def build_leaderboard_embed(bot: discord.Client) -> discord.Embed:
    from utils import leaderboard

    medals = ["🥇", "🥈", "🥉"]
    sorted_lb = sorted(leaderboard.items(), key=lambda x: x[1]['degats'], reverse=True)

    lines = []
    rank = 0
    for uid, stats in sorted_lb:
        user = None

        # Essayer de récupérer le pseudo via les guilds
        for guild in bot.guilds:
            member = guild.get_member(int(uid))
            if member:
                user = member
                break

        if not user:
            continue

        if rank >= 10:
            break

        total = stats["degats"] + stats["soin"]
        prefix = medals[rank] if rank < len(medals) else f"{rank + 1}."
        lines.append(f"{prefix} **{user.display_name}** → 🗡️ {stats['degats']} | 💚 {stats['soin']} = **{total}** points")
        rank += 1

    embed = discord.Embed(
        title="🏆 Classement selon SomniCorp",
        description="\n".join(lines) if lines else "*Aucun joueur valide trouvé.*",
        color=discord.Color.gold()
    )
    embed.set_footer(text="SomniCorp vous remercie de votre participation.")
    return embed

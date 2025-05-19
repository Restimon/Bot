import discord
from utils import leaderboard

async def build_leaderboard_embed(bot: discord.Client) -> discord.Embed:
    """Construit un embed avec le classement SomniCorp, en ignorant les utilisateurs inconnus."""
    medals = ["🥇", "🥈", "🥉"]
    sorted_lb = sorted(leaderboard.items(), key=lambda x: x[1]['degats'] + x[1]['soin'], reverse=True)

    rank = 0
    lines = []
    for uid, stats in sorted_lb:
        user = bot.get_user(int(uid))
        if not user:
            continue  # Ignore les utilisateurs inconnus

        if rank >= 10:
            break

        prefix = medals[rank] if rank < len(medals) else f"{rank + 1}."
        total = stats["degats"] + stats["soin"]
        lines.append(f"{prefix} **{user.name}** → 🗡️ {stats['degats']} | 💚 {stats['soin']} = **{total}** points")
        rank += 1

    embed = discord.Embed(
        title="🏆 Classement selon SomniCorp",
        description="\n".join(lines) if lines else "*Aucun joueur valide trouvé.*",
        color=discord.Color.gold()
    )
    embed.set_footer(text="Classement mis à jour automatiquement par SomniCorp.")
    return embed

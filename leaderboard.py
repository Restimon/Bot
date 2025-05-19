import discord
from utils import leaderboard

async def build_leaderboard_embed(bot: discord.Client) -> discord.Embed:
    """Construit un embed avec le classement SomniCorp, en ignorant les utilisateurs inconnus."""
    medals = ["🥇", "🥈", "🥉"]
    sorted_lb = sorted(leaderboard.items(), key=lambda x: x[1]['degats'], reverse=True)

    lines = []
    rank = 0
    for uid, stats in sorted_lb:
        user = bot.get_user(int(uid))
        if not user:
            continue  # Ignore les utilisateurs inconnus

        prefix = medals[rank] if rank < len(medals) else f"{rank + 1}."
        lines.append(f"{prefix} **{user.name}** : 🗡️ {stats['degats']} | 💚 {stats['soin']}")
        rank += 1

    embed = discord.Embed(
        title="🏆 Classement selon SomniCorp",
        description="\n".join(lines) if lines else "*Aucune donnée disponible.*",
        color=discord.Color.gold()
    )
    embed.set_footer(text="Mise à jour automatique toutes les 5 minutes.")
    return embed

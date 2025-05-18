import discord
from utils import leaderboard

def build_leaderboard_embed(bot: discord.Client) -> discord.Embed:
    """Construit un embed avec le classement SomniCorp."""
    lines = []
    medals = ["🥇", "🥈", "🥉"]
    sorted_lb = sorted(leaderboard.items(), key=lambda x: x[1]['degats'], reverse=True)

    for i, (uid, stats) in enumerate(sorted_lb):
        member = bot.get_user(int(uid))
        prefix = medals[i] if i < len(medals) else "🔹"
        name = member.name if member else f"ID {uid}"
        lines.append(f"{prefix} {name} : 🗡️ {stats['degats']} | 💚 {stats['soin']}")

    embed = discord.Embed(
        title="🏆 Classement selon SomniCorp",
        description="\n".join(lines) if lines else "Aucune donnée à afficher pour l’instant.",
        color=discord.Color.gold()
    )
    embed.set_footer(text="Classement mis à jour automatiquement par SomniCorp.")
    return embed

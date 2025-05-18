import discord
from utils import leaderboard

async def build_leaderboard_embed(bot: discord.Client) -> discord.Embed:
    lines = []
    medals = ["🥇", "🥈", "🥉"]
    sorted_lb = sorted(leaderboard.items(), key=lambda x: x[1]['degats'], reverse=True)

    for i, (uid, stats) in enumerate(sorted_lb):
        try:
            user = bot.get_user(int(uid)) or await bot.fetch_user(int(uid))
            name = user.name
        except Exception:
            name = f"ID {uid}"

        prefix = medals[i] if i < len(medals) else "🔹"
        lines.append(f"{prefix} {name} : 🗡️ {stats['degats']} | 💚 {stats['soin']}")

    embed = discord.Embed(
        title="🏆 Classement selon SomniCorp",
        description="\n".join(lines) if lines else "Aucune donnée à afficher pour l’instant.",
        color=discord.Color.gold()
    )
    embed.set_footer(text="Classement mis à jour automatiquement par SomniCorp.")
    return embed

import discord
from storage import leaderboard, hp  # 🔧 ajoute hp ici
from embeds import build_embed_from_item
from leaderboard_utils import update_leaderboard
from data import leaderboard

async def build_leaderboard_embed(bot: discord.Client, guild: discord.Guild) -> discord.Embed:
    medals = ["🥇", "🥈", "🥉"]
    guild_id = str(guild.id)
    server_lb = leaderboard.get(guild_id, {})

    sorted_lb = sorted(
        server_lb.items(),
        key=lambda x: x[1]['degats'] + x[1]['soin'] + x[1].get('kills', 0) * 50 - x[1].get('morts', 0) * 25,
        reverse=True
    )

    lines = []
    for rank, (uid, stats) in enumerate(sorted_lb[:10]):
        member = guild.get_member(int(uid))
        if not member:
            continue

        degats = stats.get("degats", 0)
        soin = stats.get("soin", 0)
        kills = stats.get("kills", 0)
        morts = stats.get("morts", 0)
        total = degats + soin + (kills * 50) - (morts * 25)
        current_hp = hp.get(guild_id, {}).get(uid, 100)
        prefix = medals[rank] if rank < len(medals) else f"{rank + 1}."

        lines.append(
            f"{prefix} **{member.display_name}** → "
            f"🗡️ {degats} | 💚 {soin} | ☠️ {kills} | 💀 {morts} = **{total}** points | ❤️ {current_hp} PV"
        )

    embed = discord.Embed(
        title=f"🏆 Classement de {guild.name}",
        description="\n".join(lines) if lines else "*Aucun joueur valide trouvé.*",
        color=discord.Color.gold()
    )

    embed.add_field(
        name="📊 Total joueurs actifs",
        value=f"{len(server_lb)} joueurs enregistrés",
        inline=False
    )

    embed.set_footer(text="Classement propre à ce serveur.")
    return embed

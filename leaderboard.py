import discord
from storage import leaderboard  

async def build_leaderboard_embed(bot: discord.Client, guild: discord.Guild) -> discord.Embed:
    """
    Génère un embed affichant le classement SomniCorp pour un serveur donné.
    """
    medals = ["🥇", "🥈", "🥉"]
    guild_id = str(guild.id)
    server_lb = leaderboard.get(guild_id, {})

    # Trier les utilisateurs par total de points (dégâts + soins)
    sorted_lb = sorted(
        server_lb.items(),
        key=lambda x: x[1]['degats'] + x[1]['soin'],
        reverse=True
    )

    lines = []
    for rank, (uid, stats) in enumerate(sorted_lb[:10]):  # max 10 joueurs
        member = guild.get_member(int(uid))
        if not member:
            continue  # ignorer les membres non trouvés (ex : ont quitté le serveur)

        total = stats["degats"] + stats["soin"]
        prefix = medals[rank] if rank < len(medals) else f"{rank + 1}."
        lines.append(
            f"{prefix} **{member.display_name}** → 🗡️ {stats['degats']} | 💚 {stats['soin']} = **{total}** points"
        )

    embed = discord.Embed(
        title=f"🏆 Classement de {guild.name}",
        description="\n".join(lines) if lines else "*Aucun joueur valide trouvé.*",
        color=discord.Color.gold()
    )
    embed.set_footer(text="Classement propre à ce serveur.")
    return embed

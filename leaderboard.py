import discord
from storage import leaderboard, hp  # 🔧 ajoute hp ici

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
        current_hp = hp.get(guild_id, {}).get(uid, 100)  # 🔥 récupération des PV
        prefix = medals[rank] if rank < len(medals) else f"{rank + 1}."
        lines.append(
            f"{prefix} **{member.display_name}** → "
            f"🗡️ {stats['degats']} | 💚 {stats['soin']} | ☠️ {stats.get('kills', 0)} | 💀 {stats.get('morts', 0)} = "
            f"**{total}** points | ❤️ {current_hp} PV"
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

import discord
from economy import gotcoins_balance
from storage import hp
from data import shields  # si ton shield est stocké ici, ajuste selon ton code

async def build_leaderboard_embed(bot: discord.Client, guild: discord.Guild) -> discord.Embed:
    from storage import hp, shields
    from economy import gotcoins_balance

    medals = ["🥇", "🥈", "🥉"]
    guild_id = str(guild.id)
    server_balance = gotcoins_balance.get(guild_id, {})
    server_hp = hp.get(guild_id, {})
    server_shields = shields.get(guild_id, {})

    # Trié par argent pur
    sorted_lb = sorted(
        server_balance.items(),
        key=lambda x: x[1],
        reverse=True
    )

    lines = []
    for rank, (uid, balance) in enumerate(sorted_lb[:10]):
        try:
            int_uid = int(uid)
            member = guild.get_member(int_uid)
            if not member:
                continue  # Si le membre n'est plus dans le serveur, on l'ignore
        except (ValueError, TypeError):
            print(f"⚠️ UID non valide ignoré : {uid}")
            continue

        pv = server_hp.get(uid, 100)
        pb = server_shields.get(uid, 0)

        prefix = medals[rank] if rank < len(medals) else f"{rank + 1}."

        if pb > 0:
            line = (
                f"{prefix} **{member.display_name}** → 💰 **{balance} GotCoins** | "
                f"❤️ {pv} PV / 🛡️ {pb} PB"
            )
        else:
            line = (
                f"{prefix} **{member.display_name}** → 💰 **{balance} GotCoins** | "
                f"❤️ {pv} PV"
            )

        lines.append(line)

    embed = discord.Embed(
        title=f"🏆 Classement de richesse - GotValis",
        description="\n".join(lines) if lines else "*Aucun joueur valide trouvé.*",
        color=discord.Color.gold()
    )

    embed.add_field(
        name="📊 Nombre de citoyens actifs",
        value=f"{len(server_balance)} joueurs enregistrés",
        inline=False
    )

    embed.set_footer(text="💰 Les GotCoins représentent votre richesse accumulée.")
    return embed

import discord
from economy import gotcoins_balance
from storage import hp
from data import shield_status  # si ton shield est stocké ici, ajuste selon ton code

async def build_leaderboard_embed(bot: discord.Client, guild: discord.Guild) -> discord.Embed:
    medals = ["🥇", "🥈", "🥉"]
    guild_id = str(guild.id)
    server_balance = gotcoins_balance.get(guild_id, {})

    # Trié par balance réelle
    sorted_lb = sorted(
        server_balance.items(),
        key=lambda x: x[1],  # balance pure
        reverse=True
    )

    lines = []
    for rank, (uid, balance) in enumerate(sorted_lb[:10]):
        member = guild.get_member(int(uid))
        if not member:
            continue

        prefix = medals[rank] if rank < len(medals) else f"{rank + 1}."

        # PV
        current_hp = hp.get(guild_id, {}).get(uid, 100)

        # PB (Points de bouclier)
        pb = shield_status.get(guild_id, {}).get(uid, {}).get("value", 0)

        # Ligne : montant + PV + PB éventuel
        if pb > 0:
            line = (
                f"{prefix} **{member.display_name}** → 💰 **{balance} GotCoins** | "
                f"❤️ {current_hp} PV / 🛡️ {pb} PB"
            )
        else:
            line = (
                f"{prefix} **{member.display_name}** → 💰 **{balance} GotCoins** | "
                f"❤️ {current_hp} PV"
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

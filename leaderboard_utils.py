from data import leaderboard
from economy import add_gotcoins

def update_leaderboard(guild_id, user_id, points, kill=0, death=0):
    leaderboard.setdefault(guild_id, {})
    leaderboard[guild_id].setdefault(user_id, {"degats": 0, "soin": 0, "kills": 0, "morts": 0})

    # Maj leaderboard (combat stats)
    leaderboard[guild_id][user_id]["degats"] += points
    leaderboard[guild_id][user_id]["kills"] += kill
    leaderboard[guild_id][user_id]["morts"] += death

    # Maj économie réelle
    if points > 0:
        add_gotcoins(guild_id, user_id, points, category="degats")
    if kill > 0:
        add_gotcoins(guild_id, user_id, kill * 50, category="kills")
    if death > 0:
        add_gotcoins(guild_id, user_id, -death * 25, category="morts")

from data import leaderboard

def update_leaderboard(guild_id, user_id, points, kill=0, death=0):
    leaderboard.setdefault(guild_id, {})
    leaderboard[guild_id].setdefault(user_id, {"degats": 0, "soin": 0, "kills": 0, "morts": 0})
    leaderboard[guild_id][user_id]["degats"] += points
    leaderboard[guild_id][user_id]["kills"] += kill
    leaderboard[guild_id][user_id]["morts"] += death

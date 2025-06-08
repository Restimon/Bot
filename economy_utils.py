def get_gotcoins(user_stats):
    return (
        user_stats.get("degats", 0)
        + user_stats.get("soin", 0)
        + user_stats.get("kills", 0) * 50
        - user_stats.get("morts", 0) * 25
    )

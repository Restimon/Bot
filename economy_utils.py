def get_gotcoins(user_stats):
    return (
        user_stats.get("degats", 0)
        + user_stats.get("soin", 0)
        + user_stats.get("kills", 0) * 50
        - user_stats.get("morts", 0) * 25
    )

# Gain par message
def compute_message_gains(message_content):
    length = len(message_content.strip())
    if length == 0:
        return 0
    elif length < 20:
        return 1
    elif length < 50:
        return 2
    elif length < 100:
        return 3
    elif length < 200:
        return 4
    else:
        return 5

# Gain par vocal (3 GotCoins par tranche de 30 min)
# On pourra appeler cette fonction après un timer
def compute_voice_gains(minutes_in_voice):
    # nombre de tranches complètes de 30 minutes
    num_chunks = minutes_in_voice // 30
    return num_chunks * 3

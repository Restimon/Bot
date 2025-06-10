from economy import gotcoins_balance, gotcoins_stats

# Récupérer la balance ACTUELLE (solde disponible en ce moment)
def get_gotcoins(guild_id, user_id):
    return gotcoins_balance.get(guild_id, {}).get(user_id, 0)

# Calculer l'ARGENT TOTAL GAGNÉ depuis toujours (toutes catégories)
# → c'est ça qu'on veut pour afficher en /leaderboard, /profile, etc.
def get_gotcoins_from_stats(user_stats):
    return sum(user_stats.values())

# Gain par message (GotCoins gagnés selon la longueur du message)
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
def compute_voice_gains(minutes_in_voice):
    num_chunks = minutes_in_voice // 30
    return num_chunks * 3

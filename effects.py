def remove_status_effects(guild_id, user_id):
    for status_dict in [virus_status, poison_status, infection_status]:
        if guild_id in status_dict and user_id in status_dict[guild_id]:
            del status_dict[guild_id][user_id]

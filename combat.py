import time
import math
import random
import discord

from discord import app_commands
from data import esquive_bonus, cooldowns, casque_bonus, shields, virus_status, poison_status, infection_status, immunite_status, hp, leaderboard
from utils import OBJETS, check_crit, handle_death
from storage import get_user_data
from embeds import build_embed_from_item
from cooldowns import is_on_cooldown
from leaderboard_utils import update_leaderboard
from effects import remove_status_effects

async def apply_item_with_cooldown(user_id, target_id, item, ctx):
    guild_id = str(ctx.guild.id)
    user_id = str(user_id)
    target_id = str(target_id)
    now = time.time()

    # 📦 Données utilisateurs
    user_inv, user_hp, user_stats = get_user_data(guild_id, user_id)
    _, target_hp, target_stats = get_user_data(guild_id, target_id)

    # 👤 Mentions utilisateurs
    user_mention = get_mention(ctx, user_id)
    target_mention = get_mention(ctx, target_id)

    # ❓ L’objet est-il connu ?
    if item not in OBJETS:
        return build_embed_from_item("❓", f"⚠️ L'objet `{item}` est inconnu."), False

    action = OBJETS[item]
    
    # 🕒 Vérifie le cooldown
    if action["type"] in ["attaque", "virus", "poison", "infection"]:
        on_cd, remain = is_on_cooldown(guild_id, (user_id, target_id), "attack")
        if on_cd:
            return build_embed_from_item(
                item,
                f"🕒 {user_mention}, vous devez attendre **{remain} sec** avant d'attaquer."
            ), False

    elif action["type"] == "soin":
        on_cd, remain = is_on_cooldown(guild_id, (user_id, target_id), "heal")
        if on_cd:
            return build_embed_from_item(
                item,
                f"🕒 {user_mention}, vous devez attendre **{remain} sec** avant de soigner {target_mention}."
            ), False

    # Si la cible est à 0 PV, on la remet à 100 automatiquement (fail-safe)
    if target_hp <= 0:
        hp[guild_id][target_id] = 100
        target_hp = 100


    # ⭐️ Immunité ?
    if is_immune(guild_id, target_id):
        return build_embed_from_item(
            item,
            f"⭐️ {target_mention} est **invulnérable**. Aucun effet."
        ), True

    # 💨 Esquive ?
    if action["type"] in ["attaque", "virus", "poison", "infection"]:
        if random.random() < get_evade_chance(guild_id, target_id):
            return build_embed_from_item(
                item,
                f"💨 {target_mention} esquive habilement l’attaque de {user_mention} avec {item} ! Aucun dégât."
            ), True
            
    if action["type"] == "attaque":
        base_dmg = action.get("degats", 0)
        base_dmg, crit_txt = apply_crit(base_dmg, action.get("crit", 0))
        base_dmg = apply_casque_reduction(guild_id, target_id, base_dmg)
        dmg_final = apply_shield(guild_id, target_id, base_dmg)

        before = hp[guild_id].get(target_id, 100)
        after = max(before - dmg_final, 0)
        hp[guild_id][target_id] = after

        real_dmg = before - after
        user_stats["degats"] += real_dmg

        if after == 0:
            handle_death(guild_id, target_id, user_id)
            reset_txt = f"\n💀 {target_mention} est tombé à 0 PV et revient à 100 PV."
        else:
            reset_txt = ""

        return build_embed_from_item(
            item,
            f"{user_mention} inflige {real_dmg} dégâts à {target_mention} avec {item} !\n"
            f"**{before} → {after} PV**{crit_txt}{reset_txt}"
        ), True

    elif action["type"] == "poison":
        base_dmg = action.get("degats", 3)
        base_dmg, crit_txt = apply_crit(base_dmg, action.get("crit", 0))
        base_dmg = apply_casque_reduction(guild_id, target_id, base_dmg)
        dmg_final = apply_shield(guild_id, target_id, base_dmg)

        before = hp[guild_id].get(target_id, 100)
        after = max(before - dmg_final, 0)
        hp[guild_id][target_id] = after

        real_dmg = before - after
        user_stats["degats"] += real_dmg

        # Applique le statut de poison
        poison_status.setdefault(guild_id, {})[target_id] = {
            "start": now,
            "duration": action.get("duree", 3 * 3600),  # 3 heures par défaut
            "last_tick": 0,
            "source": user_id,
            "channel_id": ctx.channel.id
        }

        if after == 0:
            handle_death(guild_id, target_id, user_id)
            reset_txt = f"\n💀 {target_mention} est tombé à 0 PV et revient à 100 PV."
        else:
            reset_txt = ""

        effect_txt = "\n🧪 Un poison s'est propagé dans son corps. 3 dégâts toutes les 30 minutes pendant 3h."

        return build_embed_from_item(
            item,
            f"{user_mention} inflige {real_dmg} dégâts à {target_mention} avec {item} !\n"
            f"**{before} → {after} PV**{crit_txt}{reset_txt}{effect_txt}"
        ), True
        
    elif action["type"] == "virus":
        base_dmg = action.get("degats", 5)
        base_dmg, crit_txt = apply_crit(base_dmg, action.get("crit", 0))
        base_dmg = apply_casque_reduction(guild_id, target_id, base_dmg)
        dmg_final = apply_shield(guild_id, target_id, base_dmg)

        before = hp[guild_id].get(target_id, 100)
        after = max(before - dmg_final, 0)
        hp[guild_id][target_id] = after

        real_dmg = before - after
        user_stats["degats"] += real_dmg

        # Applique le statut viral
        virus_status.setdefault(guild_id, {})[target_id] = {
            "start": now,
            "duration": action.get("duree", 6 * 3600),
            "last_tick": 0,
            "source": user_id,
            "channel_id": ctx.channel.id
        }

        # 💉 Auto-dégâts pour le porteur
        hp[guild_id][user_id] = max(hp[guild_id].get(user_id, 100) - 2, 0)

        # 🧠 Attribution des -2 PV au source initial (si défini)
        source_id = virus_status[guild_id].get(user_id, {}).get("source")
        if source_id:
            leaderboard.setdefault(guild_id, {})
            leaderboard[guild_id].setdefault(source_id, {"degats": 0, "soin": 0, "kills": 0, "morts": 0})
            leaderboard[guild_id][source_id]["degats"] += 2

        # ✅ Transfert automatique UNIQUEMENT si action = attaque
        if action["type"] == "attaque":
            virus_status[guild_id][target_id] = virus_status[guild_id][user_id].copy()
            del virus_status[guild_id][user_id]
            await ctx.channel.send(
                f"💉 {user_mention} a **transmis le virus** à {target_mention}.\n"
                f"🦠 Le statut viral a été **supprimé** de {user_mention}."
            )

        # 💀 KO
        if after == 0:
            handle_death(guild_id, target_id, user_id)
            reset_txt = f"\n💀 {target_mention} est tombé à 0 PV et revient à 100 PV."
        else:
            reset_txt = ""

        effect_txt = (
            "\n🦠 Le virus est en incubation. 5 dégâts toutes les heures pendant 6h."
            "\n⚔️ Lors d’une attaque : -2 PV et possible transmission."
        )

        return build_embed_from_item(
            item,
            f"{user_mention} inflige {real_dmg} dégâts à {target_mention} avec {item} !\n"
            f"**{before} → {after} PV**{crit_txt}{reset_txt}{effect_txt}"
        ), True
    
def is_immune(guild_id, target_id):
    """Vérifie si la cible a une immunité active."""
    immune = immunite_status.get(guild_id, {}).get(target_id)
    if immune:
        if time.time() - immune["start"] < immune["duration"]:
            return True
        else:
            del immunite_status[guild_id][target_id]
    return False

def get_evade_chance(guild_id, target_id):
    """Retourne la probabilité d'esquive d'un utilisateur."""
    base = 0.1
    esquive = esquive_bonus.get(guild_id, {}).get(target_id)
    if esquive:
        if time.time() - esquive["start"] < esquive["duration"]:
            base += 0.2
        else:
            del esquive_bonus[guild_id][target_id]
    return base

def apply_casque_reduction(guild_id, target_id, dmg):
    """Applique le casque si actif, sinon retourne les dégâts normaux."""
    casque = casque_bonus.get(guild_id, {}).get(target_id)
    if casque:
        if time.time() - casque["start"] < casque["duration"]:
            reduced = dmg * 0.5
            return math.ceil(reduced)
        else:
            del casque_bonus[guild_id][target_id]
    return dmg

def apply_shield(guild_id, target_id, dmg):
    """Applique le bouclier et retourne le reste des dégâts (0 si tout absorbé)."""
    shield = shields.get(guild_id, {}).get(target_id, 0)
    if shield > 0:
        if dmg <= shield:
            shields[guild_id][target_id] -= dmg
            return 0
        else:
            shields[guild_id][target_id] = 0
            return dmg - shield
    return dmg

def apply_crit(dmg, crit_chance):
    """Applique un coup critique si applicable."""
    if check_crit(crit_chance):
        return dmg * 2, " **(Coup critique ! 💥)**"
    return dmg, ""

def get_mention(ctx, user_id):
    member = ctx.guild.get_member(int(user_id))
    return member.mention if member else f"<@{user_id}>"

    

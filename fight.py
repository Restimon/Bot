# fight.py
import discord
from discord import app_commands
from discord.ext import commands

from storage import get_user_data
from utils import OBJETS
from combat import apply_item_with_cooldown

# ✅ Enregistre la commande uniquement sur TON serveur (publication instantanée)
#    Remplace si besoin par l'ID de ton serveur.
DEV_GUILD_ID = 1269384239254605856

TYPES_VALIDES_ATTAQUE = {"attaque", "attaque_chaine", "virus", "poison", "infection"}


def _to_emoji(it):
    """Normalise un élément d'inventaire vers un emoji (string)."""
    if isinstance(it, str):
        return it
    if isinstance(it, dict):
        return it.get("emoji") or it.get("emote") or it.get("e")
    return None


def _attack_items_from_inventory(user_inv):
    """Retourne la liste triée (sans doublons) des emojis d'attaque présents dans l'inventaire."""
    emojis = []
    for it in user_inv:
        e = _to_emoji(it)
        if not e:
            continue
        if OBJETS.get(e, {}).get("type") in TYPES_VALIDES_ATTAQUE:
            emojis.append(e)
    return sorted(set(emojis))


class Fight(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        print("[Fight] Cog chargé")

    # --- Commande principale /fight ---
    @app_commands.guilds(discord.Object(id=DEV_GUILD_ID))  # ➜ publication immédiate sur ce serveur
    @app_commands.command(
        name="fight",
        description="Attaque un joueur avec un objet de ton inventaire."
    )
    @app_commands.describe(
        cible="Le joueur que tu veux attaquer",
        item="L’objet d’attaque à utiliser (emoji de l’objet)"
    )
    async def fight_slash(self, interaction: discord.Interaction, cible: discord.Member, item: str):
        print(f"[Fight] /fight appelé par={interaction.user.id} cible={getattr(cible, 'id', None)} item={item!r}")
        await interaction.response.defer(thinking=True)

        # --- Garde-fous rapides ---
        if cible.bot:
            await interaction.followup.send("🤖 Tu ne peux pas attaquer un bot.", ephemeral=True)
            return
        if cible.id == interaction.user.id:
            await interaction.followup.send("🙅 Tu ne peux pas t’attaquer toi-même.", ephemeral=True)
            return
        if item == "❌":
            await interaction.followup.send("❌ Tu n’as sélectionné aucun objet d’attaque valide.", ephemeral=True)
            return

        guild_id = str(interaction.guild.id)
        attacker_id = str(interaction.user.id)

        # --- Validation côté inventaire ---
        user_inv, _, _ = get_user_data(guild_id, attacker_id)
        attack_items = _attack_items_from_inventory(user_inv)
        print(f"[Fight] Inventaire attaques dispo={attack_items}")

        if not attack_items:
            await interaction.followup.send(
                "🧺 Ton inventaire ne contient **aucun objet d’attaque** sur ce serveur.\n"
                "Utilise d’abord des commandes pour en obtenir (tirage, shop, etc.).",
                ephemeral=True
            )
            return

        if item not in attack_items:
            obj = OBJETS.get(item)
            if not obj:
                await interaction.followup.send(
                    f"❓ L’objet `{item}` est inconnu. Choisis un objet de ton autocomplete ou un emoji d’objet valide.",
                    ephemeral=True
                )
                return
            if obj.get("type") not in TYPES_VALIDES_ATTAQUE:
                await interaction.followup.send(
                    f"🧪 `{item}` n’est pas un objet d’attaque utilisable pour /fight.",
                    ephemeral=True
                )
                return
            await interaction.followup.send(
                f"🚫 Tu ne possèdes pas `{item}` dans **ton inventaire** sur ce serveur.",
                ephemeral=True
            )
            return

        # --- Application de l’objet (logique déléguée) ---
        try:
            result_embed = await apply_item_with_cooldown(
                interaction=interaction,
                guild_id=guild_id,
                attacker_id=attacker_id,
                target_id=cible.id,
                item_emoji=item
            )
        except TypeError:
            # compat si ta signature originelle est (interaction, guild_id, attacker_id, target_id, item)
            result_embed = await apply_item_with_cooldown(
                interaction,
                guild_id,
                attacker_id,
                cible.id,
                item
            )
        except Exception as e:
            print(f"[Fight] ERREUR apply_item_with_cooldown: {e}")
            await interaction.followup.send(
                f"⚠️ Une erreur est survenue pendant l’attaque : `{e}`",
                ephemeral=True
            )
            return

        # --- Réponse ---
        if isinstance(result_embed, discord.Embed):
            await interaction.followup.send(embed=result_embed)
        else:
            await interaction.followup.send(result_embed if result_embed else "✅ Action effectuée.")

    # --- Autocomplete pour l’argument "item" ---
    @fight_slash.autocomplete("item")
    async def autocomplete_items(self, interaction: discord.Interaction, current: str):
        guild_id = str(interaction.guild.id)
        uid = str(interaction.user.id)
        user_inv, _, _ = get_user_data(guild_id, uid)

        attack_items = _attack_items_from_inventory(user_inv)

        cur = (current or "").strip()
        if cur:
            attack_items = [e for e in attack_items if cur in e]

        if not attack_items:
            return [app_commands.Choice(name="❌ Aucune arme disponible dans ton inventaire", value="❌")]

        suggestions = []
        for emoji in attack_items:
            obj = OBJETS.get(emoji, {}) or {}
            typ = obj.get("type")

            if typ == "attaque":
                label = f"{emoji} | {obj.get('degats', '?')} dmg, {int(obj.get('crit', 0)*100)}% crit"
            elif typ == "attaque_chaine":
                label = f"{emoji} | ☠️ 24 dmg + 2×12, {int(obj.get('crit', 0)*100)}% crit"
            elif typ == "virus":
                label = f"{emoji} | Virus → 5 dmg initiaux + 5 dmg/h"
            elif typ == "poison":
                label = f"{emoji} | Poison → 3 dmg initiaux + 3 dmg/30min"
            elif typ == "infection":
                label = f"{emoji} | Infection → 5 dmg initiaux + 2 dmg/30min, propagation"
            else:
                label = f"{emoji} (Objet spécial)"

            suggestions.append(app_commands.Choice(name=label, value=emoji))

        return suggestions[:25]


async def setup(bot):
    await bot.add_cog(Fight(bot))
    print("[Fight] setup() terminé, commande enregistrée (guild-scoped)")

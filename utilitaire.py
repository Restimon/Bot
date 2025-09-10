# utilitaire.py
import discord
import random
import time
from discord import app_commands

from utils import OBJETS, get_mention
from storage import get_user_data
from data import sauvegarder, shields, immunite_status, esquive_status, casque_status
from embeds import build_embed_from_item
from passifs import appliquer_passif


def register_utilitaire_command(bot):
    @bot.tree.command(
        name="utilitaire",
        description="Utilise un objet utilitaire ou de protection"
    )
    @app_commands.describe(
        target="Cible (si applicable, ex: pour le vol)",
        item="Objet utilitaire à utiliser (emoji)"
    )
    async def utilitaire_slash(
        interaction: discord.Interaction,
        target: discord.Member | None = None,
        item: str = ""
    ):
        await interaction.response.defer(thinking=True)

        guild_id = str(interaction.guild.id)
        uid = str(interaction.user.id)
        tid = str(target.id) if target else uid  # si pas de cible fournie → auto-ciblage
        action = OBJETS.get(item)

        # Garde-fous de base
        if not isinstance(action, dict):
            await interaction.followup.send("❌ Objet inconnu ou non autorisé.", ephemeral=True)
            return

        allowed_types = {"vol", "bouclier", "esquive+", "reduction", "immunite"}
        if action.get("type") not in allowed_types:
            await interaction.followup.send("⚠️ Cet objet n’est pas utilisable via `/utilitaire`.", ephemeral=True)
            return

        # Inventaire de l’utilisateur
        user_inv, _, _ = get_user_data(guild_id, uid)
        if item not in user_inv:
            await interaction.followup.send("❌ Tu n’as pas cet objet dans ton inventaire.", ephemeral=True)
            return

        # Si c’est un vol, cible obligatoire + la cible ne doit pas être un bot
        if action["type"] == "vol":
            if not target:
                await interaction.followup.send("❌ Tu dois cibler quelqu’un pour utiliser un objet de type **vol**.", ephemeral=True)
                return
            if target.bot:
                await interaction.followup.send("🤖 Impossible de voler un bot.", ephemeral=True)
                return

        embed = None
        success = False

        # =========================
        # 🛡 Bouclier
        # =========================
        if action["type"] == "bouclier":
            valeur = int(action.get("valeur", 20))
            current_pb = shields.get(guild_id, {}).get(tid, 0)

            # Passif : max PB (ex: bonus de limite)
            res_max = appliquer_passif(tid, "max_pb", {"guild_id": guild_id}) or {}
            max_pb = int(res_max.get("max_pb", 20))
            bonus_txt = " ✨" if max_pb > 20 else ""

            if current_pb >= max_pb:
                await interaction.followup.send(
                    f"❌ {get_mention(interaction.guild, tid)} possède déjà le maximum de **{max_pb} PB**{bonus_txt}.",
                    ephemeral=True
                )
                return

            new_pb = min(current_pb + valeur, max_pb)
            shields.setdefault(guild_id, {})[tid] = new_pb

            # PV actuel de la cible (2e valeur de get_user_data)
            _, pv_actuels, _ = get_user_data(guild_id, tid)

            if uid == tid:
                desc = (
                    f"{interaction.user.mention} a activé un **bouclier** de protection !\n"
                    f"🛡 Total **{new_pb} PB** → ❤️ {pv_actuels} PV / 🛡 {new_pb} PB{bonus_txt}"
                )
            else:
                mention_cible = get_mention(interaction.guild, tid)
                desc = (
                    f"{interaction.user.mention} accorde un **bouclier** à {mention_cible} !\n"
                    f"🛡 Total **{new_pb} PB** → ❤️ {pv_actuels} PV / 🛡 {new_pb} PB{bonus_txt}"
                )

            embed = build_embed_from_item(item, desc)
            success = True

        # =========================
        # ⭐ Immunité
        # =========================
        elif action["type"] == "immunite":
            duree = int(action.get("duree", 2 * 3600))
            immunite_status.setdefault(guild_id, {})[tid] = time.time() + duree

            mention_cible = interaction.user.mention if uid == tid else get_mention(interaction.guild, tid)
            desc = f"{mention_cible} bénéficie désormais d’une **immunité totale** pendant {duree // 3600}h."
            embed = build_embed_from_item(item, desc)
            success = True

        # =========================
        # 👟 Esquive+
        # =========================
        elif action["type"] == "esquive+":
            duree = int(action.get("duree", 3 * 3600))
            valeur = float(action.get("valeur", 0.2))
            esquive_status.setdefault(guild_id, {})[tid] = {
                "start": time.time(),
                "duration": duree,
                "valeur": valeur,
            }

            mention_cible = interaction.user.mention if uid == tid else get_mention(interaction.guild, tid)
            desc = f"{mention_cible} bénéficie désormais d’une **augmentation d’esquive** (+{int(valeur*100)}%) pendant {duree // 3600}h."
            embed = build_embed_from_item(item, desc)
            success = True

        # =========================
        # 🪖 Réduction (Casque)
        # =========================
        elif action["type"] == "reduction":
            duree = int(action.get("duree", 4 * 3600))
            casque_status.setdefault(guild_id, {})[tid] = time.time() + duree

            mention_cible = interaction.user.mention if uid == tid else get_mention(interaction.guild, tid)
            desc = f"{mention_cible} bénéficie désormais d’une **réduction des dégâts** pendant {duree // 3600}h."
            embed = build_embed_from_item(item, desc)
            success = True

        # =========================
        # 🔍 Vol d’objet (avec passifs)
        # =========================
        elif action["type"] == "vol":
            embed, success = await _voler_objet_robuste(interaction, uid, tid, item)

        # Retirer l'objet s'il a été utilisé avec succès
        if success:
            try:
                user_inv.remove(item)
                sauvegarder()
            except Exception:
                pass

        if embed:
            # Public pour que tout le monde voie l’action utilitaire
            await interaction.followup.send(embed=embed, ephemeral=False)

    # ---------------- Autocomplétion ----------------
    @utilitaire_slash.autocomplete("item")
    async def autocomplete_items(interaction: discord.Interaction, current: str):
        guild_id = str(interaction.guild.id)
        uid = str(interaction.user.id)
        user_inv, _, _ = get_user_data(guild_id, uid)

        allowed_types = {"vol", "bouclier", "esquive+", "reduction", "immunite"}
        utilitaire_items = sorted({
            i for i in user_inv
            if isinstance(i, str) and OBJETS.get(i, {}).get("type") in allowed_types
        })

        if not utilitaire_items:
            return [app_commands.Choice(name="Aucun objet utilitaire disponible", value="")]

        cur = (current or "").strip()
        suggestions = []
        for emoji in utilitaire_items:
            if cur and cur not in emoji:
                continue

            obj = OBJETS.get(emoji, {})
            typ = obj.get("type")

            if typ == "vol":
                label = f"{emoji} | Vole un objet à la cible"
            elif typ == "bouclier":
                label = f"{emoji} | +{obj.get('valeur', 20)} Points de Bouclier"
            elif typ == "esquive+":
                label = f"{emoji} | Esquive +{int(obj.get('valeur', 0.2)*100)}% pendant {int(obj.get('duree', 10800)//3600)}h"
            elif typ == "reduction":
                label = f"{emoji} | Réduction dégâts x0.5 pendant {int(obj.get('duree', 14400)//3600)}h"
            elif typ == "immunite":
                label = f"{emoji} | Immunité totale pendant {int(obj.get('duree', 7200)//3600)}h"
            else:
                label = f"{emoji} (Objet spécial)"

            suggestions.append(app_commands.Choice(name=label, value=emoji))

        return suggestions[:25]


# =========
# Vol “smart” avec passifs & garde-fous
# =========
async def _voler_objet_robuste(interaction: discord.Interaction, uid: str, tid: str, item_emoji: str):
    guild_id = str(interaction.guild.id)

    # 1) Protection anti-vol (passif cible)
    prot = appliquer_passif("protection_vol", {
        "guild_id": guild_id,
        "user_id": tid,          # cible
        "item": item_emoji,
        "attacker_id": uid,      # voleur
    }) or {}

    if prot.get("immunise_contre_vol"):
        desc = f"🛡️ {get_mention(interaction.guild, tid)} est **protégé contre le vol** !"
        return build_embed_from_item(item_emoji, desc), True  # True = on considère l’objet consommé

    # 2) Récup inventaires
    target_inv, _, _ = get_user_data(guild_id, tid)
    voleur_inv, _, _ = get_user_data(guild_id, uid)

    # On vole uniquement des **strings** (évite de voler des dicts/personnages)
    candidats = [x for x in target_inv if isinstance(x, str)]

    if not candidats:
        # Passif voleur : conserve l’objet même si vol impossible ?
        utl = appliquer_passif("utilitaire_vol", {
            "guild_id": guild_id,
            "user_id": uid,
            "item": item_emoji,
            "target_id": tid
        }) or {}

        if not utl.get("conserver_objet_vol", False):
            # On consomme l’objet utilisé
            if item_emoji in voleur_inv:
                voleur_inv.remove(item_emoji)
                sauvegarder()

        desc = f"🔍 {get_mention(interaction.guild, tid)} n’a aucun objet à voler."
        return build_embed_from_item(item_emoji, desc), True

    # 3) Vol effectif (1 ou 2 objets selon passif)
    stolen = []
    premier = random.choice(candidats)
    target_inv.remove(premier)
    stolen.append(premier)

    utl = appliquer_passif("utilitaire_vol", {
        "guild_id": guild_id,
        "user_id": uid,
        "item": item_emoji,
        "target_id": tid
    }) or {}

    if utl.get("double_vol", False):
        candidats2 = [x for x in target_inv if isinstance(x, str)]
        if candidats2:
            second = random.choice(candidats2)
            target_inv.remove(second)
            stolen.append(second)

    # Conserver ou non l’objet utilisé
    if not utl.get("conserver_objet_vol", False):
        if item_emoji in voleur_inv:
            voleur_inv.remove(item_emoji)

    # Ajouter les objets volés à l’inventaire du voleur
    voleur_inv.extend(stolen)
    sauvegarder()

    objets_txt = " et ".join([f"**{s}**" for s in stolen])
    desc = f"{interaction.user.mention} a volé {objets_txt} à {get_mention(interaction.guild, tid)} !"
    emb = build_embed_from_item("🔍", desc)
    emb.color = discord.Color.green()
    return emb, True

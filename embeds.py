# embeds.py
import discord
from typing import Optional, Dict, Any

# Palette de couleurs (douce et lisible)
COLOR_ATTACK      = discord.Color.red()
COLOR_HEAL        = discord.Color.green()
COLOR_UTILITY     = discord.Color.blurple()
COLOR_STATUS      = discord.Color.orange()
COLOR_INFO        = discord.Color.purple()
COLOR_SUCCESS     = discord.Color.teal()
COLOR_WARNING     = discord.Color.gold()
COLOR_DARK        = discord.Color.dark_grey()

# -----------------------------
# Helpers d’affichage communs
# -----------------------------
def _title_for_item(item: Optional[str], custom_title: Optional[str] = None) -> str:
    if custom_title:
        return custom_title

    # Titre par défaut selon l’emoji
    mapping = {
        "❄️": "Boule de neige",
        "🪓": "Coup de hache",
        "🔥": "Boule de feu",
        "⚡": "Décharge",
        "🔫": "Tir",
        "🧨": "Explosif",
        "☠️": "Attaque en chaîne",
        "🦠": "Virus",
        "🧪": "Poison",
        "🧟": "Infection",
        "🍀": "Petit soin",
        "🩸": "Soin",
        "🩹": "Grand soin",
        "💊": "Pilule",
        "💕": "Régénération",
        "📦": "Boîte surprise",
        "🔍": "Vol d’objet",
        "💉": "Vaccination",
        "🛡": "Bouclier",
        "👟": "Esquive+",
        "🪖": "Casque",
        "⭐️": "Immunité",
        "🎟️": "Ticket de tirage",
        "💨": "Esquive",
    }
    if item in mapping:
        return mapping[item]
    return "Action GotValis"

def _color_for_item(item: Optional[str], is_heal_other: bool = False, is_crit: bool = False) -> discord.Color:
    if item in {"🍀", "🩸", "🩹", "💊", "💕"}:
        return COLOR_HEAL
    if item in {"🦠", "🧪", "🧟"}:
        return COLOR_STATUS
    if item in {"🔍", "🛡", "👟", "🪖", "⭐️", "📦", "🎟️"}:
        return COLOR_UTILITY
    if item == "☠️":
        return COLOR_WARNING
    if item == "💨":
        return COLOR_SUCCESS
    # Attaques par défaut
    return COLOR_ATTACK if not is_heal_other else COLOR_HEAL


# ------------------------------------------------
# 1) Embed générique orienté « objet » (combat/soin)
# ------------------------------------------------
def build_embed_from_item(
    item: Optional[str],
    description: str,
    *,
    is_heal_other: bool = False,
    is_crit: bool = False,
    disable_gif: bool = False,
    custom_title: Optional[str] = None,
    extra_fields: Optional[Dict[str, str]] = None,
) -> discord.Embed:
    """
    Construit un embed uniforme pour les actions du bot liées à un item (attaque, soin, statut, utilitaire).
    - item: emoji (peut être None pour un fallback)
    - description: texte principal
    - is_heal_other: formatage « soin »
    - is_crit: met un petit accent si critique
    - disable_gif: pas d’image/gif additionnel (combat.py gère déjà ses images)
    - custom_title: force un titre particulier
    - extra_fields: dict {name: value} pour ajouter des champs
    """
    title = _title_for_item(item, custom_title)
    color = _color_for_item(item, is_heal_other, is_crit)

    embed = discord.Embed(title=title, description=description, color=color)

    # Accent critique subtil
    if is_crit:
        embed.set_footer(text="💥 Coup critique !")

    # Ajout de champs optionnels
    if isinstance(extra_fields, dict):
        for name, value in extra_fields.items():
            embed.add_field(name=name, value=value, inline=False)

    # Optionnellement, on pourrait définir une image par défaut sur certains items
    # mais par défaut on laisse l’appelant gérer (combat.py force parfois set_image(None))
    if disable_gif:
        # explicitement rien
        pass

    return embed


# ---------------------------------------------------------
# 2) Embed spécialisé : transmission virale (🦠 → 🧬)
# ---------------------------------------------------------
def build_embed_transmission_virale(
    *,
    from_user_mention: str,
    to_user_mention: str,
    pv_avant: int,
    pv_apres: int
) -> discord.Embed:
    """
    Embed standardisé pour la transmission du virus (auto-dégâts de transfert).
    """
    desc = (
        f"🦠 **Transmission virale détectée**\n"
        f"{from_user_mention} transmet le virus à {to_user_mention}.\n"
        f"• {from_user_mention} subit **{pv_avant - pv_apres} PV** de transfert.\n"
        f"• ❤️ {pv_avant} → ❤️ {pv_apres}"
    )
    return discord.Embed(
        title="🦠 Contamination",
        description=desc,
        color=COLOR_STATUS
    )


# ---------------------------------------------------------
# 3) Embed « fiche personnage » (perso / tirage)
# ---------------------------------------------------------
def build_personnage_embed(perso: Dict[str, Any], user: Optional[discord.Member] = None) -> discord.Embed:
    """
    Embed pour l’affichage d’une carte personnage (tirage, /perso).
    Attend la structure de personnage.py :
      - nom, rarete, faction, description, passif: {nom, effet}, image (optionnel)
    L’image locale (si présente) est gérée par l’appelant (perso.py, tirage.py) via discord.File.
    """
    nom = perso.get("nom", "Personnage")
    rarete = perso.get("rarete", "Inconnu")
    faction = perso.get("faction", "—")
    description = perso.get("description", "")
    passif = perso.get("passif", {}) or {}
    passif_nom = passif.get("nom", "Passif")
    passif_effet = passif.get("effet", "")

    # Couleur indicative par rareté
    color_by_rarity = {
        "Commun": discord.Color.light_grey(),
        "Rare": discord.Color.blurple(),
        "Épique": discord.Color.purple(),
        "Epique": discord.Color.purple(),       # tolérance orthographe
        "Légendaire": discord.Color.gold(),
        "Legendaire": discord.Color.gold(),     # tolérance orthographe
    }
    color = color_by_rarity.get(rarete, COLOR_INFO)

    title = f"🎭 {nom}"
    if user:
        title += f" — {user.display_name}"

    embed = discord.Embed(title=title, color=color, description=description or "—")
    embed.add_field(name="⭐ Rareté", value=rarete, inline=True)
    embed.add_field(name="🎖 Faction", value=faction, inline=True)
    embed.add_field(name="🎁 Passif", value=f"**{passif_nom}**\n> {passif_effet}", inline=False)

    return embed

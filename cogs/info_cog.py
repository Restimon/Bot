# cogs/info_cog.py
from __future__ import annotations

import time
import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional, List, Tuple

# Stats & Economy
from stats_db import get_hp, get_shield
try:
    from economie import get_balance, get_total_earned  # si défini chez toi
except Exception:
    # fallback pour éviter de crasher si get_total_earned n'existe pas
    from economie import get_balance  # type: ignore
    async def get_total_earned(user_id: int) -> int:  # pragma: no cover
        return 0

# Inventaire & tickets (🎟️)
from inventory import get_all_items, get_item_qty
# Perso équipé
from passifs import get_equipped_name
from personnage import PERSONNAGES
# Effets
from effects_db import list_effects

# Emojis d'effets considérés comme "négatifs" pour l'encart pathologique
NEGATIVE_EFFECTS = {"poison", "virus", "infection", "brulure"}

# Mois FR pour un rendu propre sans locale système
_MONTHS_FR = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]
_MONTHS_FR_MAP = {
    "January": "Janvier", "February": "Février", "March": "Mars",
    "April": "Avril", "May": "Mai", "June": "Juin",
    "July": "Juillet", "August": "Août", "September": "Septembre",
    "October": "Octobre", "November": "Novembre", "December": "Décembre",
}

def _format_join_date(m: discord.Member) -> str:
    dt = m.joined_at or m.created_at  # fallback: date de création du compte
    # ex: "05 January 2025 à 13h06" -> remplace le mois en FR
    base = dt.strftime("%d %B %Y à %Hh%M")
    for en, fr in _MONTHS_FR_MAP.items():
        if en in base:
            return base.replace(en, fr)
    return base

def _format_inventory_lines(items: List[Tuple[str, int]]) -> List[str]:
    """
    items: list[(emoji, qty)]
    On filtre les items qty>0, on garde un rendu simple "🧪 ×2".
    On exclut le ticket 🎟️ de cette liste (affiché en haut).
    """
    lines = []
    for emoji, qty in items:
        if qty <= 0 or emoji == "🎟️":
            continue
        lines.append(f"{emoji} ×{qty}")
    # pour un rendu stable
    lines.sort()
    return lines[:24]  # éviter des embeds trop longs

async def _compute_rank_in_guild(guild: discord.Guild, user_id: int) -> Optional[int]:
    """
    Classement par solde sur ce serveur (1 = meilleur).
    On récupère le balance pour tous les membres (non-bots).
    Attention: O(n). Ok pour des serveurs ~petits à moyens.
    """
    balances: List[Tuple[int, int]] = []
    for m in guild.members:
        if m.bot:
            continue
        try:
            bal = await get_balance(m.id)
        except Exception:
            bal = 0
        balances.append((m.id, bal))

    if not balances:
        return None
    # tri desc; si égalité, par id croissant (stable)
    balances.sort(key=lambda t: (-t[1], t[0]))
    for idx, (uid, _bal) in enumerate(balances, start=1):
        if uid == user_id:
            return idx
    return None

def _effect_label_fr(eff_type: str) -> str:
    return {
        "poison": "🧪 Poison",
        "virus": "🦠 Virus",
        "infection": "🧟 Infection",
        "brulure": "🔥 Brûlure",
        "regen": "💕 Régénération",
        "reduction": "🛡 Réduction",
        "reduction_temp": "🪖 Réduction (temp.)",
        "reduction_valen": "🧠 Réduction (Valen)",
        "esquive": "👟 Esquive+",
        "immunite": "⭐ Immunité",
    }.get(eff_type, eff_type)

class InfoCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="info", description="Affiche le profil GotValis d'un membre (inventaire, PV/PB, effets, tickets...).")
    @app_commands.describe(membre="Optionnel: le membre ciblé (par défaut: toi).")
    async def info(self, interaction: discord.Interaction, membre: Optional[discord.Member] = None):
        await interaction.response.defer()
        target: discord.Member = membre or interaction.user  # type: ignore
        if target.bot:
            await interaction.followup.send("❌ Les bots n'ont pas de profil.", ephemeral=True)
            return

        # PV / PB
        hp, hp_max = await get_hp(target.id)
        pb = await get_shield(target.id)

        # Economy
        balance = await get_balance(target.id)
        total = 0
        try:
            total = await get_total_earned(target.id)
        except Exception:
            total = 0

        # Classement
        rank_text = "—"
        if interaction.guild:
            r = await _compute_rank_in_guild(interaction.guild, target.id)
            if r is not None:
                rank_text = f"Rang {r}"

        # Tickets
        tickets = await get_item_qty(target.id, "🎟️")

        # Perso équipé
        equipped_name = await get_equipped_name(target.id)
        equipped_line = "Aucun"
        thumb_url = None
        if equipped_name:
            p = PERSONNAGES.get(equipped_name)
            if p:
                equipped_line = f"**{p['nom']}** — *{p.get('passif',{}).get('nom','')}*"
                # On peut afficher la vignette si tu as un CDN/URL ; sinon laisse None
                # thumb_url = p.get("image_url")  # à adapter si tu as un hébergement
            else:
                equipped_line = equipped_name

        # Inventaire (hors tickets)
        items = await get_all_items(target.id)
        inv_lines = _format_inventory_lines(items)
        if not inv_lines:
            inv_lines = ["*(vide)*"]

        # Effets actifs
        rows = await list_effects(target.id)
        neg_lines: List[str] = []
        if rows:
            now = int(time.time())
            for eff_type, value, interval, next_ts, end_ts, source_id, meta_json in rows:
                if eff_type not in NEGATIVE_EFFECTS:
                    continue
                remain = max(0, end_ts - now)
                mins = remain // 60
                label = _effect_label_fr(eff_type)
                if interval > 0 and next_ts > 0:
                    neg_lines.append(f"{label} — {mins} min restants")
                else:
                    neg_lines.append(f"{label} — {mins} min restants")
        if not neg_lines:
            neg_lines = ["✅ Aucun effet négatif détecté."]

        # ---------- Embed ----------
        emb = discord.Embed(
            title=f"🧩 Profil GotValis de {target.display_name}",
            description="Analyse médicale et opérationnelle en cours...",
            color=discord.Color.blurple()
        )
        if thumb_url:
            emb.set_thumbnail(url=thumb_url)

        emb.add_field(name="❤️ Points de vie", value=f"{hp} / {hp_max}", inline=False)
        emb.add_field(name="🛡 Bouclier", value=f"{pb} PB", inline=False)
        emb.add_field(name="🎴 Personnage équipé", value=equipped_line, inline=False)

        emb.add_field(name="💰 GotCoins totaux (carrière)", value=str(total), inline=False)
        emb.add_field(name="💵 Solde actuel (dépensable)", value=f"{balance} GotCoins", inline=False)

        emb.add_field(name="🏆 Classement général", value=rank_text, inline=False)
        emb.add_field(name="🧾 Membre depuis", value=_format_join_date(target), inline=False)

        emb.add_field(name="🎟️ Tickets de tirage", value=("aucun" if tickets <= 0 else str(tickets)), inline=False)

        emb.add_field(name="🎒 Inventaire", value="\n".join(inv_lines), inline=False)

        emb.add_field(name="🩺 État pathologique", value="\n".join(neg_lines), inline=False)

        await interaction.followup.send(embed=emb)


async def setup(bot: commands.Bot):
    await bot.add_cog(InfoCog(bot))

# cogs/help_cog.py
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional, Dict, List

# Si certaines commandes ne sont pas (encore) chargées chez toi,
# tu peux masquer ici en retirant les lignes concernées.
USER_COMMANDS: Dict[str, Dict[str, str]] = {
    # Profil & infos
    "info": {
        "usage": "/info [membre]",
        "desc": "Affiche ton dossier médical & opérationnel GotValis : PV/PB, solde, tickets, perso équipé, inventaire, effets négatifs.",
        "cat": "Profil & Dossiers",
    },
    "inv": {
        "usage": "/inv [membre]",
        "desc": "Inventaire condensé : objets avec quantités, tickets, solde. Idéal avant un affrontement.",
        "cat": "Profil & Dossiers",
    },

    # Économie (côté joueur)
    "daily": {
        "usage": "/daily",
        "desc": "Réclamation journalière: 1 🎟️ ticket + 1 à 3 objets aléatoires (quantités variables) + 10–100 GotCoins.",
        "cat": "Crédits & Réquisitions",
    },
    "tickets": {
        "usage": "/tickets [membre]",
        "desc": "Affiche ton stock de 🎟️ utilisables pour les tirages du Gacha.",
        "cat": "Crédits & Réquisitions",
    },

    # Gacha
    "tirage": {
        "usage": "/tirage",
        "desc": "Consomme 1 🎟️ pour invoquer un personnage (Commun → Légendaire).",
        "cat": "Gacha",
    },

    # Combat
    "fight": {
        "usage": "/fight cible:<@membre> objet:<emoji>",
        "desc": "Attaque directe/DOT selon l’objet (⚡, 🔫, 🧪, 🦠, 🧟, 🔥...). CD 5s. Règles: réduction→PB→PV, esquive annule le coup (pas les DOT).",
        "cat": "Opérations — Combat",
    },
    "heal": {
        "usage": "/heal cible:<@membre> objet:<emoji>",
        "desc": "Soigne ou applique une régénération (💕). Les soins ne dépassent pas le PV max; certains passifs interagissent avec les soins.",
        "cat": "Opérations — Combat",
    },
    "use": {
        "usage": "/use objet:<emoji> [cible]",
        "desc": "Utilitaires: 🛡 bouclier, ⭐ immunité, 👟 esquive+, 🧪 vaccin, 🔍 vol, 📦 mysterybox… (1 action à la fois).",
        "cat": "Opérations — Combat",
    },

    # Divers visibles
    "status": {
        "usage": "/status [membre]",
        "desc": "État des effets actifs (poison, virus, infection, brûlure, régén, immunité…).",
        "cat": "Diagnostics",
    },
}

CATEGORIES_ORDER = [
    "Profil & Dossiers",
    "Crédits & Réquisitions",
    "Gacha",
    "Opérations — Combat",
    "Diagnostics",
]

def _group_by_category() -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {c: [] for c in CATEGORIES_ORDER}
    for cmd, meta in USER_COMMANDS.items():
        out.setdefault(meta["cat"], []).append(cmd)
    for k in out:
        out[k].sort()
    return out

def _rp_intro() -> str:
    return (
        "Connexion au **réseau GotValis** établie.\n"
        "Les modules ci-dessous sont autorisés pour les opérateurs civils.\n"
        "⚠️ Les protocoles d’administration ne sont **pas** affichés ici."
    )

def _cmd_detail_embed(name: str) -> discord.Embed:
    meta = USER_COMMANDS[name]
    emb = discord.Embed(
        title=f"📘 Protocole « {name} »",
        color=discord.Color.blurple(),
        description=(
            f"**Usage** : `{meta['usage']}`\n"
            f"**Module** : {meta['cat']}\n\n"
            f"{meta['desc']}\n"
        ),
    )
    emb.set_footer(text="GotValis • Aide contextuelle")
    return emb

def _all_cmds_embed(guild: Optional[discord.Guild]) -> discord.Embed:
    emb = discord.Embed(
        title="🛰️ Manuel d’Opérateur — Aide GotValis",
        description=_rp_intro(),
        color=discord.Color.dark_teal(),
    )
    grouped = _group_by_category()
    for cat in CATEGORIES_ORDER:
        cmds = grouped.get(cat) or []
        if not cmds:
            continue
        lines = []
        for c in cmds:
            meta = USER_COMMANDS[c]
            lines.append(f"• `/{c}` — {meta['desc']}")
        emb.add_field(name=f"__{cat}__", value="\n".join(lines), inline=False)

    emb.add_field(
        name="ℹ️ Rappels de terrain",
        value=(
            "• **Combat** : réduction ➜ bouclier ➜ PV. DOT : pas de réduction, pas d’esquive, crit 5% par tick.\n"
            "• **KO** : la cible remonte à 100 PV et tous ses statuts sont purgés.\n"
            "• **Économie** : 1 dégât = 1 coin | 1 soin = 1 coin | 1 kill = +50 | 1 mort = −25 (jamais négatif).\n"
            "• **Daily** : 1 🎟️/jour (non cumulable) + loot + GotCoins.\n"
        ),
        inline=False,
    )
    if guild:
        emb.set_footer(text=f"GotValis • {guild.name}")
    else:
        emb.set_footer(text="GotValis")
    return emb

def _choices_all() -> List[app_commands.Choice[str]]:
    return [app_commands.Choice(name=f"/{n}", value=n) for n in sorted(USER_COMMANDS.keys())][:25]

class HelpCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="help", description="Affiche l’aide GotValis (RP) ou le détail d’une commande.")
    @app_commands.describe(
        commande="Nom d'une commande (ex: info, fight, tirage...).",
        public="Si vrai, affiche l'aide publiquement (par défaut: privé/éphémère).",
    )
    @app_commands.autocomplete(commande=lambda i, c: _choices_all())
    async def help_cmd(self, interaction: discord.Interaction, commande: Optional[str] = None, public: Optional[bool] = False):
        ephemeral = not public
        if commande:
            name = commande.strip().lower()
            if name not in USER_COMMANDS:
                await interaction.response.send_message("❌ Commande inconnue (ou réservée à l'administration).", ephemeral=True)
                return
            emb = _cmd_detail_embed(name)
            await interaction.response.send_message(embed=emb, ephemeral=ephemeral)
            return

        emb = _all_cmds_embed(interaction.guild)
        await interaction.response.send_message(embed=emb, ephemeral=ephemeral)

async def setup(bot: commands.Bot):
    await bot.add_cog(HelpCog(bot))

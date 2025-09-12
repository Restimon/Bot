# cogs/inventory_cog.py
import discord
from discord import app_commands, Interaction, Embed, Colour
from discord.ext import commands

from inventory import get_all_items, init_inventory_db
from gacha_db import get_tickets, can_claim_daily_ticket
from economy_db import get_balance
from data.items import OBJETS  # ton dictionnaire des objets

# ------------------------------------------------------------------
# Utilitaires
# ------------------------------------------------------------------

def _fmt_cd(secs: int) -> str:
    """Formate un cooldown en h/m/s lisible."""
    h = secs // 3600
    m = (secs % 3600) // 60
    s = secs % 60
    parts = []
    if h: parts.append(f"{h}h")
    if m: parts.append(f"{m}m")
    if s or not parts: parts.append(f"{s}s")
    return " ".join(parts)

def _fmt_item_line(emoji: str, qty: int) -> str:
    """Construit une ligne 'emoji ×qty — description'."""
    d = OBJETS.get(emoji, {})
    t = d.get("type")

    def hours(sec: int) -> int:
        return int(sec // 3600)

    def mins(sec: int) -> int:
        return int(sec // 60)

    if t == "attaque":
        crit = f" 🎯 {int(d.get('crit', 0)*100)}% crit" if d.get("crit") else ""
        return f"{emoji} ×{qty} — {d.get('degats', 0)} dégâts{crit}"
    if t == "attaque_chaine":
        crit = f" 🎯 {int(d.get('crit', 0)*100)}% crit" if d.get("crit") else ""
        return f"{emoji} ×{qty} — {d.get('degats_principal', 0)} + {d.get('degats_secondaire', 0)} secondaire{crit}"
    if t == "virus":
        return f"{emoji} ×{qty} — {d.get('degats', 0)} dmg/30 min ({hours(d.get('duree',0))}h)"
    if t == "poison":
        return f"{emoji} ×{qty} — {d.get('degats', 0)} dmg/{mins(d.get('intervalle',1800))} min ({hours(d.get('duree',0))}h)"
    if t == "infection":
        return (
            f"{emoji} ×{qty} — Infection : {d.get('degats',0)} initiaux + "
            f"{d.get('degats',0)} / {mins(d.get('intervalle',1800))} min "
            f"({hours(d.get('duree',0))}h) ⚠️ Propagation"
        )
    if t == "soin":
        crit = f" ✨ {int(d.get('crit', 0)*100)}% crit" if d.get("crit") else ""
        return f"{emoji} ×{qty} — Soigne {d.get('soin', 0)} PV{crit}"
    if t == "regen":
        return f"{emoji} ×{qty} — Régénère {d.get('valeur',0)} PV / {mins(d.get('intervalle',1800))} min pendant {hours(d.get('duree',0))}h"
    if t == "bouclier":
        return f"{emoji} ×{qty} — Bouclier de {d.get('valeur',0)} PB"
    if t == "esquive+":
        return f"{emoji} ×{qty} — Esquive +{int(d.get('valeur',0)*100)}% pendant {hours(d.get('duree',0))}h"
    if t == "reduction":
        return f"{emoji} ×{qty} — Réduction {int(d.get('valeur',0)*100)}% pendant {hours(d.get('duree',0))}h"
    if t == "immunite":
        return f"{emoji} ×{qty} — Immunité {hours(d.get('duree',0))}h"
    if t == "mysterybox":
        return f"{emoji} ×{qty} — Contenu aléatoire"
    if t == "vol":
        return f"{emoji} ×{qty} — Permet de voler un objet"
    if t == "vaccin":
        return f"{emoji} ×{qty} — Nettoie les statuts néfastes"

    return f"{emoji} ×{qty}"

# ------------------------------------------------------------------
# Cog
# ------------------------------------------------------------------

class InventoryCog(commands.Cog):
    """Commandes d'inventaire (/inv et /inventory)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        await init_inventory_db()

    async def _send_inv(self, itx: Interaction, target: discord.User):
        items = await get_all_items(target.id)
        tickets = await get_tickets(target.id)
        ok_ticket, rem_ticket = await can_claim_daily_ticket(target.id)
        golds = await get_balance(target.id)

        emb = Embed(
            title=f"📦 Inventaire GotValis de {target.display_name}",
            colour=Colour.blurple()
        )

        # Tickets + état daily
        ticket_line = f"**{tickets}**"
        ticket_line += (
            " — ✅ ticket quotidien **disponible** (`/daily_ticket`)"
            if ok_ticket else f" — ⏳ prochain dans **{_fmt_cd(rem_ticket)}**"
        )
        emb.add_field(
            name="🎟️ Tickets de tirage",
            value=ticket_line,
            inline=False
        )

        # Objets
        if items:
            lines = [_fmt_item_line(emoji, qty) for emoji, qty in items]
            block = "\n".join(lines)
            if len(block) <= 1024:
                emb.add_field(name="Objets", value=block, inline=False)
            else:
                # split en plusieurs fields si trop long
                chunk, total, idx = [], 0, 1
                for line in lines:
                    if total + len(line) + 1 > 1024:
                        emb.add_field(
                            name=f"Objets (suite {idx})",
                            value="\n".join(chunk),
                            inline=False
                        )
                        chunk, total, idx = [], 0, idx + 1
                    chunk.append(line); total += len(line) + 1
                if chunk:
                    emb.add_field(
                        name=f"Objets (suite {idx})",
                        value="\n".join(chunk),
                        inline=False
                    )
        else:
            emb.add_field(name="Objets", value="*(vide)*", inline=False)

        # GoldValis
        emb.add_field(name="💰 GoldValis", value=f"**{golds}**", inline=False)

        await itx.response.send_message(embed=emb, ephemeral=(target.id == itx.user.id))

    # /inv
    @app_commands.command(name="inv", description="Affiche ton inventaire (tickets, objets, GoldValis).")
    async def inv(self, itx: Interaction, user: discord.User | None = None):
        await self._send_inv(itx, user or itx.user)

    # alias /inventory
    @app_commands.command(name="inventory", description="Alias de /inv.")
    async def inventory(self, itx: Interaction, user: discord.User | None = None):
        await self._send_inv(itx, user or itx.user)

async def setup(bot: commands.Bot):
    await bot.add_cog(InventoryCog(bot))

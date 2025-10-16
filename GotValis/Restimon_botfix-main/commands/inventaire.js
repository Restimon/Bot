import { SlashCommandBuilder, EmbedBuilder } from 'discord.js';
import { Player } from '../database/models/Player.js';
import { SHOP_ITEMS } from '../data/shop.js';

export const data = new SlashCommandBuilder()
  .setName('inventaire')
  .setDescription('Affiche votre inventaire')
  .addUserOption(opt =>
    opt
      .setName('user')
      .setDescription("Inventaire d'un autre membre")
      .setRequired(false)
  );

function formatItemLine(item) {
  const meta = SHOP_ITEMS[item.itemName] || SHOP_ITEMS[item.itemId] || {};
  const emoji = meta.emoji ?? item.itemName ?? '';
  const label = meta.name ?? meta.displayName ?? item.itemName ?? 'Objet';
  const qty = item.quantity ?? 1;
  return `${qty}x ${emoji} ${label}`;
}

function chunk(arr, size) {
  const out = [];
  for (let i = 0; i < arr.length; i += size) out.push(arr.slice(i, i + size));
  return out;
}

export async function execute(interaction) {
  await interaction.deferReply();

  try {
    const targetUser = interaction.options.getUser('user') || interaction.user;

    let player = await Player.findOne({ userId: targetUser.id });
    if (!player) {
      player = await Player.create({
        userId: targetUser.id,
        username: targetUser.username,
        economy: { coins: 0, totalEarned: 0 },
        gachaTickets: 0,
        inventory: [],
        lastUpdated: new Date(),
      });
    }

    // Tickets gacha
    const gachaTickets = Number(player.gachaTickets ?? 0);

    // Filtrer les tickets de l’inventaire (sinon doublon d’affichage)
    const inventory = (player.inventory || []).filter(
      it => !/ticket|🎟️/i.test(it.itemName || '')
    );

    // Trier (optionnel) par nom puis quantité
    inventory.sort((a, b) => {
      const an = (a.itemName || '').localeCompare(b.itemName || '');
      if (an !== 0) return an;
      return (b.quantity || 0) - (a.quantity || 0);
    });

    const lines = inventory.map(formatItemLine);
    const pages = chunk(lines, 24); // 24 lignes max pour rester lisible
    const page0 = pages[0] || ['—'];

    const embed = new EmbedBuilder()
      .setColor('#3498DB')
      .setTitle(`🎒 Inventaire — ${targetUser.username}`)
      .addFields(
        { name: '🎟️ Tickets', value: String(gachaTickets), inline: true },
        { name: '💳 Solde', value: `${player.economy?.coins ?? 0} GC`, inline: true },
        { name: '📦 Objets', value: page0.join('\n'), inline: false }
      )
      .setTimestamp();

    // Si besoin, indiquer qu’il y a plus d’items
    if (pages.length > 1) {
      embed.setFooter({ text: `Page 1/${pages.length} — utilisez /collection ou /inventaire pour plus de détails` });
    }

    await interaction.editReply({ embeds: [embed] });
  } catch (err) {
    console.error('Erreur /inventaire:', err);
    await interaction.editReply({
      content: '❌ Impossible d’afficher l’inventaire.',
      ephemeral: true,
    });
  }
}

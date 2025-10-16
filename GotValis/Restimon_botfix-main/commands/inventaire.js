import { SlashCommandBuilder, EmbedBuilder } from 'discord.js';
import { Player } from '../database/models/Player.js';
import { SHOP_ITEMS } from '../data/shop.js';
import { getItemCategory } from '../data/itemCategories.js';
import { COLORS } from '../utils/colors.js';

export const data = new SlashCommandBuilder()
  .setName('inventaire')
  .setNameLocalizations({ fr: 'inventaire' })
  .setDescription('Affiche votre inventaire complet')
  .addUserOption(option =>
    option
      .setName('joueur')
      .setDescription("Le membre dont vous voulez voir l'inventaire")
      .setRequired(false)
  );

export async function execute(interaction) {
  await interaction.deferReply();

  const targetUser = interaction.options.getUser('joueur') || interaction.user;

  try {
    const player = await Player.findOne({ userId: targetUser.id });

    if (!player) {
      await interaction.editReply({
        content: '❌ Profil non trouvé.',
        ephemeral: true,
      });
      return;
    }

    // Tickets (source de vérité = gachaTickets)
    const gachaTickets = Number(player.gachaTickets ?? 0);

    // Regroupe les items (et filtre les "tickets" de l'inventaire)
    const itemGroups = {};
    for (const it of (player.inventory || [])) {
      const name = it.itemName || it.itemId || '';
      if (!name || /ticket|🎟️/i.test(name)) continue; // pas de doublon
      const qty = Number(it.quantity ?? 1);
      itemGroups[name] = (itemGroups[name] || 0) + qty;
    }

    const categorized = { fight: [], heal: [], use: [], other: [] };

    function toLine(emojiKey, qty) {
      const metaShop = SHOP_ITEMS[emojiKey] || {};
      const label    = metaShop.name || metaShop.displayName || 'Objet';
      const desc     = (getItemCategory?.(emojiKey)?.description) || '';
      return `${qty}x ${emojiKey} [${label}]${desc ? ` — ${desc}` : ''}`;
    }

    for (const [emojiOrKey, quantity] of Object.entries(itemGroups)) {
      const meta = getItemCategory?.(emojiOrKey) || {};
      const cat  = (meta.category || '').toLowerCase();
      const line = toLine(emojiOrKey, quantity);

      if (cat === 'fight') categorized.fight.push(line);
      else if (cat === 'heal' || cat === 'soins') categorized.heal.push(line);
      else if (cat === 'use' || cat === 'utilitaire' || cat === 'utility') categorized.use.push(line);
      else categorized.other.push(line);
    }

    function section(title, arr) {
      if (!arr.length) return '';
      return `**${title}**\n${arr.sort().join('\n')}\n\n`;
    }

    let objectsText = '';
    objectsText += section('Fight', categorized.fight);
    objectsText += section('Soins', categorized.heal);
    objectsText += section('Utilitaires', categorized.use);
    if (!objectsText) {
      objectsText = categorized.other.length
        ? section('Divers', categorized.other)
        : '*Aucun objet*';
    }

    const thumbnailURL = player.equippedCharacter?.image
      ? player.equippedCharacter.image
      : targetUser.displayAvatarURL({ dynamic: true });

    const embed = new EmbedBuilder()
      .setColor(COLORS?.INVENTORY || '#3498DB')
      .setTitle(`🎒 Inventaire — ${targetUser.username}`)
      .setDescription(objectsText)
      .setThumbnail(thumbnailURL)
      .addFields(
        { name: '💰 GotCoins', value: String(player.economy?.coins ?? 0), inline: true },
        { name: '🎟️ Tickets', value: String(gachaTickets), inline: true }
      )
      .setTimestamp();

    await interaction.editReply({ embeds: [embed] });
  } catch (error) {
    console.error('Erreur dans la commande /inventaire:', error);
    await interaction.editReply({
      content: '❌ Une erreur est survenue lors de la récupération de l’inventaire.',
      ephemeral: true,
    });
  }
}

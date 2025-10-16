import { SlashCommandBuilder, EmbedBuilder } from 'discord.js';
import { Player } from '../database/models/Player.js';
import { getItemCategory } from '../data/itemCategories.js';
import { COLORS } from '../utils/colors.js';

export const data = new SlashCommandBuilder()
  .setName('inventaire')
  .setNameLocalizations({ fr: 'inventaire' })
  .setDescription('Affiche votre inventaire complet')
  .addUserOption(option =>
    option
      .setName('joueur')
      .setDescription('Le joueur dont vous voulez voir l\'inventaire')
      .setRequired(false)
  );

export async function execute(interaction) {
  await interaction.deferReply();

  const targetUser = interaction.options.getUser('joueur') || interaction.user;

  try {
    const player = await Player.findOne({ userId: targetUser.id });

    if (!player) {
      return await interaction.editReply({
        content: `❌ Profil non trouvé.`,
        ephemeral: true,
      });
    }

    // Group items by emoji
    const itemGroups = {};
    for (const item of player.inventory) {
      if (itemGroups[item.itemName]) {
        itemGroups[item.itemName] += item.quantity || 1;
      } else {
        itemGroups[item.itemName] = item.quantity || 1;
      }
    }

    // Categorize items
    const categorizedItems = {
      fight: [],
      heal: [],
      use: []
    };

    for (const [emoji, quantity] of Object.entries(itemGroups)) {
      const itemData = getItemCategory(emoji);
      if (itemData && itemData.category) {
        categorizedItems[itemData.category].push({
          emoji,
          quantity,
          description: itemData.description
        });
      }
    }

    // Build objects section
    let objectsText = '**Objets**\n';

    // Combine all categories into single column layout
    const allItems = [
      ...categorizedItems.fight,
      ...categorizedItems.heal,
      ...categorizedItems.use
    ];

    if (allItems.length === 0) {
      objectsText += '*Aucun objet*';
    } else {
      // Create single column layout
      for (const item of allItems) {
        objectsText += `${item.quantity}x ${item.emoji} ${item.description}\n`;
      }
    }

    // Get equipped character info
    const equippedChar = player.equippedCharacter;
    const thumbnailURL = equippedChar && equippedChar.image
      ? equippedChar.image
      : targetUser.displayAvatarURL({ dynamic: true });

    const embed = new EmbedBuilder()
      .setColor(COLORS.INVENTORY)
      .setTitle(`🎒 Inventaire — ${targetUser.username}`)
      .setDescription(objectsText)
      .setThumbnail(thumbnailURL)
      .addFields(
        {
          name: '💰 GotCoins',
          value: player.economy.coins.toString(),
          inline: true,
        },
        {
          name: '🎟️ Tickets', value: String(player.gachaTickets || 0), inline: true },
        }
      )
      .setTimestamp();

    await interaction.editReply({ embeds: [embed] });

  } catch (error) {
    console.error('Erreur dans la commande /inventaire:', error);
    await interaction.editReply({
      content: '❌ Une erreur est survenue lors de la récupération de l\'inventaire.',
      ephemeral: true,
    });
  }
}

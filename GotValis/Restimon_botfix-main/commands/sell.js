import { SlashCommandBuilder, EmbedBuilder } from 'discord.js';
import { Player } from '../database/models/Player.js';
import { getItemCategory } from '../data/itemCategories.js';
import { SHOP_ITEMS } from '../data/shop.js';

export const data = new SlashCommandBuilder()
  .setName('sell')
  .setNameLocalizations({ fr: 'sell' })
  .setDescription('Vend un objet de votre inventaire')
  .addStringOption(option =>
    option
      .setName('objet')
      .setDescription('L\'objet à vendre (emoji)')
      .setRequired(true)
      .setAutocomplete(true)
  )
  .addIntegerOption(option =>
    option
      .setName('quantite')
      .setDescription('Quantité à vendre (par défaut: 1)')
      .setRequired(false)
      .setMinValue(1)
  );

export async function autocomplete(interaction) {
  const focusedValue = interaction.options.getFocused().toLowerCase();

  try {
    const player = await Player.findOne({ userId: interaction.user.id });

    if (!player || !player.inventory || player.inventory.length === 0) {
      return await interaction.respond([]);
    }

    const choices = [];
    for (const item of player.inventory) {
      // Skip if quantity is 0 or less
      if (item.quantity <= 0) continue;

      const itemData = getItemCategory(item.itemName);
      const itemName = itemData?.name || item.itemName;

      const shopData = SHOP_ITEMS[item.itemName];
      const sellPrice = shopData?.sellPrice || Math.floor((shopData?.buyPrice || 50) * 0.6);

      const label = `${item.itemName} ${itemName} x${item.quantity} (${sellPrice} GC/u)`;

      if (label.toLowerCase().includes(focusedValue) || item.itemName.includes(focusedValue) || itemName.toLowerCase().includes(focusedValue)) {
        choices.push({
          name: label.substring(0, 100), // Discord limit
          value: item.itemName
        });
      }
    }

    await interaction.respond(choices.slice(0, 25));
  } catch (error) {
    console.error('Erreur autocomplete /sell:', error);
    await interaction.respond([]);
  }
}

export async function execute(interaction) {
  await interaction.deferReply();

  const itemEmoji = interaction.options.getString('objet');
  const quantity = interaction.options.getInteger('quantite') || 1;

  try {
    const player = await Player.findOne({ userId: interaction.user.id });

    if (!player) {
      return await interaction.editReply({
        content: `❌ Profil non trouvé.`,
        ephemeral: true,
      });
    }

    // Check if player owns the item
    const inventoryItem = player.inventory.find(item => item.itemName === itemEmoji);

    if (!inventoryItem || inventoryItem.quantity < quantity) {
      return await interaction.editReply({
        content: `❌ Vous ne possédez pas assez de cet objet. Vous avez: ${inventoryItem?.quantity || 0}, demandé: ${quantity}`,
        ephemeral: true,
      });
    }

    const itemData = getItemCategory(itemEmoji);
    const itemName = itemData?.name || itemEmoji;

    const shopData = SHOP_ITEMS[itemEmoji];
    const sellPrice = shopData?.sellPrice || Math.floor((shopData?.buyPrice || 50) * 0.6);
    const totalEarned = sellPrice * quantity;

    // Remove items from inventory
    inventoryItem.quantity -= quantity;
    if (inventoryItem.quantity <= 0) {
      player.inventory = player.inventory.filter(item => item.itemName !== itemEmoji);
    }

    // Add coins to player
    player.economy.coins += totalEarned;
    await player.save();

    const embed = new EmbedBuilder()
      .setColor('#2ECC71')
      .setTitle('💰 Vente réussie')
      .setDescription(
        `Vous avez vendu **${quantity}x ${itemEmoji} ${itemName}** pour **${totalEarned} GC** (${sellPrice} GC/u).\n\n` +
        `Solde actuel: **${player.economy.coins} GC**`
      )
      .setTimestamp();

    await interaction.editReply({ embeds: [embed] });

  } catch (error) {
    console.error('Erreur dans la commande /sell:', error);
    await interaction.editReply({
      content: '❌ Une erreur est survenue lors de la vente de l\'objet.',
      ephemeral: true,
    });
  }
}

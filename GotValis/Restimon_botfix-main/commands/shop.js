import { SlashCommandBuilder, EmbedBuilder } from 'discord.js';
import { Player } from '../database/models/Player.js';
import { getAllShopItems, getShopItem, RARITY_SELL_VALUES } from '../data/shop.js';
import { getCharacterById, getRarityInfo } from '../data/characters.js';
import { awardGotValis, deductGotValis } from '../utils/gotvalis.js';

export const data = new SlashCommandBuilder()
  .setName('shop')
  .setNameLocalizations({ fr: 'boutique' })
  .setDescription('Achetez ou vendez des objets et personnages')
  .addSubcommand(subcommand =>
    subcommand
      .setName('list')
      .setDescription('Affiche tous les articles disponibles')
  )
  .addSubcommand(subcommand =>
    subcommand
      .setName('buy')
      .setDescription('Acheter un objet')
      .addStringOption(option =>
        option
          .setName('objet')
          .setDescription('Emoji de l\'objet à acheter')
          .setRequired(true)
      )
      .addIntegerOption(option =>
        option
          .setName('quantité')
          .setDescription('Quantité à acheter (défaut: 1)')
          .setMinValue(1)
          .setMaxValue(99)
          .setRequired(false)
      )
  )
  .addSubcommand(subcommand =>
    subcommand
      .setName('sell')
      .setDescription('Vendre un objet de votre inventaire')
      .addStringOption(option =>
        option
          .setName('objet')
          .setDescription('Nom de l\'objet à vendre')
          .setRequired(true)
          .setAutocomplete(true)
      )
      .addIntegerOption(option =>
        option
          .setName('quantité')
          .setDescription('Quantité à vendre (défaut: 1)')
          .setMinValue(1)
          .setRequired(false)
      )
  )
  .addSubcommand(subcommand =>
    subcommand
      .setName('sell-character')
      .setDescription('Vendre un personnage de votre collection')
      .addStringOption(option =>
        option
          .setName('personnage')
          .setDescription('Personnage à vendre')
          .setRequired(true)
          .setAutocomplete(true)
      )
  );

export async function autocomplete(interaction) {
  const focusedOption = interaction.options.getFocused(true);

  try {
    const player = await Player.findOne({ userId: interaction.user.id });

    if (!player) {
      return await interaction.respond([]);
    }

    if (focusedOption.name === 'objet') {
      // Show inventory items
      const uniqueItems = {};
      player.inventory.forEach(item => {
        if (uniqueItems[item.itemName]) {
          uniqueItems[item.itemName] += item.quantity || 1;
        } else {
          uniqueItems[item.itemName] = item.quantity || 1;
        }
      });

      const choices = Object.entries(uniqueItems).map(([name, qty]) => ({
        name: `${name} (x${qty})`,
        value: name,
      }));

      const filtered = choices.filter(choice =>
        choice.name.toLowerCase().includes(focusedOption.value.toLowerCase())
      ).slice(0, 25);

      await interaction.respond(filtered);
    } else if (focusedOption.name === 'personnage') {
      // Show owned characters
      const choices = player.characterCollection.map(c => {
        const char = getCharacterById(c.characterId);
        return char ? {
          name: `${char.name} (${char.rarity})`,
          value: char.id,
        } : null;
      }).filter(c => c !== null);

      const filtered = choices.filter(choice =>
        choice.name.toLowerCase().includes(focusedOption.value.toLowerCase())
      ).slice(0, 25);

      await interaction.respond(filtered);
    }
  } catch (error) {
    console.error('Error in shop autocomplete:', error);
    await interaction.respond([]);
  }
}

export async function execute(interaction) {
  await interaction.deferReply();

  const subcommand = interaction.options.getSubcommand();

  try {
    if (subcommand === 'list') {
      await handleList(interaction);
    } else if (subcommand === 'buy') {
      await handleBuy(interaction);
    } else if (subcommand === 'sell') {
      await handleSell(interaction);
    } else if (subcommand === 'sell-character') {
      await handleSellCharacter(interaction);
    }
  } catch (error) {
    console.error('Error in /shop command:', error);
    await interaction.editReply({
      content: '❌ Une erreur est survenue.',
      ephemeral: true,
    });
  }
}

async function handleList(interaction) {
  const items = getAllShopItems();

  const itemList = items.map(item =>
    `${item.emoji} **${item.name}** - Achat: ${item.buyPrice} | Vente: ${item.sellPrice}`
  ).join('\n');

  const embed = new EmbedBuilder()
    .setColor('#F39C12')
    .setTitle('🏪 Boutique GotValis')
    .setDescription(itemList)
    .setFooter({ text: 'Utilisez /shop buy <emoji> pour acheter' })
    .setTimestamp();

  await interaction.editReply({ embeds: [embed] });
}

async function handleBuy(interaction) {
  const itemEmoji = interaction.options.getString('objet');
  const quantity = interaction.options.getInteger('quantité') || 1;

  const item = getShopItem(itemEmoji);

  if (!item) {
    return await interaction.editReply({
      content: '❌ Objet non trouvé dans la boutique.',
      ephemeral: true,
    });
  }

  const totalCost = item.buyPrice * quantity;

  let player = await Player.findOne({ userId: interaction.user.id });

  if (!player) {
    player = await Player.create({
      userId: interaction.user.id,
      username: interaction.user.username,
    });
  }

  if (player.economy.coins < totalCost) {
    return await interaction.editReply({
      content: `❌ Vous n'avez pas assez de GotCoins. Coût: **${totalCost}**, Solde: **${player.economy.coins}**`,
      ephemeral: true,
    });
  }

  // Deduct coins
  player.economy.coins -= totalCost;

  // Add items to inventory
  for (let i = 0; i < quantity; i++) {
    player.inventory.push({
      itemId: `${itemEmoji}_${Date.now()}_${i}`,
      itemName: `${itemEmoji} ${item.name}`,
      quantity: 1,
    });
  }

  player.lastUpdated = new Date();
  await player.save();

  // GotValis earns the coins
  await awardGotValis(totalCost, `Shop purchase: ${item.name} x${quantity}`);

  const embed = new EmbedBuilder()
    .setColor('#2ECC71')
    .setTitle('✅ Achat réussi !')
    .setDescription(
      `Vous avez acheté **${quantity}x ${itemEmoji} ${item.name}** pour **${totalCost} GotCoins**.\n\n` +
      `💰 Nouveau solde: **${player.economy.coins} GotCoins**`
    )
    .setTimestamp();

  await interaction.editReply({ embeds: [embed] });
}

async function handleSell(interaction) {
  const itemName = interaction.options.getString('objet');
  const quantity = interaction.options.getInteger('quantité') || 1;

  const player = await Player.findOne({ userId: interaction.user.id });

  if (!player || !player.inventory || player.inventory.length === 0) {
    return await interaction.editReply({
      content: '❌ Votre inventaire est vide.',
      ephemeral: true,
    });
  }

  // Find matching items
  const matchingItems = player.inventory.filter(item =>
    item.itemName.toLowerCase().includes(itemName.toLowerCase())
  );

  if (matchingItems.length < quantity) {
    return await interaction.editReply({
      content: `❌ Vous n'avez que **${matchingItems.length}** de cet objet.`,
      ephemeral: true,
    });
  }

  // Extract emoji and find shop item
  const firstItem = matchingItems[0].itemName;
  const emojiMatch = firstItem.match(/[\p{Emoji}]/u);
  const emoji = emojiMatch ? emojiMatch[0] : null;
  const shopItem = emoji ? getShopItem(emoji) : null;

  if (!shopItem || shopItem.sellPrice === 0) {
    return await interaction.editReply({
      content: '❌ Cet objet ne peut pas être vendu.',
      ephemeral: true,
    });
  }

  const totalValue = shopItem.sellPrice * quantity;

  // Remove items from inventory
  for (let i = 0; i < quantity; i++) {
    const index = player.inventory.findIndex(item =>
      item.itemName.toLowerCase().includes(itemName.toLowerCase())
    );
    if (index !== -1) {
      player.inventory.splice(index, 1);
    }
  }

  // Add coins
  player.economy.coins += totalValue;
  player.lastUpdated = new Date();
  await player.save();

  // GotValis loses coins
  await deductGotValis(totalValue, `Shop sell: ${shopItem.name} x${quantity}`);

  const embed = new EmbedBuilder()
    .setColor('#E67E22')
    .setTitle('✅ Vente réussie !')
    .setDescription(
      `Vous avez vendu **${quantity}x ${emoji} ${shopItem.name}** pour **${totalValue} GotCoins**.\n\n` +
      `💰 Nouveau solde: **${player.economy.coins} GotCoins**`
    )
    .setTimestamp();

  await interaction.editReply({ embeds: [embed] });
}

async function handleSellCharacter(interaction) {
  const characterId = interaction.options.getString('personnage');

  const player = await Player.findOne({ userId: interaction.user.id });

  if (!player || !player.characterCollection || player.characterCollection.length === 0) {
    return await interaction.editReply({
      content: '❌ Vous n\'avez aucun personnage.',
      ephemeral: true,
    });
  }

  const charIndex = player.characterCollection.findIndex(c => c.characterId === characterId);

  if (charIndex === -1) {
    return await interaction.editReply({
      content: '❌ Vous ne possédez pas ce personnage.',
      ephemeral: true,
    });
  }

  const character = getCharacterById(characterId);

  if (!character) {
    return await interaction.editReply({
      content: '❌ Personnage non trouvé.',
      ephemeral: true,
    });
  }

  const rarityInfo = getRarityInfo(character.rarity);
  const sellValue = RARITY_SELL_VALUES[rarityInfo.name] || 50;

  // Check if character is equipped
  if (player.equippedCharacter?.characterId === characterId) {
    player.equippedCharacter = { characterId: null, equippedAt: null };
  }

  // Remove character
  player.characterCollection.splice(charIndex, 1);

  // Add coins
  player.economy.coins += sellValue;
  player.lastUpdated = new Date();
  await player.save();

  // GotValis loses coins
  await deductGotValis(sellValue, `Character sell: ${character.name}`);

  const embed = new EmbedBuilder()
    .setColor(rarityInfo.color)
    .setTitle('✅ Personnage vendu !')
    .setDescription(
      `Vous avez vendu **${character.name}** (${rarityInfo.name}) pour **${sellValue} GotCoins**.\n\n` +
      `💰 Nouveau solde: **${player.economy.coins} GotCoins**`
    )
    .setTimestamp();

  await interaction.editReply({ embeds: [embed] });
}

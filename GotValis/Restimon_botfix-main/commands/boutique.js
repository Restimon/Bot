import {
  SlashCommandBuilder,
  EmbedBuilder,
  ActionRowBuilder,
  ButtonBuilder,
  ButtonStyle,
  ComponentType
} from 'discord.js';
import { Player } from '../database/models/Player.js';
import { getItemCategory } from '../data/itemCategories.js';
import { SHOP_ITEMS, RARITY_SELL_VALUES } from '../data/shop.js';

export const data = new SlashCommandBuilder()
  .setName('boutique')
  .setNameLocalizations({ fr: 'boutique' })
  .setDescription('Ouvre la boutique pour acheter des objets');

// Organize items by category
const DAMAGE_ITEMS = ["❄️", "⚔️", "🔥", "⚡", "🔫", "🧨", "☠️", "🦠", "🧪", "🧟"];
const HEAL_UTILITY_ITEMS = ["🍀", "🩹", "🩸", "💊", "💕", "🎁", "🔍", "💉", "🛡️", "👟", "🪖", "⭐"];

export async function execute(interaction) {
  await interaction.deferReply();

  try {
    const player = await Player.findOne({ userId: interaction.user.id });

    if (!player) {
      return await interaction.editReply({
        content: `❌ Profil non trouvé.`,
        ephemeral: true,
      });
    }

    let currentPage = 0;
    const totalPages = 3;

    // Function to build embed for each page
    const buildEmbed = (page) => {
      const embed = new EmbedBuilder()
        .setColor('#5865F2')
        .setFooter({ text: `Page ${page + 1}/${totalPages} • Aujourd'hui à ${new Date().toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })}` })
        .setTimestamp();

      if (page === 0) {
        // Page 1: Damage Items
        embed.setTitle('🏪 Boutique GotValis');
        embed.setDescription(`💰 **Votre solde**: ${player.economy.coins} GC\n`);

        let itemsText = '';
        DAMAGE_ITEMS.forEach(emoji => {
          const shopData = SHOP_ITEMS[emoji];
          if (shopData) {
            itemsText += `${emoji} **${shopData.name}** ${shopData.description} — **${shopData.buyPrice} GC**\n`;
          }
        });

        embed.addFields({
          name: '⚔️ Objets de Combat',
          value: itemsText || 'Aucun objet',
          inline: false
        });

      } else if (page === 1) {
        // Page 2: Healing & Utility Items
        embed.setTitle('🏪 Boutique GotValis');
        embed.setDescription(`💰 **Votre solde**: ${player.economy.coins} GC\n`);

        let healText = '';
        let utilityText = '';

        ["🍀", "🩹", "🩸", "💊", "💕"].forEach(emoji => {
          const shopData = SHOP_ITEMS[emoji];
          if (shopData) {
            healText += `${emoji} **${shopData.name}** ${shopData.description} — **${shopData.buyPrice} GC**\n`;
          }
        });

        ["🎁", "🔍", "💉", "🛡️", "👟", "🪖", "⭐"].forEach(emoji => {
          const shopData = SHOP_ITEMS[emoji];
          if (shopData) {
            utilityText += `${emoji} **${shopData.name}** ${shopData.description} — **${shopData.buyPrice} GC**\n`;
          }
        });

        embed.addFields(
          {
            name: '💚 Objets de Soin',
            value: healText || 'Aucun objet',
            inline: false
          },
          {
            name: '🛠️ Objets Utilitaires',
            value: utilityText || 'Aucun objet',
            inline: false
          }
        );

      } else if (page === 2) {
        // Page 3: Ticket System & Rarity Sell Prices
        embed.setTitle('🏪 Boutique du serveur');
        embed.setDescription('Bienvenue dans la boutique du serveur !');

        const ticketData = SHOP_ITEMS["🎫"];
        let ticketText = '';
        if (ticketData) {
          ticketText = `🎫 **${ticketData.buyPrice} GC - Acheter**\n\n`;
          ticketText += `Avec les tickets, invoque un personnage pour t'aider à survivre dans ce monde. Chaque personnage possède un passif unique, capable de modifier ton destin (ou de l'empirer). Collectionne-les tous, ou choisis le passif qui t'offrira l'avantage dont tu as besoin.`;
        }

        let rarityText = `**Prix de vente par rareté :**\n\n`;
        rarityText += ` • **Commun** — ${RARITY_SELL_VALUES["Commun"]} GC\n`;
        rarityText += ` • **Peu commun** — ${RARITY_SELL_VALUES["Peu commun"]} GC\n`;
        rarityText += ` • **Rare** — ${RARITY_SELL_VALUES["Rare"]} GC\n`;
        rarityText += ` • **Épique** — ${RARITY_SELL_VALUES["Épique"]} GC\n`;
        rarityText += ` • **Légendaire** — ${RARITY_SELL_VALUES["Légendaire"]} GC`;

        embed.addFields(
          {
            name: '🎟️ Système de Tickets',
            value: ticketText || 'Aucun ticket disponible',
            inline: false
          },
          {
            name: '💎 Prix de vente selon la rareté',
            value: rarityText,
            inline: false
          }
        );
      }

      return embed;
    };

    // Function to build buttons
    const buildButtons = (page, disabled = false) => {
      const buttons = new ActionRowBuilder();

      // Previous button
      buttons.addComponents(
        new ButtonBuilder()
          .setCustomId('prev_page')
          .setLabel('Précédent')
          .setStyle(ButtonStyle.Secondary)
          .setDisabled(page === 0 || disabled)
      );

      // Page indicator
      buttons.addComponents(
        new ButtonBuilder()
          .setCustomId('page_indicator')
          .setLabel(`Page ${page + 1}/${totalPages}`)
          .setStyle(ButtonStyle.Primary)
          .setDisabled(true)
      );

      // Next button
      buttons.addComponents(
        new ButtonBuilder()
          .setCustomId('next_page')
          .setLabel('Suivant')
          .setStyle(ButtonStyle.Secondary)
          .setDisabled(page === totalPages - 1 || disabled)
      );

      return buttons;
    };

    // Build buy buttons for items on current page
    const buildBuyButtons = (page) => {
      const rows = [];
      let items = [];

      if (page === 0) {
        items = DAMAGE_ITEMS; // All damage items
      } else if (page === 1) {
        items = HEAL_UTILITY_ITEMS; // All heal & utility items
      } else if (page === 2) {
        // Ticket page
        items = ["🎫"];
      }

      // Create rows of 5 buttons each
      for (let i = 0; i < items.length; i += 5) {
        const row = new ActionRowBuilder();
        const chunk = items.slice(i, Math.min(i + 5, items.length));

        chunk.forEach(emoji => {
          const shopData = SHOP_ITEMS[emoji];
          if (shopData) {
            row.addComponents(
              new ButtonBuilder()
                .setCustomId(`buy_${emoji}`)
                .setLabel(`${emoji} ${shopData.buyPrice} GC`)
                .setStyle(ButtonStyle.Success)
            );
          }
        });

        // Only add row if it has components
        if (row.components.length > 0) {
          rows.push(row);
        }
      }

      return rows;
    };

    // Send initial message
    const embed = buildEmbed(currentPage);
    const buyButtons = buildBuyButtons(currentPage);
    const navButtons = buildButtons(currentPage);

    const components = [...buyButtons, navButtons];

    const response = await interaction.editReply({
      embeds: [embed],
      components: components
    });

    // Create collector for button interactions
    const collector = response.createMessageComponentCollector({
      componentType: ComponentType.Button,
      time: 300000 // 5 minutes
    });

    collector.on('collect', async (i) => {
      if (i.user.id !== interaction.user.id) {
        return await i.reply({
          content: '❌ Cette boutique ne vous appartient pas.',
          ephemeral: true
        });
      }

      // Handle navigation
      if (i.customId === 'prev_page') {
        currentPage = Math.max(0, currentPage - 1);

        const newEmbed = buildEmbed(currentPage);
        const newBuyButtons = buildBuyButtons(currentPage);
        const newNavButtons = buildButtons(currentPage);

        await i.update({
          embeds: [newEmbed],
          components: [...newBuyButtons, newNavButtons]
        });

      } else if (i.customId === 'next_page') {
        currentPage = Math.min(totalPages - 1, currentPage + 1);

        const newEmbed = buildEmbed(currentPage);
        const newBuyButtons = buildBuyButtons(currentPage);
        const newNavButtons = buildButtons(currentPage);

        await i.update({
          embeds: [newEmbed],
          components: [...newBuyButtons, newNavButtons]
        });

      } else if (i.customId.startsWith('buy_')) {
        // Handle purchase
        const emoji = i.customId.replace('buy_', '');
        const shopData = SHOP_ITEMS[emoji];
        const itemData = getItemCategory(emoji);

        if (!shopData) {
          return await i.reply({
            content: '❌ Objet non trouvé.',
            ephemeral: true
          });
        }

        // Refresh player data
        const currentPlayer = await Player.findOne({ userId: i.user.id });

        if (currentPlayer.economy.coins < shopData.buyPrice) {
          return await i.reply({
            content: `❌ Vous n'avez pas assez de GotCoins. Prix: ${shopData.buyPrice} GC, Votre solde: ${currentPlayer.economy.coins} GC`,
            ephemeral: true
          });
        }

        // Deduct coins
        currentPlayer.economy.coins -= shopData.buyPrice;

        // Add item to inventory
        const existingItem = currentPlayer.inventory.find(
          item => item.itemName === emoji
        );

        if (existingItem) {
          existingItem.quantity += 1;
        } else {
          currentPlayer.inventory.push({
            itemName: emoji,
            quantity: 1
          });
        }

        await currentPlayer.save();

        // Update player reference
        player.economy.coins = currentPlayer.economy.coins;

        // Update the embed with new balance
        const updatedEmbed = buildEmbed(currentPage);
        const updatedBuyButtons = buildBuyButtons(currentPage);
        const updatedNavButtons = buildButtons(currentPage);

        await i.update({
          embeds: [updatedEmbed],
          components: [...updatedBuyButtons, updatedNavButtons]
        });

        // Send confirmation message
        const confirmEmbed = new EmbedBuilder()
          .setColor('#2ECC71')
          .setTitle('✅ Achat réussi')
          .setDescription(
            `Vous avez acheté **${emoji} ${itemData?.name || shopData.name}** pour **${shopData.buyPrice} GC**.\n\n` +
            `Solde restant: **${currentPlayer.economy.coins} GC**`
          )
          .setTimestamp();

        await i.followUp({ embeds: [confirmEmbed], ephemeral: true });
      }
    });

    collector.on('end', async () => {
      try {
        const finalNavButtons = buildButtons(currentPage, true);
        await interaction.editReply({ components: [finalNavButtons] });
      } catch (error) {
        // Ignore error if message was deleted
      }
    });

  } catch (error) {
    console.error('Erreur dans la commande /boutique:', error);
    await interaction.editReply({
      content: '❌ Une erreur est survenue lors de l\'ouverture de la boutique.',
      ephemeral: true,
    });
  }
}

import { SlashCommandBuilder, EmbedBuilder, ActionRowBuilder, ButtonBuilder, ButtonStyle } from 'discord.js';
import { CHARACTERS, getRarityInfo } from '../data/characters.js';

export const data = new SlashCommandBuilder()
  .setName('gacha_list')
  .setNameLocalizations({ fr: 'gacha_list' })
  .setDescription('Affiche la liste de tous les personnages disponibles avec leurs passifs');

export async function execute(interaction) {
  await interaction.deferReply();

  try {
    // Group characters by rarity
    const charactersByRarity = {
      LEGENDARY: [],
      EPIC: [],
      RARE: [],
      COMMON: []
    };

    for (const character of CHARACTERS) {
      charactersByRarity[character.rarity].push(character);
    }

    const pages = [];

    // Create overview page
    const overviewEmbed = new EmbedBuilder()
      .setColor('#5865F2')
      .setTitle('🎴 Liste des Personnages GotValis')
      .setDescription('Tous les personnages disponibles dans le système de gacha avec leurs passifs.\n\nUtilisez les boutons ci-dessous pour naviguer entre les raretés.')
      .setFooter({ text: `Page 1/${Object.keys(charactersByRarity).length + 1} • Total: ${CHARACTERS.length} personnages` })
      .setTimestamp();

    pages.push(overviewEmbed);

    // Create pages for each rarity
    for (const [rarityKey, characters] of Object.entries(charactersByRarity)) {
      if (characters.length === 0) continue;

      const rarity = getRarityInfo(rarityKey);
      const rarityEmbed = new EmbedBuilder()
        .setColor(rarity.color || '#5865F2')
        .setTitle(`${rarity.emoji} ${rarity.name} (${rarity.weight}%)`)
        .setDescription(`${characters.length} personnages disponibles`);

      let fieldText = '';
      let fieldCount = 1;

      for (const char of characters) {
        const charText = `**${char.name}**\n*${char.faction}*\n📜 **${char.passive}**: ${char.passiveDescription}\n\n`;

        // If adding this character would exceed 1024 chars, create a new field
        if (fieldText.length + charText.length > 1024) {
          rarityEmbed.addFields({
            name: fieldCount === 1 ? 'Personnages' : `Personnages (suite ${fieldCount})`,
            value: fieldText,
            inline: false
          });
          fieldText = charText;
          fieldCount++;
        } else {
          fieldText += charText;
        }
      }

      // Add remaining characters
      if (fieldText.length > 0) {
        rarityEmbed.addFields({
          name: fieldCount === 1 ? 'Personnages' : `Personnages (suite ${fieldCount})`,
          value: fieldText,
          inline: false
        });
      }

      rarityEmbed.setFooter({ text: `Page ${pages.length + 1}/${Object.keys(charactersByRarity).length + 1}` });
      pages.push(rarityEmbed);
    }

    let currentPage = 0;

    // Create navigation buttons
    const getButtons = (page) => {
      const row = new ActionRowBuilder()
        .addComponents(
          new ButtonBuilder()
            .setCustomId('first')
            .setLabel('⏮️')
            .setStyle(ButtonStyle.Primary)
            .setDisabled(page === 0),
          new ButtonBuilder()
            .setCustomId('prev')
            .setLabel('◀️')
            .setStyle(ButtonStyle.Primary)
            .setDisabled(page === 0),
          new ButtonBuilder()
            .setCustomId('next')
            .setLabel('▶️')
            .setStyle(ButtonStyle.Primary)
            .setDisabled(page === pages.length - 1),
          new ButtonBuilder()
            .setCustomId('last')
            .setLabel('⏭️')
            .setStyle(ButtonStyle.Primary)
            .setDisabled(page === pages.length - 1)
        );
      return row;
    };

    // Send initial message
    const message = await interaction.editReply({
      embeds: [pages[currentPage]],
      components: [getButtons(currentPage)]
    });

    // Create collector for button interactions
    const collector = message.createMessageComponentCollector({
      time: 300000 // 5 minutes
    });

    collector.on('collect', async (i) => {
      if (i.user.id !== interaction.user.id) {
        return i.reply({ content: '❌ Ces boutons ne sont pas pour vous !', ephemeral: true });
      }

      switch (i.customId) {
        case 'first':
          currentPage = 0;
          break;
        case 'prev':
          currentPage = Math.max(0, currentPage - 1);
          break;
        case 'next':
          currentPage = Math.min(pages.length - 1, currentPage + 1);
          break;
        case 'last':
          currentPage = pages.length - 1;
          break;
      }

      await i.update({
        embeds: [pages[currentPage]],
        components: [getButtons(currentPage)]
      });
    });

    collector.on('end', () => {
      interaction.editReply({
        embeds: [pages[currentPage]],
        components: []
      }).catch(() => {});
    });

  } catch (error) {
    console.error('Erreur dans la commande /gacha_list:', error);
    await interaction.editReply({
      content: '❌ Une erreur est survenue lors de la récupération de la liste des personnages.',
      ephemeral: true,
    });
  }
}

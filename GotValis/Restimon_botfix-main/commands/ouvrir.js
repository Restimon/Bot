import { SlashCommandBuilder, EmbedBuilder } from 'discord.js';
import { Player } from '../database/models/Player.js';
import { getRarityColor } from '../utils/items.js';

export const data = new SlashCommandBuilder()
  .setName('ouvrir')
  .setNameLocalizations({ fr: 'ouvrir' })
  .setDescription('Ouvre votre dernier loot box reçu');

export async function execute(interaction) {
  await interaction.deferReply();

  try {
    const player = await Player.findOne({ userId: interaction.user.id });

    if (!player || !player.inventory || player.inventory.length === 0) {
      return await interaction.editReply({
        content: '❌ Vous n\'avez aucun item dans votre inventaire.',
        ephemeral: true,
      });
    }

    // Récupérer le dernier item (le plus récent)
    const lastItem = player.inventory[player.inventory.length - 1];

    // Créer l'embed de révélation
    const embed = new EmbedBuilder()
      .setColor(getRarityColor(lastItem.rarity || 'COMMON'))
      .setTitle('📦 Loot Box Ouvert !')
      .setDescription(`**Vous avez reçu :**\n\n${lastItem.itemName}`)
      .addFields(
        {
          name: '📦 Item',
          value: lastItem.itemName,
          inline: true,
        },
        {
          name: '💰 Valeur',
          value: `${lastItem.value || 0} pièces`,
          inline: true,
        }
      )
      .setFooter({ text: `Inventaire: ${player.inventory.length} items` })
      .setTimestamp();

    await interaction.editReply({ embeds: [embed] });

  } catch (error) {
    console.error('Erreur dans la commande /ouvrir:', error);
    await interaction.editReply({
      content: '❌ Une erreur est survenue lors de l\'ouverture du loot box.',
      ephemeral: true,
    });
  }
}

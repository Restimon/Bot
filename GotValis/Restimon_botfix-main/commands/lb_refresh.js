import { SlashCommandBuilder, PermissionFlagsBits } from 'discord.js';
import { updateLeaderboard } from '../utils/leaderboard.js';

export const data = new SlashCommandBuilder()
  .setName('lb_refresh')
  .setDescription('Force une mise à jour immédiate du leaderboard')
  .setDefaultMemberPermissions(PermissionFlagsBits.Administrator);

export async function execute(interaction) {
  await interaction.deferReply({ ephemeral: true });

  const guildId = interaction.guild.id;

  try {
    const success = await updateLeaderboard(interaction.client, guildId);

    if (success) {
      await interaction.editReply({
        content: '✅ Leaderboard mis à jour avec succès !',
        ephemeral: true,
      });
    } else {
      await interaction.editReply({
        content: '❌ Aucun leaderboard configuré pour ce serveur. Utilisez `/lb_set` pour en créer un.',
        ephemeral: true,
      });
    }
  } catch (error) {
    console.error('Error in /lb_refresh command:', error);
    await interaction.editReply({
      content: '❌ Une erreur est survenue lors de la mise à jour du leaderboard.',
      ephemeral: true,
    });
  }
}

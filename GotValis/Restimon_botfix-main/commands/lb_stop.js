import { SlashCommandBuilder, PermissionFlagsBits } from 'discord.js';
import { Leaderboard } from '../database/models/Leaderboard.js';

export const data = new SlashCommandBuilder()
  .setName('lb_stop')
  .setDescription('Supprime le leaderboard du salon')
  .setDefaultMemberPermissions(PermissionFlagsBits.Administrator);

export async function execute(interaction) {
  await interaction.deferReply({ ephemeral: true });

  const guildId = interaction.guild.id;

  try {
    const leaderboard = await Leaderboard.findOne({ guildId });

    if (!leaderboard) {
      return await interaction.editReply({
        content: '❌ Aucun leaderboard configuré pour ce serveur.',
        ephemeral: true,
      });
    }

    try {
      const channel = await interaction.guild.channels.fetch(leaderboard.channelId).catch(() => null);
      const message = channel ? await channel.messages.fetch(leaderboard.messageId).catch(() => null) : null;
      if (message) await message.delete().catch(() => {});
    } catch (error) {
      console.error('Error deleting leaderboard message:', error);
    }

    await Leaderboard.deleteOne({ guildId });

    await interaction.editReply({
      content: '✅ Leaderboard supprimé avec succès !',
      ephemeral: true,
    });
  } catch (error) {
    console.error('Error in /lb_stop command:', error);
    await interaction.editReply({
      content: '❌ Une erreur est survenue lors de la suppression du leaderboard.',
      ephemeral: true,
    });
  }
}

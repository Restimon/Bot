import { SlashCommandBuilder, PermissionFlagsBits } from 'discord.js';
import { Leaderboard } from '../database/models/Leaderboard.js';
import { generateLeaderboardEmbed } from '../utils/leaderboard.js';

export const data = new SlashCommandBuilder()
  .setName('lb_set')
  .setDescription('Configure le salon du leaderboard avec le nombre de joueurs à afficher')
  .addIntegerOption(option =>
    option
      .setName('count')
      .setDescription('Nombre de joueurs à afficher (10 ou 20)')
      .setRequired(true)
      .addChoices(
        { name: '10 joueurs', value: 10 },
        { name: '20 joueurs', value: 20 }
      )
  )
  .setDefaultMemberPermissions(PermissionFlagsBits.Administrator);

export async function execute(interaction) {
  await interaction.deferReply({ ephemeral: true });

  const displayCount = interaction.options.getInteger('count');
  const guildId = interaction.guild.id;
  const channelId = interaction.channel.id;

  try {
    // Check if leaderboard already exists for this guild
    let leaderboard = await Leaderboard.findOne({ guildId });

    if (leaderboard) {
      // Delete old leaderboard message
      try {
        const oldChannel = await interaction.guild.channels.fetch(leaderboard.channelId);
        const oldMessage = await oldChannel.messages.fetch(leaderboard.messageId);
        await oldMessage.delete();
      } catch (error) {
        console.error('Error deleting old leaderboard message:', error);
      }

      // Remove old leaderboard
      await Leaderboard.deleteOne({ guildId });
    }

    // Generate leaderboard embed
    const embed = await generateLeaderboardEmbed(guildId, displayCount);

    // Send leaderboard message
    const message = await interaction.channel.send({ embeds: [embed] });

    // Save leaderboard configuration
    await Leaderboard.create({
      guildId,
      channelId,
      messageId: message.id,
      displayCount,
    });

    await interaction.editReply({
      content: `✅ Leaderboard configuré dans ce salon avec ${displayCount} joueurs affichés.\nLe classement se mettra à jour automatiquement après chaque action.`,
      ephemeral: true,
    });
  } catch (error) {
    console.error('Error in /lb_set command:', error);
    await interaction.editReply({
      content: '❌ Une erreur est survenue lors de la configuration du leaderboard.',
      ephemeral: true,
    });
  }
}

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
    let leaderboard = await Leaderboard.findOne({ guildId });

    if (leaderboard) {
      try {
        const oldChannel = await interaction.guild.channels.fetch(leaderboard.channelId).catch(() => null);
        const oldMessage = oldChannel ? await oldChannel.messages.fetch(leaderboard.messageId).catch(() => null) : null;
        if (oldMessage) await oldMessage.delete().catch(() => {});
      } catch (error) {
        console.error('Error deleting old leaderboard message:', error);
      }
      await Leaderboard.deleteOne({ guildId });
    }

    const embed = await generateLeaderboardEmbed(interaction.client, guildId, displayCount);

    const message = await interaction.channel.send({ embeds: [embed] });

    await Leaderboard.create({
      guildId,
      channelId,
      messageId: message.id,
      displayCount,
    });

    await interaction.editReply({
      content: `✅ Leaderboard configuré dans ce salon avec ${displayCount} joueurs affichés.`,
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

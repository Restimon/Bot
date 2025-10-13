import { SlashCommandBuilder, EmbedBuilder } from 'discord.js';
import { Player } from '../database/models/Player.js';
import { ActivitySession } from '../database/models/ActivitySession.js';
import { COLORS } from '../utils/colors.js';

export const data = new SlashCommandBuilder()
  .setName('info')
  .setNameLocalizations({ fr: 'info' })
  .setDescription('Affiche vos statistiques personnelles')
  .addUserOption(option =>
    option
      .setName('user')
      .setDescription('Utilisateur dont voir les stats (vous par défaut)')
      .setRequired(false)
  );

export async function execute(interaction) {
  await interaction.deferReply();

  const targetUser = interaction.options.getUser('user') || interaction.user;

  try {
    const player = await Player.findOne({ userId: targetUser.id });

    if (!player) {
      return await interaction.editReply({
        content: '❌ Profil non trouvé.',
        ephemeral: true,
      });
    }

    const member = await interaction.guild.members.fetch(targetUser.id);
    const joinedAt = member.joinedAt;

    const sevenDaysAgo = new Date();
    sevenDaysAgo.setDate(sevenDaysAgo.getDate() - 7);

    const voiceSessions = await ActivitySession.find({
      userId: targetUser.id,
      type: 'voice',
      startTime: { $gte: sevenDaysAgo },
    });

    let totalVoiceMinutes = 0;
    voiceSessions.forEach(session => {
      totalVoiceMinutes += session.duration;
    });

    const messageCount = await ActivitySession.countDocuments({
      userId: targetUser.id,
      type: 'message',
      startTime: { $gte: sevenDaysAgo },
    });

    const voiceHours = Math.floor(totalVoiceMinutes / 60);
    const voiceMinutes = totalVoiceMinutes % 60;
    const voiceTimeStr = voiceHours > 0
      ? `${voiceHours} h ${voiceMinutes} min`
      : `${voiceMinutes} min`;

    const higherRankedPlayers = await Player.countDocuments({
      'economy.coins': { $gt: player.economy.coins }
    });
    const rank = higherRankedPlayers + 1;

    let rankingText;
    if (rank === 1) rankingText = '🥇 1er';
    else if (rank === 2) rankingText = '🥈 2e';
    else if (rank === 3) rankingText = '🥉 3e';
    else if (rank <= 10) rankingText = `🎖️ Top 10 (#${rank})`;
    else if (rank <= 50) rankingText = `🏅 Top 50 (#${rank})`;
    else rankingText = 'Non classé';

    const embed = new EmbedBuilder()
      .setColor(COLORS.INFO)
      .setTitle(`📊 Stats — ${targetUser.username}`)
      .setThumbnail(targetUser.displayAvatarURL())
      .addFields(
        {
          name: '📅 Sur le serveur depuis',
          value: `${joinedAt.toLocaleDateString('fr-FR', { day: '2-digit', month: 'long', year: 'numeric' })} • ${joinedAt.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit', timeZone: 'UTC' })} UTC`,
          inline: false,
        },
        {
          name: '💬 Messages (7j)',
          value: `${messageCount}`,
          inline: true,
        },
        {
          name: '🎤 Vocal (7j)',
          value: voiceTimeStr,
          inline: true,
        },
        {
          name: '🏅 Classement',
          value: rankingText,
          inline: false,
        },
        {
          name: '⚔️ Dégâts totaux',
          value: `${player.stats.damageDealt || 0}`,
          inline: true,
        },
        {
          name: '💚 Soins totaux',
          value: `${player.stats.healingDone || 0}`,
          inline: true,
        },
        {
          name: '⚔️ Kills / 💀 Morts',
          value: `${player.stats.kills} / ${player.stats.deaths}`,
          inline: true,
        }
      )
      .setTimestamp();

    await interaction.editReply({ embeds: [embed] });
  } catch (error) {
    console.error('Error in /info command:', error);
    await interaction.editReply({
      content: '❌ Une erreur est survenue lors de la récupération des statistiques.',
      ephemeral: true,
    });
  }
}

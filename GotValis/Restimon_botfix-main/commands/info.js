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

    // Get guild member to get join date
    const member = await interaction.guild.members.fetch(targetUser.id);
    const joinedAt = member.joinedAt;

    // Calculate 7 days ago for stats
    const sevenDaysAgo = new Date();
    sevenDaysAgo.setDate(sevenDaysAgo.getDate() - 7);

    // Get voice sessions in last 7 days
    const voiceSessions = await ActivitySession.find({
      userId: targetUser.id,
      type: 'voice',
      startTime: { $gte: sevenDaysAgo },
    });

    // Calculate total voice time in minutes
    let totalVoiceMinutes = 0;
    voiceSessions.forEach(session => {
      totalVoiceMinutes += session.duration;
    });

    // Get message count in last 7 days
    const messageCount = await ActivitySession.countDocuments({
      userId: targetUser.id,
      type: 'message',
      startTime: { $gte: sevenDaysAgo },
    });

    // Format voice time
    const voiceHours = Math.floor(totalVoiceMinutes / 60);
    const voiceMinutes = totalVoiceMinutes % 60;
    const voiceTimeStr = voiceHours > 0
      ? `${voiceHours} h ${voiceMinutes} min`
      : `${voiceMinutes} min`;

    // Get leaderboard ranking by coins
    const higherRankedPlayers = await Player.countDocuments({
      'economy.coins': { $gt: player.economy.coins }
    });
    const rank = higherRankedPlayers + 1;
    const rankingText = rank <= 20 ? `#${rank}` : 'Non classé';

    // Build embed
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
          name: '🏅 Classement (Points)',
          value: rankingText,
          inline: false,
        },
        {
          name: '⚔️ Dégâts totaux (vie)',
          value: `${player.stats.damageDealt || 0}`,
          inline: true,
        },
        {
          name: '💚 Soins totaux (vie)',
          value: `${player.stats.healingDone || 0}`,
          inline: true,
        },
        {
          name: '⚔️ Kills / 💀 Morts (vie)',
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

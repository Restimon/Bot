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

    // Classement aligné sur /profile : simple #<rang>, sans libellé supplémentaire
    const higherRankedPlayers = await Player.countDocuments({
      'economy.coins': { $gt: (player.economy?.coins ?? 0) }
    });
    const rank = higherRankedPlayers + 1;
    const rankingText = `#${rank}`;

    const embed = new EmbedBuilder()
      .setColor(COLORS.INFO)
      .setTitle(`📊 Stats — ${targetUser.username}`)
      .setThumbnail(targetUser.displayAvatarURL({ dynamic: true }))
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
          name: '⚔️ Dégâts totaux (vie)',
          value: `${player.stats?.damageDealt ?? 0}`,
          inline: true,
        },
        {
          name: '💚 Soins totaux (vie)',
          value: `${player.stats?.healingDone ?? 0}`,
          inline: true,
        },
        {
          name: '⚔️ Kills / 💀 Morts',
          value: `${player.stats?.kills ?? 0} / ${player.stats?.deaths ?? 0}`,
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

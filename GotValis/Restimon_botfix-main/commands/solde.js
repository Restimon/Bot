import { SlashCommandBuilder, EmbedBuilder } from 'discord.js';
import { Player } from '../database/models/Player.js';

export const data = new SlashCommandBuilder()
  .setName('solde')
  .setNameLocalizations({ fr: 'solde' })
  .setDescription('Affiche votre solde (GotCoins et Tickets)')
  .addUserOption(option =>
    option
      .setName('joueur')
      .setDescription('Le joueur dont vous voulez voir le solde')
      .setRequired(false)
  );

export async function execute(interaction) {
  await interaction.deferReply();

  const targetUser = interaction.options.getUser('joueur') || interaction.user;

  try {
    const player = await Player.findOne({ userId: targetUser.id });

    if (!player) {
      return await interaction.editReply({
        content: `❌ Profil non trouvé.`,
        ephemeral: true,
      });
    }

    const coins = player.economy.coins || 0;
    const tickets = player.economy.tickets || 0;
    const totalEarned = player.economy.totalEarned || 0;

    const embed = new EmbedBuilder()
      .setColor('#5865F2')
      .setTitle(`💰 Solde — ${targetUser.username}`)
      .setThumbnail(targetUser.displayAvatarURL({ dynamic: true }))
      .addFields(
        {
          name: '💰 GotCoins',
          value: `${coins.toLocaleString()} GC`,
          inline: true
        },
        {
          name: '🎫 Tickets',
          value: `${tickets}`,
          inline: true
        },
        {
          name: '📊 Total gagné (vie)',
          value: `${totalEarned.toLocaleString()} GC`,
          inline: false
        }
      )
      .setTimestamp();

    await interaction.editReply({ embeds: [embed] });

  } catch (error) {
    console.error('Erreur dans la commande /solde:', error);
    await interaction.editReply({
      content: '❌ Une erreur est survenue lors de la récupération du solde.',
      ephemeral: true,
    });
  }
}

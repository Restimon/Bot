import { SlashCommandBuilder, PermissionFlagsBits } from 'discord.js';
import { Guild } from '../database/models/Guild.js';

export const data = new SlashCommandBuilder()
  .setName('welcome')
  .setNameLocalizations({ fr: 'bienvenue' })
  .setDescription('Configure le système de bienvenue du serveur')
  .setDefaultMemberPermissions(PermissionFlagsBits.Administrator)
  .addSubcommand(subcommand =>
    subcommand
      .setName('activer')
      .setDescription('Active le système de bienvenue')
      .addChannelOption(option =>
        option
          .setName('salon')
          .setDescription('Le salon où envoyer les messages de bienvenue')
          .setRequired(true)
      )
  )
  .addSubcommand(subcommand =>
    subcommand
      .setName('desactiver')
      .setDescription('Désactive le système de bienvenue')
  )
  .addSubcommand(subcommand =>
    subcommand
      .setName('message')
      .setDescription('Définit le message de bienvenue personnalisé')
      .addStringOption(option =>
        option
          .setName('texte')
          .setDescription('Le message (utilisez {user}, {server}, {username} comme variables)')
          .setRequired(true)
      )
  )
  .addSubcommand(subcommand =>
    subcommand
      .setName('info')
      .setDescription('Affiche la configuration actuelle du système de bienvenue')
  );

export async function execute(interaction) {
  const subcommand = interaction.options.getSubcommand();

  try {
    let guildConfig = await Guild.findOne({ guildId: interaction.guild.id });

    if (!guildConfig) {
      guildConfig = await Guild.create({
        guildId: interaction.guild.id,
        guildName: interaction.guild.name,
      });
    }

    switch (subcommand) {
      case 'activer': {
        const channel = interaction.options.getChannel('salon');

        guildConfig.welcome.enabled = true;
        guildConfig.welcome.channelId = channel.id;
        guildConfig.lastUpdated = new Date();
        await guildConfig.save();

        await interaction.reply({
          content: `✅ Système de bienvenue activé dans ${channel} !`,
          ephemeral: true,
        });
        break;
      }

      case 'desactiver': {
        guildConfig.welcome.enabled = false;
        guildConfig.lastUpdated = new Date();
        await guildConfig.save();

        await interaction.reply({
          content: '✅ Système de bienvenue désactivé.',
          ephemeral: true,
        });
        break;
      }

      case 'message': {
        const messageText = interaction.options.getString('texte');

        guildConfig.welcome.message = messageText;
        guildConfig.lastUpdated = new Date();
        await guildConfig.save();

        await interaction.reply({
          content: `✅ Message de bienvenue mis à jour :\n\`\`\`${messageText}\`\`\`\n*Variables disponibles: {user}, {server}, {username}*`,
          ephemeral: true,
        });
        break;
      }

      case 'info': {
        const status = guildConfig.welcome.enabled ? '✅ Activé' : '❌ Désactivé';
        const channel = guildConfig.welcome.channelId
          ? `<#${guildConfig.welcome.channelId}>`
          : '*Non configuré*';

        await interaction.reply({
          content: [
            '**📋 Configuration du système de bienvenue**',
            `**Statut:** ${status}`,
            `**Salon:** ${channel}`,
            `**Message:**\n\`\`\`${guildConfig.welcome.message}\`\`\``,
          ].join('\n'),
          ephemeral: true,
        });
        break;
      }
    }

  } catch (error) {
    console.error('Erreur dans la commande /welcome:', error);
    await interaction.reply({
      content: '❌ Une erreur est survenue lors de la configuration.',
      ephemeral: true,
    });
  }
}

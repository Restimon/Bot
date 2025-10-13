import { Events, EmbedBuilder } from 'discord.js';
import { Guild } from '../database/models/Guild.js';
import { Player } from '../database/models/Player.js';
import { generateWelcomeMessage } from '../utils/openai.js';

export const name = Events.GuildMemberAdd;

export async function execute(member) {
  try {
    // Créer le profil du joueur
    await Player.findOneAndUpdate(
      { userId: member.id },
      {
        userId: member.id,
        username: member.user.username,
        lastUpdated: new Date(),
      },
      { upsert: true, new: true }
    );

    // Vérifier la configuration du serveur
    const guildConfig = await Guild.findOne({ guildId: member.guild.id });

    if (!guildConfig || !guildConfig.welcome.enabled || !guildConfig.welcome.channelId) {
      return;
    }

    const channel = member.guild.channels.cache.get(guildConfig.welcome.channelId);

    if (!channel) {
      console.error(`Salon de bienvenue non trouvé: ${guildConfig.welcome.channelId}`);
      return;
    }

    // Générer le message avec OpenAI
    const welcomeText = await generateWelcomeMessage(member, guildConfig.welcome.message);

    // Créer l'embed de bienvenue
    const embed = new EmbedBuilder()
      .setColor('#57F287')
      .setTitle('🎉 Nouveau membre !')
      .setDescription(welcomeText)
      .setThumbnail(member.user.displayAvatarURL({ dynamic: true }))
      .addFields(
        {
          name: '👤 Membre',
          value: `${member.user.tag}`,
          inline: true,
        },
        {
          name: '📊 Membre n°',
          value: `${member.guild.memberCount}`,
          inline: true,
        }
      )
      .setFooter({
        text: `Arrivé le ${new Date().toLocaleDateString('fr-FR')}`,
      })
      .setTimestamp();

    await channel.send({ embeds: [embed] });

  } catch (error) {
    console.error('Erreur lors de l\'arrivée d\'un membre:', error);
  }
}

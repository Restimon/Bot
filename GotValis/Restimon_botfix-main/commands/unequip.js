import { SlashCommandBuilder, EmbedBuilder } from 'discord.js';
import { Player } from '../database/models/Player.js';
import { getCharacterById } from '../data/characters.js';

export const data = new SlashCommandBuilder()
  .setName('unequip')
  .setNameLocalizations({ fr: 'déséquiper' })
  .setDescription('Retirez votre personnage équipé (cooldown: 1 heure)');

const UNEQUIP_COOLDOWN = 60 * 60 * 1000; // 1 hour in milliseconds

export async function execute(interaction) {
  await interaction.deferReply();

  try {
    const player = await Player.findOne({ userId: interaction.user.id });

    if (!player) {
      return await interaction.editReply({
        content: '❌ Profil non trouvé.',
        ephemeral: true,
      });
    }

    // Check if player has a character equipped
    if (!player.equippedCharacter || !player.equippedCharacter.characterId) {
      return await interaction.editReply({
        content: '❌ Vous n\'avez aucun personnage équipé.',
        ephemeral: true,
      });
    }

    // Check cooldown
    if (player.lastUnequip) {
      const timeSinceLastUnequip = Date.now() - player.lastUnequip.getTime();
      const timeRemaining = UNEQUIP_COOLDOWN - timeSinceLastUnequip;

      if (timeRemaining > 0) {
        const minutesRemaining = Math.ceil(timeRemaining / (1000 * 60));

        return await interaction.editReply({
          content: `⏰ Vous devez attendre encore **${minutesRemaining} minute(s)** avant de pouvoir déséquiper un personnage.`,
          ephemeral: true,
        });
      }
    }

    // Get character info before unequipping
    const character = getCharacterById(player.equippedCharacter.characterId);
    const characterName = character ? character.name : 'Personnage inconnu';

    // Unequip character
    player.equippedCharacter = {
      characterId: null,
      equippedAt: null,
    };
    player.lastUnequip = new Date();
    player.lastUpdated = new Date();
    await player.save();

    const embed = new EmbedBuilder()
      .setColor('#95A5A6')
      .setTitle('✅ Personnage déséquipé')
      .setDescription(`Vous avez retiré **${characterName}**.`)
      .setFooter({ text: 'Vous pouvez équiper un nouveau personnage avec /equip' })
      .setTimestamp();

    await interaction.editReply({ embeds: [embed] });

  } catch (error) {
    console.error('Error in /unequip command:', error);
    await interaction.editReply({
      content: '❌ Une erreur est survenue lors du retrait du personnage.',
      ephemeral: true,
    });
  }
}

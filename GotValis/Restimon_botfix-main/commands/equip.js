import { SlashCommandBuilder, EmbedBuilder } from 'discord.js';
import { Player } from '../database/models/Player.js';
import { getCharacterById, getRarityInfo } from '../data/characters.js';

export const data = new SlashCommandBuilder()
  .setName('equip')
  .setNameLocalizations({ fr: 'équiper' })
  .setDescription('Équipez un personnage de votre collection')
  .addStringOption(option =>
    option
      .setName('personnage')
      .setDescription('ID ou nom du personnage à équiper')
      .setRequired(true)
      .setAutocomplete(true)
  );

export async function autocomplete(interaction) {
  const focusedValue = interaction.options.getFocused().toLowerCase();

  try {
    const player = await Player.findOne({ userId: interaction.user.id });

    if (!player || !player.characterCollection || player.characterCollection.length === 0) {
      return await interaction.respond([]);
    }

    const choices = player.characterCollection.map(c => {
      const char = getCharacterById(c.characterId);
      return char ? {
        name: `${char.name} (${char.rarity})`,
        value: char.id,
      } : null;
    }).filter(c => c !== null);

    const filtered = choices.filter(choice =>
      choice.name.toLowerCase().includes(focusedValue)
    ).slice(0, 25);

    await interaction.respond(filtered);
  } catch (error) {
    console.error('Error in autocomplete:', error);
    await interaction.respond([]);
  }
}

export async function execute(interaction) {
  await interaction.deferReply();

  const characterInput = interaction.options.getString('personnage');

  try {
    const player = await Player.findOne({ userId: interaction.user.id });

    if (!player) {
      return await interaction.editReply({
        content: '❌ Profil non trouvé. Utilisez `/summon` pour obtenir votre premier personnage !',
        ephemeral: true,
      });
    }

    // Find character by ID or name
    const character = getCharacterById(characterInput);

    if (!character) {
      return await interaction.editReply({
        content: '❌ Personnage non trouvé.',
        ephemeral: true,
      });
    }

    // Check if player owns this character
    const ownedChar = player.characterCollection.find(c => c.characterId === character.id);

    if (!ownedChar) {
      return await interaction.editReply({
        content: `❌ Vous ne possédez pas **${character.name}**. Utilisez \`/summon\` pour l'obtenir !`,
        ephemeral: true,
      });
    }

    // Equip the character
    player.equippedCharacter = {
      characterId: character.id,
      equippedAt: new Date(),
    };
    player.lastUpdated = new Date();
    await player.save();

    const rarityInfo = getRarityInfo(character.rarity);

    const embed = new EmbedBuilder()
      .setColor(rarityInfo.color)
      .setTitle('✅ Personnage équipé !')
      .setDescription(
        `Vous avez équipé **${character.name}** ${rarityInfo.emoji}\n\n` +
        `**${character.passive}**\n${character.passiveDescription}`
      )
      .addFields(
        {
          name: 'Rareté',
          value: rarityInfo.name,
          inline: true,
        },
        {
          name: 'Faction',
          value: character.faction,
          inline: true,
        }
      )
      .setFooter({ text: 'Utilisez /unequip pour retirer votre personnage (cooldown: 1h)' })
      .setTimestamp();

    await interaction.editReply({ embeds: [embed] });

  } catch (error) {
    console.error('Error in /equip command:', error);
    await interaction.editReply({
      content: '❌ Une erreur est survenue lors de l\'équipement du personnage.',
      ephemeral: true,
    });
  }
}

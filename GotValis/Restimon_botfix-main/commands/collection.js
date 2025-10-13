import { SlashCommandBuilder, EmbedBuilder } from 'discord.js';
import { Player } from '../database/models/Player.js';
import { getCharacterById, getRarityInfo } from '../data/characters.js';

export const data = new SlashCommandBuilder()
  .setName('collection')
  .setNameLocalizations({ fr: 'collection' })
  .setDescription('Affiche votre collection de personnages')
  .addUserOption(option =>
    option
      .setName('joueur')
      .setDescription('Le joueur dont vous voulez voir la collection')
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

    if (!player.characterCollection || player.characterCollection.length === 0) {
      return await interaction.editReply({
        content: `${targetUser.username} n'a aucun personnage dans sa collection.`,
        ephemeral: false,
      });
    }

    // Build collection display
    let collectionText = '';
    let totalCharacters = 0;

    for (const entry of player.characterCollection) {
      const character = getCharacterById(entry.characterId);
      if (!character) continue;

      const rarity = getRarityInfo(character.rarity);
      const isEquipped = player.equippedCharacter?.characterId === entry.characterId;
      const equippedMark = isEquipped ? ' ⚡ **[Équipé]**' : '';
      const duplicateMark = entry.count > 1 ? ` *x${entry.count}*` : '';

      collectionText += `${rarity.emoji} **${character.name}**${duplicateMark}${equippedMark}\n`;
      collectionText += `└ *${character.faction}* • ${character.passive}\n\n`;

      totalCharacters += entry.count;
    }

    const embed = new EmbedBuilder()
      .setColor('#5865F2')
      .setTitle(`🎴 Collection — ${targetUser.username}`)
      .setDescription(collectionText || '*Collection vide*')
      .setFooter({ text: `Total: ${totalCharacters} personnage(s)` })
      .setThumbnail(targetUser.displayAvatarURL({ dynamic: true }))
      .setTimestamp();

    await interaction.editReply({ embeds: [embed] });

  } catch (error) {
    console.error('Erreur dans la commande /collection:', error);
    await interaction.editReply({
      content: '❌ Une erreur est survenue lors de la récupération de la collection.',
      ephemeral: true,
    });
  }
}

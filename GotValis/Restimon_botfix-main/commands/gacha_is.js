import { SlashCommandBuilder, EmbedBuilder } from 'discord.js';
import { Player } from '../database/models/Player.js';
import { getCharacterById, getRarityInfo } from '../data/characters.js';

export const data = new SlashCommandBuilder()
  .setName('gacha_is')
  .setNameLocalizations({ fr: 'gacha_is' })
  .setDescription('Affiche le personnage actuellement équipé')
  .addUserOption(option =>
    option
      .setName('joueur')
      .setDescription('Le joueur dont vous voulez voir le personnage équipé')
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

    if (!player.equippedCharacter || !player.equippedCharacter.characterId) {
      return await interaction.editReply({
        content: `${targetUser.username} n'a aucun personnage équipé.`,
        ephemeral: false,
      });
    }

    const character = getCharacterById(player.equippedCharacter.characterId);

    if (!character) {
      return await interaction.editReply({
        content: `❌ Personnage introuvable (ID: ${player.equippedCharacter.characterId})`,
        ephemeral: true,
      });
    }

    const rarity = getRarityInfo(character.rarity);
    const equippedDate = player.equippedCharacter.equippedAt
      ? new Date(player.equippedCharacter.equippedAt).toLocaleString('fr-FR')
      : 'Date inconnue';

    const embed = new EmbedBuilder()
      .setColor(rarity.color)
      .setTitle(`⚡ Personnage Équipé — ${targetUser.username}`)
      .setThumbnail(character.image || targetUser.displayAvatarURL({ dynamic: true }))
      .addFields(
        {
          name: `${rarity.emoji} ${character.name}`,
          value: `**Rareté**: ${rarity.name}\n**Faction**: ${character.faction}`,
          inline: false
        },
        {
          name: '📖 Description',
          value: character.description,
          inline: false
        },
        {
          name: `📜 Passif: ${character.passive}`,
          value: character.passiveDescription,
          inline: false
        },
        {
          name: '📅 Équipé le',
          value: equippedDate,
          inline: false
        }
      )
      .setTimestamp();

    await interaction.editReply({ embeds: [embed] });

  } catch (error) {
    console.error('Erreur dans la commande /gacha_is:', error);
    await interaction.editReply({
      content: '❌ Une erreur est survenue lors de la récupération du personnage équipé.',
      ephemeral: true,
    });
  }
}

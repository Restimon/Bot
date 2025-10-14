import { SlashCommandBuilder, EmbedBuilder, AttachmentBuilder } from 'discord.js';
import { Player } from '../database/models/Player.js';
import { summonCharacter, getRarityInfo } from '../data/characters.js';

export const data = new SlashCommandBuilder()
  .setName('summon')
  .setNameLocalizations({ fr: 'invocation' })
  .setDescription('Invoquez un personnage avec vos tickets')
  .addIntegerOption(option =>
    option
      .setName('nombre')
      .setDescription('Nombre de tickets à utiliser (défaut: 1)')
      .setMinValue(1)
      .setMaxValue(10)
      .setRequired(false)
  );

export async function execute(interaction) {
  await interaction.deferReply();

  const amount = interaction.options.getInteger('nombre') || 1;

  try {
    // Get player
    let player = await Player.findOne({ userId: interaction.user.id });

    if (!player) {
      player = await Player.create({
        userId: interaction.user.id,
        username: interaction.user.username,
      });
    }

    // Check if player has enough tickets
    if ((player.tickets || 0) < amount) {
      return await interaction.editReply({
        content: `❌ Vous n'avez pas assez de tickets. Vous avez **${player.tickets || 0}** ticket(s), mais vous en avez besoin de **${amount}**.`,
        ephemeral: true,
      });
    }

    // Perform summons
    const summonedCharacters = [];
    const newCharacters = [];

    for (let i = 0; i < amount; i++) {
      const character = summonCharacter();
      summonedCharacters.push(character);

      // Check if character already in collection
      const existingChar = player.characterCollection.find(c => c.characterId === character.id);

      if (existingChar) {
        existingChar.count += 1;
      } else {
        player.characterCollection.push({
          characterId: character.id,
          obtainedAt: new Date(),
          count: 1,
        });
        newCharacters.push(character);
      }
    }

    // Deduct tickets
    player.tickets -= amount;
    player.lastUpdated = new Date();
    await player.save();

    // Create embeds for each summon
    if (amount === 1) {
      // Single summon - detailed view
      const character = summonedCharacters[0];
      const rarityInfo = getRarityInfo(character.rarity);
      const isNew = newCharacters.includes(character);

      const embed = new EmbedBuilder()
        .setColor(rarityInfo.color)
        .setTitle('🔮 Résultat de l\'invocation')
        .setDescription(
          `**${character.name}** — *${rarityInfo.name}* (${character.faction}) — ${isNew ? '🆕' : '♻️'}\n\n` +
          `**Description**\n${character.description}\n\n` +
          `**Capacité**\n**${character.passive}** 📜\n${character.passiveDescription}`
        )
        .addFields(
          {
            name: '🎫 Tickets',
            value: `-${amount} (reste: ${player.tickets})`,
            inline: true,
          },
          {
            name: '📚 Collection',
            value: `${player.characterCollection.length} possédé(s) (${newCharacters.length > 0 ? '+1 nouveau' : 'dup'})`,
            inline: true,
          }
        )
        .setFooter({ text: 'Équipement\n🎭 Personnage équipé inchangé.\n\nAstuce: /invocation 10 pour une multi.' })
        .setTimestamp();

      // Note: Image would be set if we had real image URLs
      // .setImage(character.image);

      await interaction.editReply({ embeds: [embed] });
    } else {
      // Multiple summons - summary view
      const rarityCount = {};
      summonedCharacters.forEach(char => {
        const rarity = char.rarity;
        rarityCount[rarity] = (rarityCount[rarity] || 0) + 1;
      });

      const summaryLines = Object.entries(rarityCount).map(([rarity, count]) => {
        const rarityInfo = getRarityInfo(rarity);
        return `${rarityInfo.emoji} **${rarityInfo.name}**: ${count}`;
      });

      const characterList = summonedCharacters.map((char, index) => {
        const rarityInfo = getRarityInfo(char.rarity);
        const isNew = newCharacters.some(nc => nc.id === char.id);
        return `${index + 1}. ${rarityInfo.emoji} ${char.name} ${isNew ? '🆕' : ''}`;
      }).join('\n');

      const embed = new EmbedBuilder()
        .setColor('#5865F2')
        .setTitle(`🔮 Résultats de l'invocation (x${amount})`)
        .setDescription(
          `**Résumé des raretés:**\n${summaryLines.join('\n')}\n\n` +
          `**Personnages obtenus:**\n${characterList}`
        )
        .addFields(
          {
            name: '🎫 Tickets',
            value: `-${amount} (reste: ${player.tickets})`,
            inline: true,
          },
          {
            name: '📚 Collection',
            value: `${player.characterCollection.length} possédé(s) (+${newCharacters.length} nouveaux)`,
            inline: true,
          }
        )
        .setFooter({ text: `${newCharacters.length} nouveau(x) personnage(s) ajouté(s) à votre collection !` })
        .setTimestamp();

      await interaction.editReply({ embeds: [embed] });
    }

  } catch (error) {
    console.error('Error in /summon command:', error);
    await interaction.editReply({
      content: '❌ Une erreur est survenue lors de l\'invocation.',
      ephemeral: true,
    });
  }
}

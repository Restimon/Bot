import { SlashCommandBuilder, EmbedBuilder } from 'discord.js';
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
    // Charger ou créer le joueur
    let player = await Player.findOne({ userId: interaction.user.id });
    if (!player) {
      player = await Player.create({
        userId: interaction.user.id,
        username: interaction.user.username,
        gachaTickets: 0,
        characterCollection: [],
      });
    }

    // Sécuriser les champs attendus
    if (!Array.isArray(player.characterCollection)) {
      player.characterCollection = [];
    }
    if (typeof player.gachaTickets !== 'number') {
      player.gachaTickets = 0;
    }

    // Vérifier les tickets
    if ((player.gachaTickets || 0) < amount) {
      return await interaction.editReply({
        content: `❌ Tickets insuffisants. Vous avez **${player.gachaTickets || 0}** ticket(s), il en faut **${amount}**.`,
        ephemeral: true,
      });
    }

    // Effectuer les invocations
    const summonedCharacters = [];
    const newCharacters = [];

    for (let i = 0; i < amount; i++) {
      const character = summonCharacter();
      summonedCharacters.push(character);

      // vérifier existant
      const existingChar = player.characterCollection.find(c => c.characterId === character.id);
      if (existingChar) {
        existingChar.count = (existingChar.count || 1) + 1;
      } else {
        player.characterCollection.push({
          characterId: character.id,
          obtainedAt: new Date(),
          count: 1,
        });
        newCharacters.push(character);
      }
    }

    // Décrémenter les tickets et sauvegarder
    player.gachaTickets -= amount;
    player.lastUpdated = new Date();
    await player.save();

    const ticketsRestants = player.gachaTickets;

    // Embeds
    if (amount === 1) {
      const character = summonedCharacters[0];
      const rarityInfo = getRarityInfo(character.rarity);
      const isNew = newCharacters.some(nc => nc.id === character.id);

      const embed = new EmbedBuilder()
        .setColor(rarityInfo.color)
        .setTitle('🔮 Résultat de l’invocation')
        .setDescription(
          `**${character.name}** — *${rarityInfo.name}* (${character.faction}) — ${isNew ? '🆕' : '♻️'}\n\n` +
          `**Description**\n${character.description}\n\n` +
          `**Capacité**\n**${character.passive}** 📜\n${character.passiveDescription}`
        )
        .addFields(
          { name: '🎫 Tickets', value: `-${amount} (reste: ${ticketsRestants})`, inline: true },
          {
            name: '📚 Collection',
            value: `${player.characterCollection.length} possédé(s) ${isNew ? '(+1 nouveau)' : '(dup)'}`,
            inline: true,
          }
        )
        .setFooter({ text: 'Astuce : /invocation 10 pour une multi.' })
        .setTimestamp();

      // .setImage(character.image) // si tu as une URL d’image

      await interaction.editReply({ embeds: [embed] });
    } else {
      // multiple
      const rarityCount = {};
      for (const ch of summonedCharacters) {
        rarityCount[ch.rarity] = (rarityCount[ch.rarity] || 0) + 1;
      }

      const summaryLines = Object.entries(rarityCount).map(([rarity, count]) => {
        const r = getRarityInfo(rarity);
        return `${r.emoji} **${r.name}**: ${count}`;
      });

      const characterList = summonedCharacters
        .map((ch, i) => {
          const r = getRarityInfo(ch.rarity);
          const isNew = newCharacters.some(nc => nc.id === ch.id);
          return `${i + 1}. ${r.emoji} ${ch.name} ${isNew ? '🆕' : ''}`;
        })
        .join('\n');

      const embed = new EmbedBuilder()
        .setColor('#5865F2')
        .setTitle(`🔮 Résultats de l’invocation (x${amount})`)
        .setDescription(
          `**Raretés:**\n${summaryLines.join('\n')}\n\n` +
          `**Personnages:**\n${characterList}`
        )
        .addFields(
          { name: '🎫 Tickets', value: `-${amount} (reste: ${ticketsRestants})`, inline: true },
          {
            name: '📚 Collection',
            value: `${player.characterCollection.length} possédé(s) (+${newCharacters.length} nouveaux)`,
            inline: true,
          }
        )
        .setFooter({ text: `${newCharacters.length} nouveau(x) personnage(s) ajouté(s) à votre collection` })
        .setTimestamp();

      await interaction.editReply({ embeds: [embed] });
    }

  } catch (error) {
    console.error('Error in /summon command:', error);
    await interaction.editReply({
      content: '❌ Une erreur est survenue lors de l’invocation.',
      ephemeral: true,
    });
  }
}

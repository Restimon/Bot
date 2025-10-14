import { SlashCommandBuilder, EmbedBuilder } from 'discord.js';
import { Player } from '../database/models/Player.js';
import { getCharacterById, getRarityInfo } from '../data/characters.js';

// Sell prices by rarity
const SELL_PRICES = {
  COMMON: 50,
  UNCOMMON: 150,
  RARE: 400,
  EPIC: 1000,
  LEGENDARY: 3000
};

export const data = new SlashCommandBuilder()
  .setName('gacha_sell')
  .setNameLocalizations({ fr: 'gacha_sell' })
  .setDescription('Vend un personnage de votre collection')
  .addStringOption(option =>
    option
      .setName('personnage')
      .setDescription('Le nom ou ID du personnage à vendre')
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

    const choices = [];
    for (const entry of player.characterCollection) {
      const character = getCharacterById(entry.characterId);
      if (!character) continue;

      // Skip equipped character
      if (player.equippedCharacter?.characterId === entry.characterId) continue;

      const rarity = getRarityInfo(character.rarity);
      const label = `${rarity.emoji} ${character.name} (${SELL_PRICES[character.rarity]} GC)`;

      if (label.toLowerCase().includes(focusedValue) || character.id.includes(focusedValue)) {
        choices.push({
          name: label,
          value: character.id
        });
      }
    }

    await interaction.respond(choices.slice(0, 25));
  } catch (error) {
    console.error('Erreur autocomplete /gacha_sell:', error);
    await interaction.respond([]);
  }
}

export async function execute(interaction) {
  await interaction.deferReply();

  const characterId = interaction.options.getString('personnage');

  try {
    const player = await Player.findOne({ userId: interaction.user.id });

    if (!player) {
      return await interaction.editReply({
        content: `❌ Profil non trouvé.`,
        ephemeral: true,
      });
    }

    // Check if player owns the character
    const collectionEntry = player.characterCollection.find(
      c => c.characterId === characterId
    );

    if (!collectionEntry) {
      return await interaction.editReply({
        content: `❌ Vous ne possédez pas ce personnage.`,
        ephemeral: true,
      });
    }

    // Check if character is equipped
    if (player.equippedCharacter?.characterId === characterId) {
      return await interaction.editReply({
        content: `❌ Vous ne pouvez pas vendre un personnage équipé. Déséquipez-le d'abord avec \`/unequip\`.`,
        ephemeral: true,
      });
    }

    const character = getCharacterById(characterId);
    if (!character) {
      return await interaction.editReply({
        content: `❌ Personnage introuvable.`,
        ephemeral: true,
      });
    }

    const sellPrice = SELL_PRICES[character.rarity] || 50;
    const rarity = getRarityInfo(character.rarity);

    // Remove one instance of the character
    if (collectionEntry.count > 1) {
      collectionEntry.count -= 1;
      await player.save();
    } else {
      player.characterCollection = player.characterCollection.filter(
        c => c.characterId !== characterId
      );
      await player.save();
    }

    // Add coins to player
    player.economy.coins += sellPrice;
    await player.save();

    const embed = new EmbedBuilder()
      .setColor(rarity.color)
      .setTitle('💰 Personnage Vendu')
      .setDescription(
        `Vous avez vendu **${rarity.emoji} ${character.name}** pour **${sellPrice} GC**.\n\n` +
        `Solde actuel: **${player.economy.coins} GC**`
      )
      .setThumbnail(character.image || interaction.user.displayAvatarURL({ dynamic: true }))
      .setTimestamp();

    await interaction.editReply({ embeds: [embed] });

  } catch (error) {
    console.error('Erreur dans la commande /gacha_sell:', error);
    await interaction.editReply({
      content: '❌ Une erreur est survenue lors de la vente du personnage.',
      ephemeral: true,
    });
  }
}

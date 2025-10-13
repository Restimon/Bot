import { SlashCommandBuilder, EmbedBuilder } from 'discord.js';
import { Player } from '../database/models/Player.js';
import { applyHealing, addShield } from '../utils/combat.js';
import { COLORS } from '../utils/colors.js';

export const data = new SlashCommandBuilder()
  .setName('use')
  .setNameLocalizations({ fr: 'utiliser' })
  .setDescription('Utilise un objet utilitaire')
  .addStringOption(option =>
    option
      .setName('objet')
      .setDescription('L\'objet à utiliser (emoji)')
      .setRequired(true)
      .setAutocomplete(true)
  )
  .addUserOption(option =>
    option
      .setName('cible')
      .setDescription('La cible de l\'objet (vous par défaut)')
      .setRequired(false)
  );

// Utility items with their effects
const UTILITY_ITEMS = {
  '🛡️': {
    name: 'Bouclier',
    type: 'shield',
    value: 20,
    description: 'bouclier de protection',
    action: 'a activé un',
    result: (user, hp, shield) => `En équipant l'armure, ${user} le porteur passe à → ${hp} ❤️ | ${shield} 🛡`
  },
  '💖': {
    name: 'Cœur',
    type: 'heal',
    value: 15,
    description: 'cœur régénérateur',
    action: 'a utilisé un',
    result: (user, hp, shield) => `${user} récupère de la vie → ${hp} ❤️ | ${shield} 🛡`
  },
  '🍎': {
    name: 'Pomme',
    type: 'heal',
    value: 10,
    description: 'pomme',
    action: 'a mangé une',
    result: (user, hp, shield) => `${user} se restaure → ${hp} ❤️ | ${shield} 🛡`
  },
  '🍖': {
    name: 'Viande',
    type: 'heal',
    value: 20,
    description: 'viande',
    action: 'a consommé de la',
    result: (user, hp, shield) => `${user} récupère des forces → ${hp} ❤️ | ${shield} 🛡`
  },
  '🧪': {
    name: 'Potion',
    type: 'heal',
    value: 25,
    description: 'potion de soin',
    action: 'a bu une',
    result: (user, hp, shield) => `${user} se soigne → ${hp} ❤️ | ${shield} 🛡`
  },
  '⚙️': {
    name: 'Engrenage',
    type: 'shield',
    value: 15,
    description: 'engrenage mécanique',
    action: 'a activé un',
    result: (user, hp, shield) => `${user} renforce sa défense → ${hp} ❤️ | ${shield} 🛡`
  },
  '💡': {
    name: 'Ampoule',
    type: 'heal',
    value: 5,
    description: 'ampoule énergétique',
    action: 'a utilisé une',
    result: (user, hp, shield) => `${user} gagne un peu d'énergie → ${hp} ❤️ | ${shield} 🛡`
  },
};

export async function autocomplete(interaction) {
  const focusedValue = interaction.options.getFocused().toLowerCase();

  try {
    const player = await Player.findOne({ userId: interaction.user.id });

    if (!player || !player.inventory || player.inventory.length === 0) {
      return await interaction.respond([]);
    }

    // Find utility items in inventory
    const utilityItems = player.inventory.filter(item => {
      const emojiMatch = item.itemName.match(/[\p{Emoji}]/u);
      const emoji = emojiMatch ? emojiMatch[0] : null;
      return emoji && UTILITY_ITEMS[emoji];
    });

    // Create unique list
    const uniqueItems = {};
    utilityItems.forEach(item => {
      const emojiMatch = item.itemName.match(/[\p{Emoji}]/u);
      const emoji = emojiMatch ? emojiMatch[0] : null;
      if (emoji && UTILITY_ITEMS[emoji]) {
        uniqueItems[emoji] = (uniqueItems[emoji] || 0) + 1;
      }
    });

    const choices = Object.entries(uniqueItems).map(([emoji, count]) => ({
      name: `${emoji} ${UTILITY_ITEMS[emoji].name} (x${count})`,
      value: emoji,
    }));

    const filtered = choices.filter(choice =>
      choice.name.toLowerCase().includes(focusedValue)
    ).slice(0, 25);

    await interaction.respond(filtered);
  } catch (error) {
    console.error('Error in /use autocomplete:', error);
    await interaction.respond([]);
  }
}

export async function execute(interaction) {
  await interaction.deferReply();

  const itemEmoji = interaction.options.getString('objet');
  const targetUser = interaction.options.getUser('cible') || interaction.user;

  try {
    const player = await Player.findOne({ userId: interaction.user.id });

    if (!player) {
      return await interaction.editReply({
        content: '❌ Profil non trouvé.',
        ephemeral: true,
      });
    }

    // Check if item is a valid utility item
    const utilityItem = UTILITY_ITEMS[itemEmoji];

    if (!utilityItem) {
      return await interaction.editReply({
        content: '❌ Cet objet n\'est pas un objet utilitaire.',
        ephemeral: true,
      });
    }

    // Find item in inventory
    const itemIndex = player.inventory.findIndex(item => {
      const emojiMatch = item.itemName.match(/[\p{Emoji}]/u);
      return emojiMatch && emojiMatch[0] === itemEmoji;
    });

    if (itemIndex === -1) {
      return await interaction.editReply({
        content: `❌ Vous ne possédez pas cet objet: ${itemEmoji} ${utilityItem.name}`,
        ephemeral: true,
      });
    }

    // Remove item from inventory
    player.inventory.splice(itemIndex, 1);
    await player.save();

    // Apply effect based on item type
    let result;
    let targetPlayer = await Player.findOne({ userId: targetUser.id });

    if (!targetPlayer) {
      targetPlayer = await Player.create({
        userId: targetUser.id,
        username: targetUser.username,
      });
    }

    if (utilityItem.type === 'heal') {
      result = await applyHealing(targetUser.id, utilityItem.value, interaction.user.id);
    } else if (utilityItem.type === 'shield') {
      result = await addShield(targetUser.id, utilityItem.value);
    }

    // Reload target player to get updated stats
    targetPlayer = await Player.findOne({ userId: targetUser.id });

    const hp = targetPlayer.combat.hp;
    const shield = targetPlayer.combat.shield;

    // Create embed
    const embed = new EmbedBuilder()
      .setColor(COLORS.COMBAT_UTILITY)
      .setTitle(`🛡️ Action de ${interaction.user.username}`)
      .setDescription(
        `<@${targetUser.id}> ${utilityItem.action} **${utilityItem.description}** !\n\n` +
        utilityItem.result(`<@${targetUser.id}>`, hp, shield)
      )
      .setTimestamp();

    await interaction.editReply({ embeds: [embed] });

  } catch (error) {
    console.error('Error in /use command:', error);
    await interaction.editReply({
      content: '❌ Une erreur est survenue lors de l\'utilisation de l\'objet.',
      ephemeral: true,
    });
  }
}

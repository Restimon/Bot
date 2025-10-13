import { SlashCommandBuilder, EmbedBuilder, AttachmentBuilder } from 'discord.js';
import { Player } from '../database/models/Player.js';
import { applyHealing, addShield } from '../utils/combat.js';
import { HEALING_ITEMS, SHIELD_ITEMS, getHealingItem } from '../data/healingItems.js';
import { isStatusEffectItem, getStatusEffectByItem, STATUS_EFFECT_ITEMS } from '../data/statusEffects.js';
import { applyStatusEffect } from '../utils/statusEffects.js';
import { COLORS } from '../utils/colors.js';

export const data = new SlashCommandBuilder()
  .setName('heal')
  .setNameLocalizations({ fr: 'soigner' })
  .setDescription('Soigne un joueur avec un objet de soin')
  .addStringOption(option =>
    option
      .setName('objet')
      .setDescription('L\'objet de soin à utiliser (emoji)')
      .setRequired(true)
      .setAutocomplete(true)
  )
  .addUserOption(option =>
    option
      .setName('cible')
      .setDescription('Le joueur à soigner (vous par défaut)')
      .setRequired(false)
  );

export async function autocomplete(interaction) {
  const focusedValue = interaction.options.getFocused().toLowerCase();

  try {
    const player = await Player.findOne({ userId: interaction.user.id });

    if (!player || !player.inventory || player.inventory.length === 0) {
      return await interaction.respond([]);
    }

    // Find healing items in inventory
    const healingItems = player.inventory.filter(item => {
      const emojiMatch = item.itemName.match(/[\p{Emoji}]/u);
      const emoji = emojiMatch ? emojiMatch[0] : null;
      return emoji && getHealingItem(emoji);
    });

    // Create unique list
    const uniqueItems = {};
    healingItems.forEach(item => {
      const emojiMatch = item.itemName.match(/[\p{Emoji}]/u);
      const emoji = emojiMatch ? emojiMatch[0] : null;
      if (emoji && getHealingItem(emoji)) {
        uniqueItems[emoji] = (uniqueItems[emoji] || 0) + 1;
      }
    });

    const choices = Object.entries(uniqueItems).map(([emoji, count]) => {
      const itemData = getHealingItem(emoji);
      return {
        name: `${emoji} ${itemData.name} (x${count})`,
        value: emoji,
      };
    });

    const filtered = choices.filter(choice =>
      choice.name.toLowerCase().includes(focusedValue)
    ).slice(0, 25);

    await interaction.respond(filtered);
  } catch (error) {
    console.error('Error in /heal autocomplete:', error);
    await interaction.respond([]);
  }
}

export async function execute(interaction) {
  await interaction.deferReply();

  const itemEmoji = interaction.options.getString('objet');
  const targetUser = interaction.options.getUser('cible') || interaction.user;
  const healerUser = interaction.user;

  try {
    // Get healer
    const healer = await Player.findOne({ userId: healerUser.id });
    if (!healer) {
      return await interaction.editReply({
        content: '❌ Profil non trouvé.',
        ephemeral: true,
      });
    }

    // Check if item is valid healing item
    const healingItem = getHealingItem(itemEmoji);
    if (!healingItem) {
      return await interaction.editReply({
        content: '❌ Cet objet n\'est pas un objet de soin.',
        ephemeral: true,
      });
    }

    // Find item in inventory
    const itemIndex = healer.inventory.findIndex(item => {
      const emojiMatch = item.itemName.match(/[\p{Emoji}]/u);
      return emojiMatch && emojiMatch[0] === itemEmoji;
    });

    if (itemIndex === -1) {
      return await interaction.editReply({
        content: `❌ Vous ne possédez pas cet objet: ${itemEmoji} ${healingItem.name}`,
        ephemeral: true,
      });
    }

    // Get or create target
    let target = await Player.findOne({ userId: targetUser.id });
    if (!target) {
      target = await Player.create({
        userId: targetUser.id,
        username: targetUser.username,
      });
    }

    // Check if target is KO
    if (target.combat.isKO) {
      return await interaction.editReply({
        content: `❌ <@${targetUser.id}> est KO ! Utilisez une revive au lieu d'un soin.`,
        ephemeral: true,
      });
    }

    // Remove item from healer's inventory
    healer.inventory.splice(itemIndex, 1);
    await healer.save();

    // Store initial HP/shield for calculation
    const initialHP = target.combat.hp;
    const initialShield = target.combat.shield;
    const maxHP = target.combat.maxHp;

    let result;
    let actionText;
    let calculationText;

    // Apply healing or shield
    if (healingItem.type === 'instant') {
      result = await applyHealing(targetUser.id, healingItem.healAmount, healerUser.id);

      // Check if target is at max HP
      if (result.healAmount === 0) {
        return await interaction.editReply({
          content: `❌ <@${targetUser.id}> est déjà à HP max (${maxHP} ❤️) !`,
          ephemeral: true,
        });
      }

      const finalHP = result.currentHP;

      // Format: @User heals @Target for 10 ❤️. 86 ❤️ + 10 ❤️ = 96 ❤️
      if (targetUser.id === healerUser.id) {
        actionText = `<@${healerUser.id}> rend **10 PV** à <@${targetUser.id}> avec 🩹.`;
      } else {
        actionText = `<@${healerUser.id}> rend **${result.healAmount} PV** à <@${targetUser.id}> avec 🩹.`;
      }

      calculationText = `❤️ **${initialHP}/100** + **(${result.healAmount})** = ❤️ **${finalHP}/100**`;

    } else if (healingItem.type === 'shield') {
      result = await addShield(targetUser.id, healingItem.shieldAmount);

      if (result.shieldAdded === 0) {
        return await interaction.editReply({
          content: `❌ <@${targetUser.id}> a déjà le bouclier au max !`,
          ephemeral: true,
        });
      }

      const finalShield = result.currentShield;

      if (targetUser.id === healerUser.id) {
        actionText = `<@${healerUser.id}> s'équipe d'un bouclier.`;
      } else {
        actionText = `<@${healerUser.id}> équipe <@${targetUser.id}> d'un bouclier.`;
      }

      calculationText = `🛡️ **${initialShield}** + **(${result.shieldAdded})** = 🛡️ **${finalShield}**`;
    }

    // Apply status effect if item applies one (e.g., regeneration)
    let statusEffectApplied = null;
    if (isStatusEffectItem(itemEmoji)) {
      const statusEffectData = getStatusEffectByItem(itemEmoji);
      if (statusEffectData && statusEffectData.type === 'heal') {
        const effectResult = await applyStatusEffect(
          targetUser.id,
          STATUS_EFFECT_ITEMS[itemEmoji],
          interaction.channelId,
          interaction.guildId,
          healerUser.id
        );
        if (effectResult.success) {
          statusEffectApplied = {
            name: statusEffectData.name,
            emoji: statusEffectData.emoji,
            duration: statusEffectData.duration,
            refreshed: effectResult.refreshed,
          };
        }
      }
    }

    // Build description with status effect if applicable
    let description = `${actionText}\n${calculationText}`;
    if (statusEffectApplied) {
      const minutes = Math.floor(statusEffectApplied.duration / 60);
      if (statusEffectApplied.refreshed) {
        description += `\n\n${statusEffectApplied.emoji} **${statusEffectApplied.name} renouvelé !** (${minutes} min)`;
      } else {
        description += `\n\n${statusEffectApplied.emoji} **${statusEffectApplied.name} appliqué !** (${minutes} min)`;
      }
    }

    const embed = new EmbedBuilder()
      .setColor(COLORS.COMBAT_HEAL)
      .setTitle('💊 Soin')
      .setDescription(description)
      .setTimestamp();

    // Add healing image if available (optional)
    // You can add an image attachment here if desired
    // const attachment = new AttachmentBuilder('path/to/healing-image.png');

    await interaction.editReply({ embeds: [embed] });

  } catch (error) {
    console.error('Error in /heal command:', error);
    await interaction.editReply({
      content: '❌ Une erreur est survenue lors du soin.',
      ephemeral: true,
    });
  }
}

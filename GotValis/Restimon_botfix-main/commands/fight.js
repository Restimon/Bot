import { SlashCommandBuilder, EmbedBuilder } from 'discord.js';
import { Player } from '../database/models/Player.js';
import { applyDamage } from '../utils/combat.js';
import { OFFENSIVE_ITEMS, STATUS_EFFECT_EMOJIS, STATUS_EFFECT_REDUCTION } from '../data/offensiveItems.js';
import { isStatusEffectItem, getStatusEffectByItem, STATUS_EFFECT_ITEMS } from '../data/statusEffects.js';
import { applyStatusEffect } from '../utils/statusEffects.js';
import { COLORS } from '../utils/colors.js';

export const data = new SlashCommandBuilder()
  .setName('fight')
  .setNameLocalizations({ fr: 'combattre' })
  .setDescription('Attaque un autre joueur avec un objet offensif')
  .addUserOption(option =>
    option
      .setName('cible')
      .setDescription('Le joueur à attaquer')
      .setRequired(true)
  )
  .addStringOption(option =>
    option
      .setName('objet')
      .setDescription('L\'objet offensif à utiliser (emoji)')
      .setRequired(true)
      .setAutocomplete(true)
  );

export async function autocomplete(interaction) {
  const focusedValue = interaction.options.getFocused().toLowerCase();

  try {
    const player = await Player.findOne({ userId: interaction.user.id });

    if (!player || !player.inventory || player.inventory.length === 0) {
      return await interaction.respond([]);
    }

    // Find offensive items in inventory
    const offensiveItems = player.inventory.filter(item => {
      const emojiMatch = item.itemName.match(/[\p{Emoji}]/u);
      const emoji = emojiMatch ? emojiMatch[0] : null;
      return emoji && OFFENSIVE_ITEMS[emoji];
    });

    // Create unique list
    const uniqueItems = {};
    offensiveItems.forEach(item => {
      const emojiMatch = item.itemName.match(/[\p{Emoji}]/u);
      const emoji = emojiMatch ? emojiMatch[0] : null;
      if (emoji && OFFENSIVE_ITEMS[emoji]) {
        uniqueItems[emoji] = (uniqueItems[emoji] || 0) + 1;
      }
    });

    const choices = Object.entries(uniqueItems).map(([emoji, count]) => ({
      name: `${emoji} ${OFFENSIVE_ITEMS[emoji].name} (x${count})`,
      value: emoji,
    }));

    const filtered = choices.filter(choice =>
      choice.name.toLowerCase().includes(focusedValue)
    ).slice(0, 25);

    await interaction.respond(filtered);
  } catch (error) {
    console.error('Error in /fight autocomplete:', error);
    await interaction.respond([]);
  }
}

export async function execute(interaction) {
  await interaction.deferReply();

  const targetUser = interaction.options.getUser('cible');
  const itemEmoji = interaction.options.getString('objet');
  const attackerUser = interaction.user;

  try {
    // Check if attacking self
    if (targetUser.id === attackerUser.id) {
      return await interaction.editReply({
        content: '❌ Vous ne pouvez pas vous attaquer vous-même !',
        ephemeral: true,
      });
    }

    // Check if target is a bot (except GotValis)
    if (targetUser.bot && targetUser.id !== interaction.client.user.id) {
      return await interaction.editReply({
        content: '❌ Vous ne pouvez pas attaquer ce bot !',
        ephemeral: true,
      });
    }

    // Get attacker
    const attacker = await Player.findOne({ userId: attackerUser.id });
    if (!attacker) {
      return await interaction.editReply({
        content: '❌ Profil non trouvé.',
        ephemeral: true,
      });
    }

    // Check if attacker is KO
    if (attacker.combat.isKO) {
      return await interaction.editReply({
        content: '❌ Vous êtes KO ! Vous ne pouvez pas attaquer.',
        ephemeral: true,
      });
    }

    // Check if item is valid offensive item
    const offensiveItem = OFFENSIVE_ITEMS[itemEmoji];
    if (!offensiveItem) {
      return await interaction.editReply({
        content: '❌ Cet objet n\'est pas un objet offensif.',
        ephemeral: true,
      });
    }

    // Find item in inventory
    const itemIndex = attacker.inventory.findIndex(item => {
      const emojiMatch = item.itemName.match(/[\p{Emoji}]/u);
      return emojiMatch && emojiMatch[0] === itemEmoji;
    });

    if (itemIndex === -1) {
      return await interaction.editReply({
        content: `❌ Vous ne possédez pas cet objet: ${itemEmoji} ${offensiveItem.name}`,
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
        content: `❌ <@${targetUser.id}> est déjà KO !`,
        ephemeral: true,
      });
    }

    // Remove item from attacker's inventory
    attacker.inventory.splice(itemIndex, 1);
    await attacker.save();

    // Calculate damage
    let baseDamage = offensiveItem.baseDamage;
    let isCritical = Math.random() < offensiveItem.critChance;
    let finalDamage = isCritical ? Math.floor(baseDamage * offensiveItem.critMultiplier) : baseDamage;

    // Store initial HP and shield for calculation display
    const initialHP = target.combat.hp;
    const initialShield = target.combat.shield;

    // Calculate status effect reductions
    const now = new Date();
    const activeEffects = target.activeEffects?.filter(effect => {
      const elapsedSeconds = (now - effect.appliedAt) / 1000;
      return elapsedSeconds < effect.duration;
    }) || [];

    let totalReduction = 0;
    const effectDetails = [];

    activeEffects.forEach(effect => {
      const reduction = STATUS_EFFECT_REDUCTION[effect.effect] || 0;
      totalReduction += reduction;
      const emoji = STATUS_EFFECT_EMOJIS[effect.effect] || '❓';
      effectDetails.push({ effect: effect.effect, emoji, reduction });
    });

    // Apply damage reduction from status effects
    const reducedDamage = Math.floor(finalDamage * (1 - totalReduction));
    const actualDamageToApply = Math.max(1, reducedDamage); // Minimum 1 damage

    // Check for virus transfer (attacker has virus)
    let virusTransferred = false;
    let virusTransferDamage = 0;
    const attackerHasVirus = attacker.activeEffects?.some(e => e.effect === 'VIRUS');

    if (attackerHasVirus) {
      // Transfer virus to target
      await applyStatusEffect(
        targetUser.id,
        'VIRUS',
        interaction.channelId,
        interaction.guildId,
        attackerUser.id
      );
      virusTransferred = true;

      // Deal 5 damage to attacker (virus transfer damage)
      virusTransferDamage = 5;
      await applyDamage(attackerUser.id, 5, null);
    }

    // Check for infection mechanics (attacker has infection)
    let infectionBonus = 0;
    let infectionSpread = false;
    const attackerHasInfection = attacker.activeEffects?.some(e => e.effect === 'INFECTION');

    if (attackerHasInfection) {
      const targetHasInfection = activeEffects.some(e => e.effect === 'INFECTION');

      if (targetHasInfection) {
        // Target already infected: no damage bonus, no change
        // Nothing happens
      } else {
        // Not infected: +3 damage and 25% chance to infect
        infectionBonus = 3;
        actualDamageToApply += 3;

        if (Math.random() < 0.25) {
          await applyStatusEffect(
            targetUser.id,
            'INFECTION',
            interaction.channelId,
            interaction.guildId,
            attackerUser.id
          );
          infectionSpread = true;

          // Apply immediate 5 damage from infection
          await applyDamage(targetUser.id, 5, attackerUser.id);
        }
      }
    }

    // Apply damage using combat utility
    const damageResult = await applyDamage(targetUser.id, actualDamageToApply, attackerUser.id);

    // Reload target and attacker to get updated stats
    target = await Player.findOne({ userId: targetUser.id });
    attacker = await Player.findOne({ userId: attackerUser.id });

    // Apply status effect if item applies one
    let statusEffectApplied = null;
    if (isStatusEffectItem(itemEmoji)) {
      const statusEffectData = getStatusEffectByItem(itemEmoji);
      if (statusEffectData) {
        const effectResult = await applyStatusEffect(
          targetUser.id,
          STATUS_EFFECT_ITEMS[itemEmoji],
          interaction.channelId,
          interaction.guildId,
          attackerUser.id
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

    // Build damage calculation string matching screenshot format
    let calculationStr = buildDamageCalculation(
      initialHP,
      initialShield,
      finalDamage,
      damageResult.shieldDamage,
      damageResult.hpDamage,
      target.combat.hp,
      target.combat.shield,
      effectDetails
    );

    // Build embed description
    let description = `<@${attackerUser.id}> ${offensiveItem.action} **${offensiveItem.description}** sur <@${targetUser.id}> !\n\n`;

    if (isCritical) {
      description += `💥 **COUP CRITIQUE !** (${offensiveItem.critMultiplier}x)\n`;
    }

    description += `**Calcul des dégâts:**\n${calculationStr}\n\n`;

    // Add shield destroyed message if applicable
    if (initialShield > 0 && target.combat.shield === 0) {
      description += `🛡️ **Bouclier détruit !**\n\n`;
    }

    // Add status effect messages
    if (effectDetails.length > 0) {
      const effectNames = effectDetails.map(e => `${e.emoji} ${e.effect}`).join(', ');
      description += `🧬 Effets actifs réduisent les dégâts: ${effectNames}\n\n`;
    }

    // Add virus transfer message
    if (virusTransferred) {
      description += `🦠 **Virus transféré !** <@${targetUser.id}> est maintenant infecté !\n`;
      description += `💥 <@${attackerUser.id}> subit **${virusTransferDamage} dégâts** du transfert viral → **${attacker.combat.hp} ❤️**\n\n`;
    }

    // Add infection spread/bonus message
    if (infectionSpread) {
      description += `🧟 **Infection transmise !** <@${targetUser.id}> est infecté et subit **5 dégâts d'infection** ! (+${infectionBonus} dégâts de l'attaque)\n\n`;
    } else if (infectionBonus > 0) {
      description += `🧟 **Attaque sur cible non-infectée !** (+${infectionBonus} dégâts)\n\n`;
    }

    // Add applied status effect message
    if (statusEffectApplied) {
      const minutes = Math.floor(statusEffectApplied.duration / 60);
      if (statusEffectApplied.refreshed) {
        description += `${statusEffectApplied.emoji} **${statusEffectApplied.name} renouvelé !** (${minutes} min)\n\n`;
      } else {
        description += `${statusEffectApplied.emoji} **${statusEffectApplied.name} appliqué !** (${minutes} min)\n\n`;
      }
    }

    // Add KO message if applicable
    if (damageResult.isKO) {
      description += `💀 **<@${targetUser.id}> est KO !**\n\n`;
      description += `🏆 <@${attackerUser.id}> remporte le combat !`;
    } else {
      description += `<@${targetUser.id}> → **${target.combat.hp} ❤️ | ${target.combat.shield} 🛡**`;
    }

    const embed = new EmbedBuilder()
      .setColor(COLORS.COMBAT_DAMAGE)
      .setTitle(`⚔️ Combat: ${attackerUser.username} VS ${targetUser.username}`)
      .setDescription(description)
      .setTimestamp();

    await interaction.editReply({ embeds: [embed] });

  } catch (error) {
    console.error('Error in /fight command:', error);
    await interaction.editReply({
      content: '❌ Une erreur est survenue lors du combat.',
      ephemeral: true,
    });
  }
}

// Build damage calculation string matching screenshot format
function buildDamageCalculation(initialHP, initialShield, baseDamage, shieldDamage, hpDamage, finalHP, finalShield, effectDetails) {
  // Format: 37 ❤️ | 10 🛡 − (10 ❤️ − 10 🪖 | 10 🛡 − 2 🧪) = 37 ❤️ | 2 🛡

  let calculation = `${initialHP} ❤️ | ${initialShield} 🛡`;

  // Build the damage portion
  let damageStr = ' − (';

  // Show HP damage and shield damage
  if (hpDamage > 0 && shieldDamage > 0) {
    damageStr += `${hpDamage} ❤️ | ${shieldDamage} 🛡`;
  } else if (hpDamage > 0) {
    damageStr += `${hpDamage} ❤️`;
  } else if (shieldDamage > 0) {
    damageStr += `${shieldDamage} 🛡`;
  }

  // Add status effect reductions
  if (effectDetails.length > 0) {
    effectDetails.forEach(effect => {
      const reductionAmount = Math.floor(baseDamage * effect.reduction);
      damageStr += ` − ${reductionAmount} ${effect.emoji}`;
    });
  }

  damageStr += ')';

  calculation += damageStr;
  calculation += ` = ${finalHP} ❤️ | ${finalShield} 🛡`;

  return calculation;
}

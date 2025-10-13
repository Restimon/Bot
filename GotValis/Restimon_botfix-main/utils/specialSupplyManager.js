import { EmbedBuilder } from 'discord.js';
import { SpecialSupply } from '../database/models/SpecialSupply.js';
import { SpecialSupplyTracker } from '../database/models/SpecialSupplyTracker.js';
import { Player } from '../database/models/Player.js';
import { generateSpecialSupplyReward, applyRewardToPlayer } from './rewards.js';

const SPECIAL_SUPPLY_EMOJI = '📦';
const SPECIAL_SUPPLY_DURATION = 300000; // 5 minutes
const MAX_PARTICIPANTS = 5;

// Check if we should spawn a special supply
export async function checkAndSpawnSpecialSupply(guild, channel) {
  try {
    // Check if channel allows bot to send messages and add reactions
    const permissions = channel.permissionsFor(guild.members.me);
    if (!permissions || !permissions.has(['SendMessages', 'AddReactions'])) {
      return false;
    }

    // Get or create tracker
    let tracker = await SpecialSupplyTracker.findOne({ guildId: guild.id });

    if (!tracker) {
      tracker = await SpecialSupplyTracker.create({
        guildId: guild.id,
        lastActiveChannelId: channel.id,
        messagesSinceLastSupply: 0,
      });
      return false; // Don't spawn on first creation
    }

    // Update last active channel
    tracker.lastActiveChannelId = channel.id;

    // Check if we can spawn
    if (!tracker.canSpawnSupply()) {
      await tracker.save();
      return false;
    }

    // Random chance to spawn (20% chance when conditions are met)
    if (Math.random() > 0.2) {
      await tracker.save();
      return false;
    }

    // Spawn the special supply!
    await spawnSpecialSupply(guild, channel, tracker);
    return true;

  } catch (error) {
    console.error('Error checking special supply spawn:', error);
    return false;
  }
}

// Spawn a special supply
async function spawnSpecialSupply(guild, channel, tracker) {
  try {
    // Create the embed
    const embed = new EmbedBuilder()
      .setColor('#F39C12')
      .setTitle('📦 Ravitaillement spécial GotValis')
      .setDescription(
        `Réagissez avec ${SPECIAL_SUPPLY_EMOJI} pour récupérer une récompense surprise !\n` +
        `⏱️ Disponible pendant 5 minutes, maximum 5 personnes.`
      )
      .setTimestamp(Date.now() + SPECIAL_SUPPLY_DURATION)
      .setFooter({ text: 'Ravitaillement spécial' });

    const message = await channel.send({ embeds: [embed] });
    await message.react(SPECIAL_SUPPLY_EMOJI);

    // Create database entry
    const specialSupply = await SpecialSupply.create({
      guildId: guild.id,
      channelId: channel.id,
      messageId: message.id,
      participants: [],
      isActive: true,
      isCompleted: false,
    });

    // Update tracker
    tracker.suppliesSpawnedToday += 1;
    tracker.lastSupplyAt = new Date();
    tracker.messagesSinceLastSupply = 0;
    tracker.hasActiveSupply = true;
    tracker.activeSupplyId = specialSupply._id;
    await tracker.save();

    console.log(`✨ Special supply spawned in ${channel.name} (${tracker.suppliesSpawnedToday}/3 today)`);

    // Create reaction collector
    const filter = (reaction, user) => {
      return reaction.emoji.name === SPECIAL_SUPPLY_EMOJI && !user.bot;
    };

    const collector = message.createReactionCollector({
      filter,
      time: SPECIAL_SUPPLY_DURATION,
      max: MAX_PARTICIPANTS,
    });

    collector.on('collect', async (reaction, user) => {
      await handleSpecialSupplyParticipant(specialSupply, user, tracker);
    });

    collector.on('end', async () => {
      await completeSpecialSupply(message, specialSupply, tracker);
    });

  } catch (error) {
    console.error('Error spawning special supply:', error);
  }
}

// Handle a participant joining
async function handleSpecialSupplyParticipant(specialSupply, user, tracker) {
  try {
    // Reload to get latest data
    const supply = await SpecialSupply.findById(specialSupply._id);

    if (!supply || !supply.isActive) return;

    // Check if already participated
    const alreadyParticipated = supply.participants.some(p => p.userId === user.id);
    if (alreadyParticipated) return;

    // Check if full
    if (supply.participants.length >= MAX_PARTICIPANTS) return;

    // Generate reward
    const reward = generateSpecialSupplyReward();

    // Add participant
    supply.participants.push({
      userId: user.id,
      username: user.username,
      reactedAt: new Date(),
      reward: {
        type: reward.type,
        details: reward.details,
      }
    });

    await supply.save();

    console.log(`${user.username} joined special supply (${supply.participants.length}/${MAX_PARTICIPANTS})`);

  } catch (error) {
    console.error('Error handling special supply participant:', error);
  }
}

// Complete the special supply
async function completeSpecialSupply(message, specialSupply, tracker) {
  try {
    // Reload to get latest data
    const supply = await SpecialSupply.findById(specialSupply._id);

    if (!supply) return;

    const participantCount = supply.participants.length;

    if (participantCount === 0) {
      // No participants
      const embed = new EmbedBuilder()
        .setColor('#95A5A6')
        .setTitle('📦 Ravitaillement spécial GotValis')
        .setDescription('❌ Personne n\'a récupéré le ravitaillement spécial.')
        .setTimestamp();

      await message.edit({ embeds: [embed] });
    } else {
      // Build rewards summary
      const rewardLines = [];

      for (const participant of supply.participants) {
        const reward = participant.reward;
        let rewardDescription = '';

        switch (reward.type) {
          case 'item':
            rewardDescription = `${reward.details.emoji} ${reward.details.name}${reward.details.quantity > 1 ? ` x${reward.details.quantity}` : ''}`;
            break;
          case 'ticket':
            rewardDescription = '🎫 1 Ticket';
            break;
          case 'coins':
            rewardDescription = `🪙 ${reward.details.amount} GotCoins`;
            break;
          case 'damage':
            rewardDescription = `💥 ${reward.details.amount} dégâts (PV: ${reward.details.hp})`;
            break;
          case 'heal':
            const critText = reward.details.critChance > 0 ? ` (Crit ${reward.details.critChance}%)` : '';
            rewardDescription = `💚 Restaure ${reward.details.amount} PV${critText}`;
            break;
          case 'status_effect':
            rewardDescription = `${reward.details.emoji} ${reward.details.name} (${reward.details.duration}s)`;
            break;
        }

        // Map emoji to reward type
        let rewardEmoji = '🎁';
        if (reward.type === 'damage') rewardEmoji = '💥';
        else if (reward.type === 'heal') rewardEmoji = '🎁';
        else if (reward.type === 'item') rewardEmoji = reward.details.emoji;

        rewardLines.push(`${rewardEmoji} @${participant.username} a obtenu ${rewardDescription}`);

        // Apply reward to player
        await applyRewardToPlayer(Player, participant.userId, {
          type: reward.type,
          details: reward.details,
          description: rewardDescription,
        });
      }

      const embed = new EmbedBuilder()
        .setColor('#2ECC71')
        .setTitle('📦 Récapitulatif du ravitaillement')
        .setDescription(rewardLines.join('\n'))
        .setFooter({ text: `${participantCount} participant${participantCount > 1 ? 's' : ''}` })
        .setTimestamp();

      await message.edit({ embeds: [embed] });
    }

    // Mark as completed
    supply.isActive = false;
    supply.isCompleted = true;
    supply.completedAt = new Date();
    await supply.save();

    // Update tracker
    tracker.hasActiveSupply = false;
    tracker.activeSupplyId = null;
    await tracker.save();

  } catch (error) {
    console.error('Error completing special supply:', error);
  }
}

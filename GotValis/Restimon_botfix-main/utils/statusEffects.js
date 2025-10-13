// Status effect management utilities
import { Player } from '../database/models/Player.js';
import { getStatusEffect } from '../data/statusEffects.js';
import { applyDamage, applyHealing } from './combat.js';

/**
 * Apply a status effect to a player
 * @param {string} userId - Target player user ID
 * @param {string} effectName - Effect name (POISON, BURN, etc.)
 * @param {string} channelId - Channel ID for notifications
 * @param {string} guildId - Guild ID
 * @returns {Promise<Object>} Result object
 */
export async function applyStatusEffect(userId, effectName, channelId, guildId) {
  const player = await Player.findOne({ userId });

  if (!player) {
    throw new Error('Player not found');
  }

  const effectData = getStatusEffect(effectName);
  if (!effectData) {
    throw new Error('Invalid status effect');
  }

  // Check if effect already exists
  const existingEffectIndex = player.activeEffects.findIndex(
    e => e.effect === effectName
  );

  if (existingEffectIndex !== -1) {
    // Refresh existing effect (reset duration and last tick)
    player.activeEffects[existingEffectIndex].appliedAt = new Date();
    player.activeEffects[existingEffectIndex].lastTickAt = new Date();
    player.activeEffects[existingEffectIndex].duration = effectData.duration;
  } else {
    // Add new effect
    player.activeEffects.push({
      effect: effectName,
      appliedAt: new Date(),
      duration: effectData.duration,
      tickValue: effectData.tickValue,
      tickInterval: effectData.tickInterval,
      lastTickAt: new Date(),
      channelId,
      guildId,
    });
  }

  await player.save();

  return {
    success: true,
    effect: effectName,
    duration: effectData.duration,
    refreshed: existingEffectIndex !== -1,
  };
}

/**
 * Remove a status effect from a player
 * @param {string} userId - Player user ID
 * @param {string} effectName - Effect name to remove
 * @returns {Promise<Object>} Result object
 */
export async function removeStatusEffect(userId, effectName) {
  const player = await Player.findOne({ userId });

  if (!player) {
    throw new Error('Player not found');
  }

  const effectIndex = player.activeEffects.findIndex(
    e => e.effect === effectName
  );

  if (effectIndex === -1) {
    return { success: false, message: 'Effect not found' };
  }

  player.activeEffects.splice(effectIndex, 1);
  await player.save();

  return { success: true };
}

/**
 * Get all active status effects for a player
 * @param {string} userId - Player user ID
 * @returns {Promise<Array>} Active effects
 */
export async function getActiveStatusEffects(userId) {
  const player = await Player.findOne({ userId });

  if (!player) {
    return [];
  }

  const now = new Date();

  // Filter expired effects
  const activeEffects = player.activeEffects.filter(effect => {
    const elapsedSeconds = (now - effect.appliedAt) / 1000;
    return elapsedSeconds < effect.duration;
  });

  return activeEffects;
}

/**
 * Process a single tick for a status effect
 * @param {Object} player - Player document
 * @param {Object} effect - Effect object
 * @param {Object} client - Discord client for sending messages
 * @returns {Promise<Object>} Tick result
 */
export async function processEffectTick(player, effect, client) {
  const effectData = getStatusEffect(effect.effect);

  if (!effectData) {
    return { success: false, message: 'Invalid effect' };
  }

  const now = new Date();
  const timeSinceLastTick = (now - effect.lastTickAt) / 1000;

  // Check if it's time for a tick
  if (timeSinceLastTick < effect.tickInterval) {
    return { success: false, message: 'Not time for tick yet' };
  }

  // Check if effect has expired
  const elapsedSeconds = (now - effect.appliedAt) / 1000;
  if (elapsedSeconds >= effect.duration) {
    return { success: false, message: 'Effect expired', expired: true };
  }

  let result;
  const previousHP = player.combat.hp;

  // Apply tick effect
  if (effectData.type === 'damage') {
    // Apply damage (no attacker ID for status effects, but still award coins to player)
    result = await applyDamage(player.userId, effect.tickValue, null);

    // Award coins for damage taken from status effect (+1 GC per HP)
    await Player.findOneAndUpdate(
      { userId: player.userId },
      {
        $inc: {
          'economy.coins': effect.tickValue,
          'economy.totalEarned': effect.tickValue
        }
      }
    );
  } else if (effectData.type === 'heal') {
    // Apply healing (no healer ID for status effects, but still award coins to player)
    result = await applyHealing(player.userId, effect.tickValue, null);

    // Award coins for healing from status effect (+1 GC per HP)
    await Player.findOneAndUpdate(
      { userId: player.userId },
      {
        $inc: {
          'economy.coins': effect.tickValue,
          'economy.totalEarned': effect.tickValue
        }
      }
    );
  }

  // Update last tick time
  effect.lastTickAt = now;
  await player.save();

  // Reload player to get updated HP
  const updatedPlayer = await Player.findOne({ userId: player.userId });

  // Calculate time remaining
  const timeRemaining = effect.duration - elapsedSeconds;
  const minutesRemaining = Math.floor(timeRemaining / 60);

  // Send notification to channel
  if (effect.channelId && effect.guildId) {
    try {
      const guild = await client.guilds.fetch(effect.guildId);
      const channel = await guild.channels.fetch(effect.channelId);

      if (channel) {
        const currentHP = updatedPlayer.combat.hp;
        const tickValue = effect.tickValue;

        let message;
        if (effectData.type === 'damage') {
          message = `${effectData.emoji} <@${player.userId}> subit **${tickValue} dégâts** *(${effectData.description})*.
❤️ **${previousHP}** - **${tickValue}** ${effectData.emoji} = ❤️ **${currentHP}**
⏳ **Temps restant : ${minutesRemaining} min**`;
        } else {
          message = `${effectData.emoji} <@${player.userId}> récupère **${tickValue} PV** *(${effectData.emoji})*.
❤️ **${previousHP}** + **${tickValue}** ${effectData.emoji} = ❤️ **${currentHP}**
⏳ **Temps restant : ${minutesRemaining} min**`;
        }

        await channel.send(message);
      }
    } catch (error) {
      console.error('Error sending status effect tick notification:', error);
    }
  }

  return {
    success: true,
    effectType: effectData.type,
    tickValue: effect.tickValue,
    currentHP: updatedPlayer.combat.hp,
    timeRemaining: minutesRemaining,
  };
}

/**
 * Clean up expired status effects for a player
 * @param {string} userId - Player user ID
 * @returns {Promise<Object>} Cleanup result
 */
export async function cleanupExpiredEffects(userId) {
  const player = await Player.findOne({ userId });

  if (!player) {
    return { success: false, message: 'Player not found' };
  }

  const now = new Date();
  const initialCount = player.activeEffects.length;

  // Remove expired effects
  player.activeEffects = player.activeEffects.filter(effect => {
    const elapsedSeconds = (now - effect.appliedAt) / 1000;
    return elapsedSeconds < effect.duration;
  });

  const removedCount = initialCount - player.activeEffects.length;

  if (removedCount > 0) {
    await player.save();
  }

  return {
    success: true,
    removedCount,
  };
}

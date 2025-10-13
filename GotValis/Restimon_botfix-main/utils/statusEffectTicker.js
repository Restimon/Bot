// Status effect tick manager - processes ticks for all players
import { Player } from '../database/models/Player.js';
import { processEffectTick, cleanupExpiredEffects } from './statusEffects.js';

/**
 * Process all status effect ticks for all players
 * @param {Object} client - Discord client
 */
export async function processAllStatusEffectTicks(client) {
  try {
    // Find all players with active effects
    const players = await Player.find({
      'activeEffects.0': { $exists: true }, // Has at least one effect
    });

    console.log(`⏱️  Processing status effects for ${players.length} players...`);

    for (const player of players) {
      // Clean up expired effects first
      await cleanupExpiredEffects(player.userId);

      // Reload player after cleanup
      const reloadedPlayer = await Player.findOne({ userId: player.userId });

      if (!reloadedPlayer || !reloadedPlayer.activeEffects.length) {
        continue;
      }

      // Process each active effect
      for (const effect of reloadedPlayer.activeEffects) {
        try {
          const result = await processEffectTick(reloadedPlayer, effect, client);

          if (result.expired) {
            // Remove expired effect
            await cleanupExpiredEffects(reloadedPlayer.userId);
          }
        } catch (error) {
          console.error(
            `Error processing tick for ${reloadedPlayer.username} (${effect.effect}):`,
            error
          );
        }
      }
    }
  } catch (error) {
    console.error('Error in processAllStatusEffectTicks:', error);
  }
}

/**
 * Start the status effect ticker (runs every 30 seconds)
 * @param {Object} client - Discord client
 */
export function startStatusEffectTicker(client) {
  console.log('✅ Status effect ticker started (30s interval)');

  // Run immediately on start
  processAllStatusEffectTicks(client);

  // Then run every 30 seconds
  setInterval(() => {
    processAllStatusEffectTicks(client);
  }, 30 * 1000); // 30 seconds
}

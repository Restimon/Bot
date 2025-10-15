// Leaderboard utility functions
import { EmbedBuilder } from 'discord.js';
import { Player } from '../database/models/Player.js';
import { Leaderboard } from '../database/models/Leaderboard.js';

// Medal emojis for top 3
const MEDALS = {
  1: '🥇',
  2: '🥈',
  3: '🥉',
};

/**
 * Generate leaderboard embed
 * -> utilise le displayName (pseudo serveur)
 * -> n'affiche que les membres encore présents sur la guilde
 * @param {Object} client - Discord client
 * @param {string} guildId - Guild ID
 * @param {number} displayCount - Number of players to display (10 or 20)
 * @returns {Promise<EmbedBuilder>} Leaderboard embed
 */
export async function generateLeaderboardEmbed(client, guildId, displayCount = 10) {
  const guild = await client.guilds.fetch(guildId).catch(() => null);

  // Get top players (on prend large puis on filtrera)
  const players = await Player.find({})
    .sort({ 'economy.coins': -1 })
    .limit(displayCount * 5);

  // Build leaderboard description
  let description = '';
  let shown = 0;

  for (let index = 0; index < players.length; index++) {
    const player = players[index];

    // sécurise l'ID (au cas où il aurait été stocké en Number)
    const uid = typeof player.userId === 'number' ? String(player.userId) : String(player.userId || '');
    if (!uid) continue;

    // essaie le cache, sinon fetch ciblé
    let member = guild?.members?.cache.get(uid) || null;
    if (!member && guild) {
      member = await guild.members.fetch(uid).catch(() => null);
    }
    if (!member) continue; // pas/plus dans la guilde → on ignore

    const displayName = member.displayName || member.user?.username || player.username || 'Joueur';
    const coins = player.economy?.coins ?? 0;
    const hp = player.combat?.hp ?? 100;

    const rank = shown + 1;
    const medal = MEDALS[rank] || `${rank}.`;

    description += `${medal} **${displayName}** → 💰 **${coins}** GotCoins | ❤️ **${hp}** PV\n`;

    shown++;
    if (shown >= displayCount) break;
  }

  if (shown === 0) {
    return new EmbedBuilder()
      .setColor('#FFD700')
      .setTitle('🏆 CLASSEMENT GOTVALIS — ÉDITION SPÉCIALE 🏆')
      .setDescription('Aucun joueur du serveur dans le classement pour le moment.')
      .setFooter({ text: '💡 Les GotCoins représentent votre richesse accumulée.' })
      .setTimestamp();
  }

  const embed = new EmbedBuilder()
    .setColor('#FFD700')
    .setTitle('🏆 CLASSEMENT GOTVALIS — ÉDITION SPÉCIALE 🏆')
    .setDescription(description)
    .setFooter({ text: '💡 Les GotCoins représentent votre richesse accumulée.' })
    .setTimestamp();

  return embed;
}

/**
 * Update leaderboard message
 * @param {Object} client - Discord client
 * @param {string} guildId - Guild ID
 * @returns {Promise<boolean>} Success status
 */
export async function updateLeaderboard(client, guildId) {
  try {
    const leaderboard = await Leaderboard.findOne({ guildId });

    if (!leaderboard) {
      return false;
    }

    const guild = await client.guilds.fetch(guildId);
    const channel = await guild.channels.fetch(leaderboard.channelId);

    if (!channel) {
      console.error(`Leaderboard channel not found for guild ${guildId}`);
      return false;
    }

    const message = await channel.messages.fetch(leaderboard.messageId).catch(() => null);
    if (!message) {
      console.error(`Leaderboard message not found for guild ${guildId}`);
      return false;
    }

    // >>> passe le client ici <<<
    const embed = await generateLeaderboardEmbed(client, guildId, leaderboard.displayCount);

    await message.edit({ embeds: [embed] });

    leaderboard.lastUpdated = new Date();
    await leaderboard.save();

    return true;
  } catch (error) {
    console.error('Error updating leaderboard:', error);
    return false;
  }
}

/**
 * Update all leaderboards
 * @param {Object} client - Discord client
 */
export async function updateAllLeaderboards(client) {
  try {
    const leaderboards = await Leaderboard.find({});

    console.log(`⏱️  Updating ${leaderboards.length} leaderboards...`);

    for (const leaderboard of leaderboards) {
      await updateLeaderboard(client, leaderboard.guildId);
    }
  } catch (error) {
    console.error('Error updating all leaderboards:', error);
  }
}

/**
 * Start leaderboard auto-update ticker
 * @param {Object} client - Discord client
 */
export function startLeaderboardTicker(client) {
  console.log('✅ Leaderboard ticker started (30 sec interval)');

  // Run immediately on start
  updateAllLeaderboards(client);

  // Then run every 30 seconds
  setInterval(() => {
    updateAllLeaderboards(client);
  }, 30 * 1000); // 30 seconds
}

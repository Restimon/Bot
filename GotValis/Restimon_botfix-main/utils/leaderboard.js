import { EmbedBuilder } from 'discord.js';
import { Player } from '../database/models/Player.js';
import { Leaderboard } from '../database/models/Leaderboard.js';

const MEDALS = { 1: '🥇', 2: '🥈', 3: '🥉' };

export async function generateLeaderboardEmbed(guildId, displayCount = 10) {
  const players = await Player.find({}).sort({ 'economy.coins': -1 }).limit(displayCount);

  if (players.length === 0) {
    return new EmbedBuilder()
      .setColor('#FFD700')
      .setTitle('🏆 CLASSEMENT GOTVALIS — ÉDITION SPÉCIALE 🏆')
      .setDescription('Aucun joueur dans le classement pour le moment.')
      .setFooter({ text: '💡 Les GotCoins représentent votre richesse accumulée.' })
      .setTimestamp();
  }

  let description = '';
  players.forEach((player, index) => {
    const rank = index + 1;
    const medal = MEDALS[rank] || `${rank}.`;
    const coins = player.economy.coins;
    const hp = player.combat.hp;
    description += `${medal} **${player.username}** → 💰 **${coins}** GotCoins | ❤️ **${hp}** PV\n`;
  });

  return new EmbedBuilder()
    .setColor('#FFD700')
    .setTitle('🏆 CLASSEMENT GOTVALIS — ÉDITION SPÉCIALE 🏆')
    .setDescription(description)
    .setFooter({ text: '💡 Les GotCoins représentent votre richesse accumulée.' })
    .setTimestamp();
}

export async function updateLeaderboard(client, guildId) {
  try {
    const leaderboard = await Leaderboard.findOne({ guildId });
    if (!leaderboard) return false;

    const guild = await client.guilds.fetch(guildId);
    const channel = await guild.channels.fetch(leaderboard.channelId);
    if (!channel) return false;

    const embed = await generateLeaderboardEmbed(guildId, leaderboard.displayCount);

    async function createFresh() {
      const newMsg = await channel.send({ embeds: [embed] });
      leaderboard.messageId = newMsg.id;
      leaderboard.lastUpdated = new Date();
      await leaderboard.save();
      return true;
    }

    if (!leaderboard.messageId) return await createFresh();

    try {
      const msg = await channel.messages.fetch(leaderboard.messageId);
      if (!msg || msg.author?.id !== client.user.id) return await createFresh();
      await msg.edit({ embeds: [embed] });
      leaderboard.lastUpdated = new Date();
      await leaderboard.save();
      return true;
    } catch (err) {
      if (err?.code === 10008 || err?.code === 50005 || err?.code === 50013) {
        return await createFresh();
      }
      throw err;
    }
  } catch (error) {
    console.error('Error updating leaderboard:', error);
    return false;
  }
}

export async function updateAllLeaderboards(client) {
  try {
    const leaderboards = await Leaderboard.find({});
    console.log(`⏱️  Updating ${leaderboards.length} leaderboards...`);
    for (const lb of leaderboards) {
      await updateLeaderboard(client, lb.guildId);
    }
  } catch (error) {
    console.error('Error updating all leaderboards:', error);
  }
}

export function startLeaderboardTicker(client) {
  console.log('✅ Leaderboard ticker started (30 sec interval)');
  updateAllLeaderboards(client);
  setInterval(() => {
    updateAllLeaderboards(client);
  }, 30 * 1000);
}

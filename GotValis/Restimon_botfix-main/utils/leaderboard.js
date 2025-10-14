import { EmbedBuilder } from 'discord.js';
import { Player } from '../database/models/Player.js';
import { Leaderboard } from '../database/models/Leaderboard.js';

const MEDALS = { 1: '🥇', 2: '🥈', 3: '🥉' };

export async function generateLeaderboardEmbed(guildId, displayCount = 10) {
  const players = await Player.find({}).sort({ 'economy.coins': -1 }).limit(displayCount);
  if (!players.length) {
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

async function ensureGuild(client, guildId) {
  const cached = client.guilds.cache.get(guildId);
  if (cached) return cached;
  try {
    return await client.guilds.fetch(guildId);
  } catch (e) {
    if (e?.code === 10004 || e?.code === 50001) return null;
    throw e;
  }
}

export async function updateLeaderboard(client, guildId) {
  try {
    const lb = await Leaderboard.findOne({ guildId });
    if (!lb) return false;

    const guild = await ensureGuild(client, guildId);
    if (!guild) {
      await Leaderboard.deleteOne({ guildId });
      return false;
    }

    const channel = await guild.channels.fetch(lb.channelId).catch(() => null);
    if (!channel) {
      await Leaderboard.deleteOne({ guildId });
      return false;
    }

    const embed = await generateLeaderboardEmbed(guildId, lb.displayCount);

    let msg = null;
    if (lb.messageId) {
      msg = await channel.messages.fetch(lb.messageId).catch(() => null);
    }

    if (!msg || msg.author?.id !== client.user.id) {
      const newMsg = await channel.send({ embeds: [embed] }).catch(() => null);
      if (!newMsg) return false;
      lb.messageId = newMsg.id;
      lb.lastUpdated = new Date();
      await lb.save();
      return true;
    }

    await msg.edit({ embeds: [embed] }).catch(async (e) => {
      if (e?.code === 50005 || e?.code === 10008) {
        const newMsg = await channel.send({ embeds: [embed] }).catch(() => null);
        if (!newMsg) return;
        lb.messageId = newMsg.id;
        lb.lastUpdated = new Date();
        await lb.save();
        return;
      }
      throw e;
    });

    lb.lastUpdated = new Date();
    await lb.save();
    return true;
  } catch (error) {
    if (error?.code === 10004) {
      await Leaderboard.deleteOne({ guildId });
      return false;
    }
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

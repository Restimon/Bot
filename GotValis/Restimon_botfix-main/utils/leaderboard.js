import { EmbedBuilder } from 'discord.js';
import { Player } from '../database/models/Player.js';
import { Leaderboard } from '../database/models/Leaderboard.js';

const MEDALS = { 1: '🥇', 2: '🥈', 3: '🥉' };

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

/**
 * Génère l'embed du classement :
 *  - noms = displayName (pseudo serveur)
 *  - seulement les membres encore présents sur la guilde
 */
export async function generateLeaderboardEmbed(client, guildId, displayCount = 10) {
  const guild = await ensureGuild(client, guildId);
  if (!guild) {
    return new EmbedBuilder()
      .setColor('#FFD700')
      .setTitle('🏆 CLASSEMENT GOTVALIS — ÉDITION SPÉCIALE 🏆')
      .setDescription('Le bot n’est pas présent sur cette guilde.')
      .setTimestamp();
  }

  // On récupère tous les membres pour :
  // 1) filtrer ceux encore dans la guilde
  // 2) récupérer le displayName (pseudo serveur)
  const members = await guild.members.fetch().catch(() => null);
  if (!members) {
    return new EmbedBuilder()
      .setColor('#FFD700')
      .setTitle('🏆 CLASSEMENT GOTVALIS — ÉDITION SPÉCIALE 🏆')
      .setDescription('Impossible de récupérer les membres de la guilde.')
      .setTimestamp();
  }

  const memberIds = new Set(members.map(m => m.id));

  // On prend tous les joueurs classés par coins, puis on filtre pour ne garder
  // que ceux qui sont encore dans la guilde. On s’arrête à displayCount.
  const sortedPlayers = await Player.find({})
    .sort({ 'economy.coins': -1 })
    .limit(100); // marge pour filtrer

  const inGuild = [];
  for (const p of sortedPlayers) {
    if (memberIds.has(p.userId)) inGuild.push(p);
    if (inGuild.length >= displayCount) break;
  }

  if (inGuild.length === 0) {
    return new EmbedBuilder()
      .setColor('#FFD700')
      .setTitle('🏆 CLASSEMENT GOTVALIS — ÉDITION SPÉCIALE 🏆')
      .setDescription('Aucun membre du serveur dans le classement pour le moment.')
      .setFooter({ text: '💡 Les GotCoins représentent votre richesse accumulée.' })
      .setTimestamp();
  }

  let description = '';
  inGuild.forEach((player, index) => {
    const rank = index + 1;
    const medal = MEDALS[rank] || `${rank}.`;
    const coins = player.economy?.coins ?? 0;
    const hp = player.combat?.hp ?? 100;

    const member = members.get(player.userId);
    const displayName = member?.displayName || member?.user?.username || player.username || 'Joueur';

    description += `${medal} **${displayName}** → 💰 **${coins}** GotCoins | ❤️ **${hp}** PV\n`;
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

    const embed = await generateLeaderboardEmbed(client, guildId, lb.displayCount);

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

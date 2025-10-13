import { Events } from 'discord.js';
import { Player } from '../database/models/Player.js';
import { ActivitySession } from '../database/models/ActivitySession.js';

export const name = Events.VoiceStateUpdate;

// Track voice sessions
const voiceSessions = new Map(); // userId -> { joinedAt, guildId, channelId, sessionId }

export async function execute(oldState, newState) {
  const userId = newState.member.id;
  const username = newState.member.user.username;

  // User joined a voice channel
  if (!oldState.channelId && newState.channelId) {
    const startTime = new Date();

    // Create activity session in database
    const session = await ActivitySession.create({
      userId,
      username,
      guildId: newState.guild.id,
      type: 'voice',
      channelId: newState.channelId,
      startTime,
    });

    voiceSessions.set(userId, {
      joinedAt: startTime,
      guildId: newState.guild.id,
      channelId: newState.channelId,
      sessionId: session._id,
    });

    console.log(`🎤 ${username} joined voice channel`);
  }

  // User left a voice channel
  else if (oldState.channelId && !newState.channelId) {
    const sessionData = voiceSessions.get(userId);

    if (sessionData) {
      const now = new Date();
      const timeSpent = (now - sessionData.joinedAt) / 1000 / 60; // minutes

      // Update activity session in database
      await ActivitySession.findByIdAndUpdate(sessionData.sessionId, {
        endTime: now,
        duration: Math.floor(timeSpent),
      });

      // Update voice time in player stats
      await Player.findOneAndUpdate(
        { userId },
        {
          userId,
          username,
          $inc: {
            'activity.voiceTime': Math.floor(timeSpent),
          },
          lastUpdated: now,
        },
        { upsert: true }
      );

      voiceSessions.delete(userId);
      console.log(`🎤 ${username} left voice channel (${Math.floor(timeSpent)} min)`);
    }
  }

  // User switched channels (still in voice)
  else if (oldState.channelId && newState.channelId && oldState.channelId !== newState.channelId) {
    console.log(`🎤 ${username} switched voice channels`);
  }
}

// Voice reward ticker - runs every 30 minutes to reward active voice users
export function startVoiceRewardTicker(client) {
  console.log('✅ Voice reward ticker started (30 min interval)');

  setInterval(async () => {
    console.log('⏱️  Processing voice rewards...');

    for (const [userId, session] of voiceSessions.entries()) {
      try {
        const player = await Player.findOne({ userId });

        if (!player) continue;

        const now = new Date();
        const canReward = !player.activity?.lastVoiceReward ||
                         (now - player.activity.lastVoiceReward) >= 30 * 60 * 1000;

        if (canReward) {
          const reward = Math.floor(Math.random() * 5) + 2; // 2-6 GC

          await Player.findOneAndUpdate(
            { userId },
            {
              $inc: {
                'economy.coins': reward,
                'economy.totalEarned': reward,
              },
              'activity.lastVoiceReward': now,
            }
          );

          console.log(`💰 Rewarded ${player.username} ${reward} GC for voice activity`);
        }
      } catch (error) {
        console.error(`Error processing voice reward for ${userId}:`, error);
      }
    }
  }, 30 * 60 * 1000); // 30 minutes
}

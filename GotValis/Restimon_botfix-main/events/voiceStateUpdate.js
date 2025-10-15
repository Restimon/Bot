// events/voiceStateUpdate.js
import { Events } from 'discord.js';
import { Player } from '../database/models/Player.js';
import { ActivitySession } from '../database/models/ActivitySession.js';

export const name = Events.VoiceStateUpdate;
export const once = false;

// cache RAM facultatif (accélère, mais on ne s'y fie pas)
const voiceSessions = new Map(); // userId -> { joinedAt, guildId, channelId, sessionId }

async function closeOpenSession(userId) {
  // ferme la session ouverte en DB si elle existe
  const open = await ActivitySession.findOne({ userId, type: 'voice', endTime: null });
  if (!open) return null;

  const now = new Date();
  const minutes = Math.max(1, Math.round((now - open.startTime) / 60000));
  open.endTime = now;
  open.duration = minutes;
  await open.save();

  // incrémente aussi le compteur côté Player (optionnel mais utile)
  await Player.findOneAndUpdate(
    { userId },
    {
      $inc: { 'activity.voiceTime': minutes },
      lastUpdated: now,
    },
    { upsert: true }
  );

  return open;
}

export async function execute(oldState, newState) {
  try {
    const userId = newState?.member?.id || oldState?.member?.id;
    const username = newState?.member?.user?.username || oldState?.member?.user?.username || 'user';
    const guildId = (newState.guild || oldState.guild)?.id;

    // rien n'a changé (mute/unmute) -> on ignore
    if (oldState.channelId === newState.channelId) return;

    // a QUITTÉ complètement la voix
    if (oldState.channelId && !newState.channelId) {
      // ferme la session en RAM si on l'a
      const ram = voiceSessions.get(userId);
      if (ram) voiceSessions.delete(userId);

      // ferme la session DB ouverte même si la RAM n'a rien
      const closed = await closeOpenSession(userId);
      if (closed) {
        console.log(`🎤 ${username} left voice channel (${closed.duration} min)`);
      } else {
        console.log(`🎤 ${username} left voice channel (no open session found, already closed?)`);
      }
      return;
    }

    // a REJOINT la voix (aucune ancienne channel)
    if (!oldState.channelId && newState.channelId) {
      // par sécurité, ferme une éventuelle session DB ouverte
      await closeOpenSession(userId);

      const startTime = new Date();
      const session = await ActivitySession.create({
        userId,
        username,
        guildId,
        type: 'voice',
        channelId: newState.channelId,
        startTime,
        endTime: null,
        duration: 0,
      });

      voiceSessions.set(userId, {
        joinedAt: startTime,
        guildId,
        channelId: newState.channelId,
        sessionId: session._id,
      });

      console.log(`🎤 ${username} joined voice channel`);
      return;
    }

    // a CHANGÉ de salon vocal
    if (oldState.channelId && newState.channelId && oldState.channelId !== newState.channelId) {
      // clôture l'ancienne session puis en ouvre une nouvelle
      await closeOpenSession(userId);

      const startTime = new Date();
      const session = await ActivitySession.create({
        userId,
        username,
        guildId,
        type: 'voice',
        channelId: newState.channelId,
        startTime,
        endTime: null,
        duration: 0,
      });

      voiceSessions.set(userId, {
        joinedAt: startTime,
        guildId,
        channelId: newState.channelId,
        sessionId: session._id,
      });

      console.log(`🎤 ${username} switched voice channels`);
    }
  } catch (err) {
    console.error('voiceStateUpdate error:', err);
  }
}

// (optionnel) récompense périodique basée sur la DB (pas la RAM)
export function startVoiceRewardTicker(client) {
  console.log('✅ Voice reward ticker started (30 min interval)');

  setInterval(async () => {
    console.log('⏱️  Processing voice rewards...');
    const now = new Date();

    // récupère toutes les sessions OUVERTES (utilisateurs encore en vocal)
    const openSessions = await ActivitySession.find({ type: 'voice', endTime: null });

    for (const s of openSessions) {
      try {
        const player = await Player.findOne({ userId: s.userId });
        if (!player) continue;

        const canReward =
          !player.activity?.lastVoiceReward ||
          (now - player.activity.lastVoiceReward) >= 30 * 60 * 1000;

        if (canReward) {
          const reward = Math.floor(Math.random() * 5) + 2; // 2-6 GC
          await Player.findOneAndUpdate(
            { userId: s.userId },
            {
              $inc: { 'economy.coins': reward, 'economy.totalEarned': reward },
              'activity.lastVoiceReward': now,
              lastUpdated: now,
            },
            { upsert: true }
          );
          console.log(`💰 Rewarded ${player?.username || s.userId} ${reward} GC for voice activity`);
        }
      } catch (e) {
        console.error(`Error processing voice reward for ${s.userId}:`, e);
      }
    }
  }, 30 * 60 * 1000);
}

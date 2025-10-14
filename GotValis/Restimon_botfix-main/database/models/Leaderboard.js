import mongoose from 'mongoose';

const leaderboardSchema = new mongoose.Schema({
  guildId: { type: String, required: true, unique: true },
  channelId: { type: String, required: true },
  messageId: { type: String, required: true },
  displayCount: { type: Number, default: 10 }, // 10 or 20
  lastUpdated: { type: Date, default: Date.now },
  createdAt: { type: Date, default: Date.now },
});

export const Leaderboard = mongoose.model('Leaderboard', leaderboardSchema);

import mongoose from 'mongoose';

const activitySessionSchema = new mongoose.Schema({
  userId: { type: String, required: true, index: true },
  username: { type: String, required: true },
  guildId: { type: String, required: true },

  // Session type: 'voice' or 'message'
  type: { type: String, required: true, enum: ['voice', 'message'] },

  // Voice session data
  channelId: { type: String }, // For voice sessions
  startTime: { type: Date, required: true },
  endTime: { type: Date }, // null if still active

  // Duration in minutes (calculated on end)
  duration: { type: Number, default: 0 },

  createdAt: { type: Date, default: Date.now },
});

// Index for efficient queries on last 7 days
activitySessionSchema.index({ userId: 1, type: 1, startTime: -1 });
activitySessionSchema.index({ createdAt: 1 });

export const ActivitySession = mongoose.model('ActivitySession', activitySessionSchema);

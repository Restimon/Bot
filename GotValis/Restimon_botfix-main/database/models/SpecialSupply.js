import mongoose from 'mongoose';

const specialSupplySchema = new mongoose.Schema({
  guildId: { type: String, required: true },
  channelId: { type: String, required: true },
  messageId: { type: String, required: true },

  // Participants who reacted (max 5)
  participants: [{
    userId: String,
    username: String,
    reactedAt: { type: Date, default: Date.now },
    reward: {
      type: String, // 'item', 'ticket', 'coins', 'damage', 'heal', 'status_effect'
      details: mongoose.Schema.Types.Mixed, // Reward details
    }
  }],

  // Supply status
  isActive: { type: Boolean, default: true },
  isCompleted: { type: Boolean, default: false },

  // Timestamps
  createdAt: { type: Date, default: Date.now },
  expiresAt: { type: Date, default: () => new Date(Date.now() + 300000) }, // 5 minutes
  completedAt: { type: Date },
});

// Auto-delete after 1 hour
specialSupplySchema.index({ expiresAt: 1 }, { expireAfterSeconds: 3600 });

export const SpecialSupply = mongoose.model('SpecialSupply', specialSupplySchema);

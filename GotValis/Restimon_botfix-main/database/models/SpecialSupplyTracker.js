import mongoose from 'mongoose';

const specialSupplyTrackerSchema = new mongoose.Schema({
  guildId: { type: String, required: true, unique: true },

  // Daily tracking
  todayDate: { type: String, default: () => new Date().toISOString().split('T')[0] }, // YYYY-MM-DD
  suppliesSpawnedToday: { type: Number, default: 0 },
  maxSuppliesPerDay: { type: Number, default: 3 },

  // Last spawn tracking
  lastSupplyAt: { type: Date },
  lastActiveChannelId: { type: String },
  messagesSinceLastSupply: { type: Number, default: 0 },

  // Active supply tracking
  hasActiveSupply: { type: Boolean, default: false },
  activeSupplyId: { type: mongoose.Schema.Types.ObjectId },

  // Timestamps
  updatedAt: { type: Date, default: Date.now },
});

// Method to check if a new supply can spawn
specialSupplyTrackerSchema.methods.canSpawnSupply = function() {
  const now = new Date();
  const currentHour = now.getHours();
  const currentMinutes = now.getMinutes();

  // Reset daily counter if it's a new day
  const today = now.toISOString().split('T')[0];
  if (this.todayDate !== today) {
    this.todayDate = today;
    this.suppliesSpawnedToday = 0;
  }

  // Check: No spawns between 00:00 and 06:30
  if (currentHour < 6 || (currentHour === 6 && currentMinutes < 30)) {
    return false;
  }

  // Check: Max 3 per day
  if (this.suppliesSpawnedToday >= this.maxSuppliesPerDay) {
    return false;
  }

  // Check: No active supply
  if (this.hasActiveSupply) {
    return false;
  }

  // Check: At least 3 hours since last supply
  if (this.lastSupplyAt) {
    const hoursSinceLastSupply = (now - this.lastSupplyAt) / (1000 * 60 * 60);
    if (hoursSinceLastSupply < 3) {
      return false;
    }
  }

  // Check: At least 30 messages since last supply
  if (this.messagesSinceLastSupply < 30) {
    return false;
  }

  return true;
};

export const SpecialSupplyTracker = mongoose.model('SpecialSupplyTracker', specialSupplyTrackerSchema);

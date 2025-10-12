import mongoose from 'mongoose';

const lootBoxSchema = new mongoose.Schema({
  guildId: { type: String, required: true },
  channelId: { type: String, required: true },
  messageId: { type: String, required: true },

  // Joueurs qui ont réagi
  participants: [{
    userId: String,
    username: String,
    reactedAt: { type: Date, default: Date.now },
  }],

  // État du loot box
  isActive: { type: Boolean, default: true },
  isOpened: { type: Boolean, default: false },

  // Items générés pour chaque participant
  rewards: [{
    userId: String,
    item: {
      itemId: String,
      name: String,
      rarity: String, // common, uncommon, rare, epic, legendary
      emoji: String,
      value: Number,
    }
  }],

  // Timestamps
  createdAt: { type: Date, default: Date.now },
  expiresAt: { type: Date, default: () => new Date(Date.now() + 30000) }, // 30 secondes
  openedAt: { type: Date },
});

// Index pour nettoyer les anciens loot boxes
lootBoxSchema.index({ expiresAt: 1 }, { expireAfterSeconds: 300 }); // Suppression après 5 minutes

export const LootBox = mongoose.model('LootBox', lootBoxSchema);

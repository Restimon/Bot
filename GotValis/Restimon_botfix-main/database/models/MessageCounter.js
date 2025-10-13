import mongoose from 'mongoose';

const messageCounterSchema = new mongoose.Schema({
  guildId: { type: String, required: true, unique: true },

  // Compteur de messages
  messageCount: { type: Number, default: 0 },

  // Prochain déclenchement (aléatoire entre 5 et 15)
  nextTrigger: { type: Number, default: () => Math.floor(Math.random() * 11) + 5 }, // 5-15

  // Y a-t-il un loot box actif?
  hasActiveLootBox: { type: Boolean, default: false },

  // Dernier loot box créé
  lastLootBoxAt: { type: Date },

  // Timestamps
  lastMessageAt: { type: Date, default: Date.now },
});

export const MessageCounter = mongoose.model('MessageCounter', messageCounterSchema);

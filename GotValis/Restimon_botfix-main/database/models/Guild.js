import mongoose from 'mongoose';

const guildSchema = new mongoose.Schema({
  guildId: { type: String, required: true, unique: true },
  guildName: { type: String, required: true },

  // Configuration du système de bienvenue
  welcome: {
    enabled: { type: Boolean, default: false },
    channelId: { type: String, default: null },
    message: {
      type: String,
      default: 'Bienvenue {user} sur le serveur {server} ! 🎉'
    },
  },

  // Timestamps
  createdAt: { type: Date, default: Date.now },
  lastUpdated: { type: Date, default: Date.now },
});

export const Guild = mongoose.model('Guild', guildSchema);

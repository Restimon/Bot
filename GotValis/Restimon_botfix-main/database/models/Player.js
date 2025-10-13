import mongoose from 'mongoose';

const playerSchema = new mongoose.Schema({
  userId: { type: String, required: true, unique: true },
  username: { type: String, required: true },

  // Statistiques de jeu
  stats: {
    damageDealt: { type: Number, default: 0 }, // Total damage dealt (cumulative)
    damageTaken: { type: Number, default: 0 }, // Total damage taken (cumulative)
    healingDone: { type: Number, default: 0 }, // Total healing done (cumulative)
    kills: { type: Number, default: 0 },
    deaths: { type: Number, default: 0 },
    assists: { type: Number, default: 0 },
    // Legacy fields for compatibility
    damages: { type: Number, default: 0 },
    heals: { type: Number, default: 0 },
  },

  // Activité Discord
  activity: {
    messagesSent: { type: Number, default: 0 },
    voiceTime: { type: Number, default: 0 }, // en minutes
    lastMessageReward: { type: Date }, // Last message reward timestamp (15s cooldown)
    lastVoiceReward: { type: Date }, // Last voice reward timestamp (30 min cooldown)
  },

  // Économie
  economy: {
    coins: { type: Number, default: 0 },
    tickets: { type: Number, default: 0 }, // Gacha tickets
    totalEarned: { type: Number, default: 0 }, // Total gagné depuis le début
    casinoBalance: { type: Number, default: 0 },
  },

  // Combat stats
  combat: {
    hp: { type: Number, default: 100 },
    maxHp: { type: Number, default: 100 },
    shield: { type: Number, default: 0 },
    maxShield: { type: Number, default: 20 }, // Default max shield is 20
    isKO: { type: Boolean, default: false }, // KO status (alive or dead)
    lastKOAt: { type: Date }, // Last KO timestamp
  },

  // Equipped character
  equippedCharacter: {
    characterId: { type: String, default: null },
    equippedAt: { type: Date },
  },

  // Character collection
  characterCollection: [{
    characterId: String,
    obtainedAt: { type: Date, default: Date.now },
    count: { type: Number, default: 1 }, // For duplicates
  }],

  // Unequip cooldown
  lastUnequip: { type: Date },

  // Inventaire
  inventory: [{
    itemId: String,
    itemName: String,
    quantity: { type: Number, default: 1 },
  }],

  // XP et niveau
  xp: { type: Number, default: 0 },
  level: { type: Number, default: 1 },

  // Tickets
  tickets: { type: Number, default: 0 },

  // Active status effects
  activeEffects: [{
    effect: String, // POISON, BURN, REGENERATION, VIRUS, INFECTION
    appliedAt: { type: Date, default: Date.now },
    duration: Number, // in seconds
    tickValue: Number, // damage or healing per tick
    tickInterval: Number, // seconds between ticks
    lastTickAt: { type: Date, default: Date.now }, // last tick timestamp
    channelId: String, // channel where effect was applied (for notifications)
    guildId: String, // guild where effect was applied
  }],

  // Daily rewards
  daily: {
    lastClaimed: { type: Date },
    currentStreak: { type: Number, default: 0 },
    maxStreak: { type: Number, default: 0 },
  },

  // Timestamps
  createdAt: { type: Date, default: Date.now },
  lastUpdated: { type: Date, default: Date.now },
});

// Calculer le KDA
playerSchema.virtual('kda').get(function() {
  const { kills, deaths, assists } = this.stats;
  if (deaths === 0) return (kills + assists).toFixed(2);
  return ((kills + assists) / deaths).toFixed(2);
});

playerSchema.set('toJSON', { virtuals: true });

export const Player = mongoose.model('Player', playerSchema);

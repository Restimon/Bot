import mongoose from 'mongoose';

const playerSchema = new mongoose.Schema({
  userId:   { type: String, required: true, unique: true },
  username: { type: String, required: true },

  // Statistiques de jeu
  stats: {
    damageDealt: { type: Number, default: 0 },
    damageTaken: { type: Number, default: 0 },
    healingDone: { type: Number, default: 0 },
    kills:        { type: Number, default: 0 },
    deaths:       { type: Number, default: 0 },
    assists:      { type: Number, default: 0 },
    // legacy
    damages: { type: Number, default: 0 },
    heals:   { type: Number, default: 0 },
  },

  // Activité Discord
  activity: {
    messagesSent:      { type: Number, default: 0 },
    voiceTime:         { type: Number, default: 0 }, // minutes
    lastMessageReward: { type: Date },
    lastVoiceReward:   { type: Date },
  },

  // Économie
  economy: {
    coins:        { type: Number, default: 0 },
    totalEarned:  { type: Number, default: 0 },
    casinoBalance:{ type: Number, default: 0 },

    // ❌ legacy: ne plus utiliser (gardé pour compat)
    tickets:      { type: Number, default: 0 },
  },

  // ✅ Tickets gacha (source de vérité)
  gachaTickets: { type: Number, default: 0 },

  // Combat
  combat: {
    hp:        { type: Number, default: 100 },
    maxHp:     { type: Number, default: 100 },
    shield:    { type: Number, default: 0 },
    maxShield: { type: Number, default: 20 },
    isKO:      { type: Boolean, default: false },
    lastKOAt:  { type: Date },
  },

  // Équipement/personnage
  equippedCharacter: {
    characterId: { type: String, default: null },
    equippedAt:  { type: Date },
    // image?: string  // si tu veux l’afficher dans les embeds
  },

  // Collection de personnages
  characterCollection: [{
    characterId: { type: String, required: true },
    obtainedAt:  { type: Date, default: Date.now },
    count:       { type: Number, default: 1 },
  }],

  // Cooldown unequip
  lastUnequip: { type: Date },

  // Inventaire (clé = emoji en itemName)
  inventory: [{
    itemId:   { type: String },                  // optionnel
    itemName: { type: String, required: true },  // ex: '🔫'
    quantity: { type: Number, default: 1 },
  }],

  // XP et niveau
  xp:    { type: Number, default: 0 },
  level: { type: Number, default: 1 },

  // ❌ legacy: ancien doublon de tickets (à ne plus utiliser)
  tickets: { type: Number, default: 0 },

  // Effets d’état
  activeEffects: [{
    effect:      String,   // POISON, BURN, REGENERATION, VIRUS, INFECTION
    appliedAt:   { type: Date, default: Date.now },
    duration:    Number,   // sec
    tickValue:   Number,
    tickInterval:Number,   // sec
    lastTickAt:  { type: Date, default: Date.now },
    channelId:   String,
    guildId:     String,
  }],

  // Daily
  daily: {
    lastClaimed:   { type: Date },
    currentStreak: { type: Number, default: 0 },
    maxStreak:     { type: Number, default: 0 },
  },

  // Timestamps
  createdAt:  { type: Date, default: Date.now },
  lastUpdated:{ type: Date, default: Date.now },
});

// KDA virtuel
playerSchema.virtual('kda').get(function () {
  const { kills, deaths, assists } = this.stats;
  if (deaths === 0) return (kills + assists).toFixed(2);
  return ((kills + assists) / deaths).toFixed(2);
});

playerSchema.set('toJSON', { virtuals: true });

export const Player = mongoose.model('Player', playerSchema);

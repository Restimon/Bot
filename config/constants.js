// Bot configuration constants

// GotValis Bot User ID (this should be set to the actual bot's Discord ID)
export const GOTVALIS_BOT_ID = process.env.CLIENT_ID || '1423023018258726974';

// AI Configuration
export const AI_REPLY_CHANCE = 0.15; // 15% chance to reply to messages
export const AI_ALWAYS_REPLY_ON_MENTION = true; // Always reply when mentioned

// GotValis earning rates
export const GOTVALIS_EARNINGS = {
  MESSAGE_REPLY: 1, // Coins per message reply
  DAMAGE_COIN_RATIO: 1, // 1 damage = 1 coin
};

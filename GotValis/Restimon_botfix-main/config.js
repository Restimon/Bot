import dotenv from 'dotenv';
dotenv.config();

export const config = {
  token: process.env.DISCORD_TOKEN,
  clientId: process.env.CLIENT_ID,
  guildId: process.env.GUILD_ID,                    
  mongoUri: process.env.MONGO_URI || process.env.MONGODB_URI, 
  openaiApiKey: process.env.OPENAI_API_KEY,
};

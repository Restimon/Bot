import mongoose from 'mongoose';
import { config } from '../config.js';

export async function connectDatabase() {
  try {
    await mongoose.connect(config.mongoUri);
    console.log('✅ Connecté à MongoDB');
  } catch (error) {
    console.error('❌ Erreur de connexion à MongoDB:', error);
    process.exit(1);
  }
}

import mongoose from 'mongoose';
import { config } from '../config.js';

export async function connectDatabase() {
  const uri =
    config.mongoUri ||
    process.env.MONGODB_URI || // fallback direct Render
    process.env.MONGO_URI;     // fallback alternatif

  if (!uri || typeof uri !== 'string' || !uri.trim()) {
    console.error('❌ URI MongoDB introuvable. Vérifie la variable MONGODB_URI sur Render.');
    process.exit(1);
  }

  try {
    await mongoose.connect(uri, {
      serverSelectionTimeoutMS: 10000,
      maxPoolSize: 10,
    });
    console.log('✅ Connecté à MongoDB');
  } catch (error) {
    console.error('❌ Erreur de connexion à MongoDB:', error);
    process.exit(1);
  }
}

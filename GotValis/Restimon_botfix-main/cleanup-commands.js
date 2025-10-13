import { REST, Routes } from 'discord.js';
import { config } from './config.js';

const rest = new REST().setToken(config.token);

try {
  console.log('🧹 Suppression de toutes les commandes (globales et guild)...');

  // Supprime toutes les commandes globales
  await rest.put(Routes.applicationCommands(config.clientId), { body: [] });
  console.log('✅ Commandes globales supprimées.');

  // Supprime les commandes sur ta guilde principale (si config.guildId existe)
  if (config.guildId) {
    await rest.put(
      Routes.applicationGuildCommands(config.clientId, config.guildId),
      { body: [] }
    );
    console.log(`✅ Commandes de la guilde ${config.guildId} supprimées.`);
  }

  console.log('✨ Nettoyage terminé !');
} catch (error) {
  console.error('❌ Erreur lors du nettoyage:', error);
}

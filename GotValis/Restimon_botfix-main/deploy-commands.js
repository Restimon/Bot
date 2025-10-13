import { REST, Routes } from 'discord.js';
import { readdirSync } from 'fs';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';
import { config } from './config.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const commands = [];

// Charger toutes les commandes
const commandsPath = join(__dirname, 'commands');
const commandFiles = readdirSync(commandsPath).filter(file => file.endsWith('.js'));

for (const file of commandFiles) {
  const filePath = join(commandsPath, file);
  const command = await import(`file://${filePath}`);

  if ('data' in command) {
    commands.push(command.data.toJSON());
    console.log(`✅ Commande ajoutée: ${command.data.name}`);
  }
}

// Déployer les commandes
const rest = new REST().setToken(config.token);

try {
  console.log(`🔄 Déploiement de ${commands.length} commandes slash...`);

  const data = await rest.put(
    Routes.applicationCommands(config.clientId),
    { body: commands },
  );

  console.log(`✅ ${data.length} commandes slash déployées avec succès !`);
} catch (error) {
  console.error('❌ Erreur lors du déploiement:', error);
}

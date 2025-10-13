import { REST, Routes } from 'discord.js';
import { readdirSync } from 'fs';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';
import { config } from './config.js'; // charge .env (token, clientId, etc.)

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const GUILD_ID = process.env.GUILD_ID; // <- optionnel pour déploiement instantané sur un serveur
const commands = [];

// Charger toutes les commandes
const commandsPath = join(__dirname, 'commands');
const commandFiles = readdirSync(commandsPath).filter(file => file.endsWith('.js'));

for (const file of commandFiles) {
  const filePath = join(commandsPath, file);
  const mod = await import(`file://${filePath}`);

  if ('data' in mod) {
    commands.push(mod.data.toJSON());
    console.log(`✅ Commande ajoutée: ${mod.data.name}`);
  } else {
    console.warn(`⚠️  Fichier ${file} ignoré (pas de "data")`);
  }
}

// Sanity checks
if (!config.token) throw new Error('DISCORD_TOKEN manquant');
if (!config.clientId) throw new Error('CLIENT_ID manquant');
if (commands.length === 0) console.warn('ℹ️ Aucune commande à déployer.');

// Déployer les commandes
const rest = new REST().setToken(config.token);

try {
  console.log(`🔄 Déploiement de ${commands.length} commande(s) (${GUILD_ID ? 'guilde' : 'global'})...`);

  const route = GUILD_ID
    ? Routes.applicationGuildCommands(config.clientId, GUILD_ID) // instantané
    : Routes.applicationCommands(config.clientId);               // global (propagation plus lente)

  const data = await rest.put(route, { body: commands });

  console.log(`✅ ${Array.isArray(data) ? data.length : 0} commande(s) déployée(s) avec succès !`);
  if (!GUILD_ID) {
    console.log('⏳ Déploiement global : l’apparition peut prendre un moment côté Discord.');
  } else {
    console.log(`⚡ Déploiement de guilde instantané sur GUILD_ID=${GUILD_ID}`);
  }
} catch (error) {
  console.error('❌ Erreur lors du déploiement:', error);
  process.exit(1);
}

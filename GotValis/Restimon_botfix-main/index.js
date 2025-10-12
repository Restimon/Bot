import { Client, Collection, GatewayIntentBits } from 'discord.js';
import { readdirSync } from 'fs';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';
import { config } from './config.js';
import { connectDatabase } from './database/connection.js';
import { startStatusEffectTicker } from './utils/statusEffectTicker.js';
import { startVoiceRewardTicker } from './events/voiceStateUpdate.js';
import { startLeaderboardTicker } from './utils/leaderboard.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

// Créer le client Discord
const client = new Client({
  intents: [
    GatewayIntentBits.Guilds,
    GatewayIntentBits.GuildMembers,
    GatewayIntentBits.GuildMessages,
    GatewayIntentBits.MessageContent,
    GatewayIntentBits.GuildVoiceStates,
  ],
});

// Collection pour stocker les commandes
client.commands = new Collection();

// Charger les commandes
const commandsPath = join(__dirname, 'commands');
const commandFiles = readdirSync(commandsPath).filter(file => file.endsWith('.js'));

for (const file of commandFiles) {
  const filePath = join(commandsPath, file);
  const command = await import(`file://${filePath}`);

  if ('data' in command && 'execute' in command) {
    client.commands.set(command.data.name, command);
    console.log(`✅ Commande chargée: ${command.data.name}`);
  } else {
    console.log(`⚠️ La commande ${file} est incomplète (manque data ou execute)`);
  }
}

// Charger les événements
const eventsPath = join(__dirname, 'events');
const eventFiles = readdirSync(eventsPath).filter(file => file.endsWith('.js'));

for (const file of eventFiles) {
  const filePath = join(eventsPath, file);
  const event = await import(`file://${filePath}`);

  if (event.once) {
    client.once(event.name, (...args) => event.execute(...args));
  } else {
    client.on(event.name, (...args) => event.execute(...args));
  }
  console.log(`✅ Événement chargé: ${event.name}`);
}

// Connexion à la base de données et au bot
async function start() {
  try {
    await connectDatabase();
    await client.login(config.token);

    // Start tickers after bot is ready
    client.once('ready', () => {
      startStatusEffectTicker(client);
      startVoiceRewardTicker(client);
      startLeaderboardTicker(client);
    });
  } catch (error) {
    console.error('❌ Erreur de démarrage:', error);
    process.exit(1);
  }
}

start();

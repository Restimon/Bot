import { Client, Collection, GatewayIntentBits } from 'discord.js';
import { readdirSync } from 'fs';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';
import { config } from './config.js';
import { connectDatabase } from './database/connection.js';
import { startStatusEffectTicker } from './utils/statusEffectTicker.js';
import { startVoiceRewardTicker } from './events/voiceStateUpdate.js';
import { startLeaderboardTicker } from './utils/leaderboard.js';
import { ActivitySession } from './database/models/ActivitySession.js'; // ← AJOUT

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

// ───────────────────────────────────────────────────────────────
// Réconciliation des sessions vocales "ouvertes" (bot redémarré)
// ───────────────────────────────────────────────────────────────
async function reconcileOpenVoiceSessions(client) {
  console.log('🔎 Vérification des sessions vocales incomplètes...');
  const opens = await ActivitySession.find({ type: 'voice', endTime: null });

  for (const s of opens) {
    try {
      const guild =
        client.guilds.cache.get(s.guildId) ||
        (await client.guilds.fetch(s.guildId).catch(() => null));

      const member =
        guild
          ? (guild.members.cache.get(s.userId) ||
             (await guild.members.fetch(s.userId).catch(() => null)))
          : null;

      const stillInVoice = !!member?.voice?.channelId;

      if (!stillInVoice) {
        const now = new Date();
        s.endTime = now;
        s.duration = Math.max(1, Math.round((now - s.startTime) / 60000));
        await s.save();
        console.log(`✅ Fermeture d’une session vocale orpheline de ${s.userId} (${s.duration} min)`);
      }
    } catch (e) {
      console.error('reconcileOpenVoiceSessions error:', e);
    }
  }
}

// Créer le client Discord
const client = new Client({
  intents: [
    GatewayIntentBits.Guilds,
    GatewayIntentBits.GuildMembers,
    GatewayIntentBits.GuildMessages,
    GatewayIntentBits.MessageContent,
    GatewayIntentBits.GuildVoiceStates, // requis pour suivre la voix
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
    client.once('ready', async () => {
      console.log(`✅ Connecté en tant que ${client.user.tag}`);

      // ⚠️ Rattrape les sessions vocales ouvertes avant de lancer les tickers
      await reconcileOpenVoiceSessions(client);

      // Tes tickers existants
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

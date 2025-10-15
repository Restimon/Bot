import { Client, Collection, GatewayIntentBits } from 'discord.js';
import { readdirSync } from 'fs';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';
import { config } from './config.js';
import { connectDatabase } from './database/connection.js';
import { startStatusEffectTicker } from './utils/statusEffectTicker.js';
import { startVoiceRewardTicker } from './events/voiceStateUpdate.js';
import { startLeaderboardTicker } from './utils/leaderboard.js';
import { ActivitySession } from './database/models/ActivitySession.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

async function reconcileOpenVoiceSessions(client) {
  const opens = await ActivitySession.find({ type: 'voice', endTime: null });
  for (const s of opens) {
    try {
      const guild = client.guilds.cache.get(s.guildId) || await client.guilds.fetch(s.guildId).catch(() => null);
      const member = guild ? (guild.members.cache.get(s.userId) || await guild.members.fetch(s.userId).catch(() => null)) : null;
      const stillInVoice = !!member?.voice?.channelId;
      if (!stillInVoice) {
        const now = new Date();
        s.endTime = now;
        s.duration = Math.max(1, Math.round((now - s.startTime) / 60000));
        await s.save();
      }
    } catch {}
  }
}

const client = new Client({
  intents: [
    GatewayIntentBits.Guilds,
    GatewayIntentBits.GuildMembers,
    GatewayIntentBits.GuildMessages,
    GatewayIntentBits.MessageContent,
    GatewayIntentBits.GuildVoiceStates,
  ],
});

client.commands = new Collection();

const commandsPath = join(__dirname, 'commands');
const commandFiles = readdirSync(commandsPath).filter(file => file.endsWith('.js'));

for (const file of commandFiles) {
  const filePath = join(commandsPath, file);
  const mod = await import(`file://${filePath}`);

  if (mod?.data && mod?.execute) {
    client.commands.set(mod.data.name, mod);
    console.log(`✅ Commande chargée: ${mod.data.name}`);
    continue;
  }

  if (Array.isArray(mod?.commands)) {
    for (const cmd of mod.commands) {
      if (cmd?.data && cmd?.execute) {
        client.commands.set(cmd.data.name, cmd);
        console.log(`✅ Commande chargée: ${cmd.data.name}`);
      } else {
        console.log(`⚠️ Une commande dans ${file} est incomplète (manque data ou execute)`);
      }
    }
    continue;
  }

  console.log(`⚠️ La commande ${file} est incomplète (manque data/execute ou commands[])`);
}

const eventsPath = join(__dirname, 'events');
const eventFiles = readdirSync(eventsPath).filter(file => file.endsWith('.js'));

for (const file of eventFiles) {
  const filePath = join(eventsPath, file);
  const event = await import(`file://${filePath}`);
  if (event.once) client.once(event.name, (...args) => event.execute(...args));
  else client.on(event.name, (...args) => event.execute(...args));
  console.log(`✅ Événement chargé: ${event.name}`);
}

async function start() {
  try {
    await connectDatabase();
    await client.login(config.token);

    client.once('ready', async () => {
      await reconcileOpenVoiceSessions(client);
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

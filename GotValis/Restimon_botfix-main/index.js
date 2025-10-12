import { Client, Collection, GatewayIntentBits } from 'discord.js';
import { readdirSync } from 'fs';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';
import { config } from './config.js';
import { connectDatabase } from './database/connection.js';
import { startStatusEffectTicker } from './utils/statusEffectTicker.js';
import { startVoiceRewardTicker } from './events/voiceStateUpdate.js';
import { startLeaderboardTicker } from './utils/leaderboard.js';

// 🔥 AJOUTS : intégration avec le système d’IA (sanctions / HP)
import { setPunishHandler, setHpProvider } from './utils/ai-reply.js';
import { Player } from './database/models/Player.js';

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

    // ─────────────────────────────────────────────
    // 🔥 LIAISON IA ↔ SYSTÈME DE JEU (sanctions)
    // ─────────────────────────────────────────────
    setHpProvider(async (userId) => {
      const player = await Player.findOne({ userId }).lean();
      return player?.combat?.hp ?? 100; // valeur par défaut
    });

    setPunishHandler(async (userId, dmg, reason, message) => {
      const player = await Player.findOneAndUpdate(
        { userId },
        { $setOnInsert: { userId, username: message?.author?.username ?? 'Unknown' } },
        { upsert: true, new: true }
      );

      const before = player.combat?.hp ?? 100;
      const after = Math.max(0, before - Number(dmg || 0));

      // Mets à jour la fiche du joueur
      player.combat = {
        ...(player.combat || {}),
        hp: after,
        maxHp: player.combat?.maxHp ?? 100,
        shield: player.combat?.shield ?? 0,
        maxShield: player.combat?.maxShield ?? 20,
        isKO: after <= 0 ? true : (player.combat?.isKO ?? false),
        lastKOAt: after <= 0 ? new Date() : player.combat?.lastKOAt,
      };

      player.stats = {
        ...(player.stats || {}),
        damageTaken: (player.stats?.damageTaken ?? 0) + Number(dmg || 0),
      };

      player.lastUpdated = new Date();
      await player.save();

      console.log(`💢 Sanction appliquée à ${player.username}: -${dmg} HP (${before} → ${after})`);

      return { hpBefore: before, hpAfter: after };
    });

    // ─────────────────────────────────────────────
    // Connexion du bot
    // ─────────────────────────────────────────────
    await client.login(config.token);

    // Lancer les tickers une fois prêt
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

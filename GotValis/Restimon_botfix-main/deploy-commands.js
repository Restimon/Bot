import { REST, Routes } from 'discord.js';
import { readdirSync } from 'fs';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';
import { config } from './config.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const commands = [];
const commandsPath = join(__dirname, 'commands');
const files = readdirSync(commandsPath).filter(f => f.endsWith('.js'));

for (const file of files) {
  const filePath = join(commandsPath, file);
  try {
    const mod = await import(`file://${filePath}`);
    if (mod?.data?.toJSON) {
      commands.push(mod.data.toJSON());
      console.log(`✅ ajout: ${mod.data.name}`);
    } else {
      console.warn(`⚠️ ignorée (pas de data.toJSON): ${file}`);
    }
  } catch (e) {
    console.error(`❌ import échoué: ${file}`, e);
  }
}

const rest = new REST().setToken(config.token);
console.log(`🌍 Déploiement global de ${commands.length} commandes...`);
const data = await rest.put(Routes.applicationCommands(config.clientId), { body: commands });
console.log(`✅ ${data.length} commandes globales actives`);

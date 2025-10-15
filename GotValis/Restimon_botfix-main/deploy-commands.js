import { REST, Routes } from 'discord.js';
import { readdirSync } from 'fs';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';
import { config } from './config.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const defs = [];
const commandsPath = join(__dirname, 'commands');
const commandFiles = readdirSync(commandsPath).filter(f => f.endsWith('.js'));

for (const file of commandFiles) {
  const filePath = join(commandsPath, file);
  const mod = await import(`file://${filePath}`);

  if (mod?.data?.toJSON) {
    defs.push(mod.data.toJSON());
    console.log(`✅ Commande ajoutée: ${mod.data.name}`);
    continue;
  }
  if (Array.isArray(mod?.commands)) {
    for (const cmd of mod.commands) {
      if (cmd?.data?.toJSON) {
        defs.push(cmd.data.toJSON());
        console.log(`✅ Commande ajoutée: ${cmd.data.name}`);
      } else {
        console.log(`⚠️ Une commande dans ${file} est incomplète`);
      }
    }
    continue;
  }
  console.log(`⚠️ ${file}: pas de data/commands`);
}

const rest = new REST().setToken(config.token);

try {
  console.log(`🔄 Déploiement de ${defs.length} commandes slash...`);
  await rest.put(Routes.applicationCommands(config.clientId), { body: defs });
  console.log(`✅ Déploiement global OK (${defs.length})`);
  // Pour un serveur de test instantané, décommente si tu as un GUILD_ID:
  // await rest.put(Routes.applicationGuildCommands(config.clientId, config.guildId), { body: defs });
} catch (error) {
  console.error('❌ Erreur lors du déploiement:', error);
}

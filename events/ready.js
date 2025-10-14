import { Events, ActivityType } from 'discord.js';

export const name = Events.ClientReady;
export const once = true;

export async function execute(client) {
  console.log(`✅ Bot connecté en tant que ${client.user.tag}`);
  console.log(`📊 Serveurs: ${client.guilds.cache.size}`);
  console.log(`👥 Utilisateurs: ${client.users.cache.size}`);

  // Définir l'activité du bot
  client.user.setPresence({
    activities: [{
      name: '/info pour voir vos stats',
      type: ActivityType.Playing,
    }],
    status: 'online',
  });
}

import mongoose from 'mongoose';
import { config } from '../config.js';
import { Player } from '../database/models/Player.js';

async function migrateTickets() {
  await mongoose.connect(config.mongoUri, { dbName: config.mongoDbName });

  let migratedCount = 0;
  const players = await Player.find({});

  for (const p of players) {
    let add = 0;

    // 1️⃣ Si le joueur avait l’ancien champ tickets
    if (typeof p.economy?.tickets === 'number' && p.economy.tickets > 0) {
      add += p.economy.tickets;
      p.economy.tickets = 0; // on vide l’ancien champ
    }

    // 2️⃣ Si le joueur a un champ direct "tickets" (ancien format)
    if (typeof p.tickets === 'number' && p.tickets > 0) {
      add += p.tickets;
      p.tickets = 0;
    }

    // 3️⃣ Si l’inventaire contient un item “Ticket” ou “🎟️”
    if (Array.isArray(p.inventory)) {
      let keep = [];
      for (const item of p.inventory) {
        if (/ticket/i.test(item.itemName)) {
          add += item.quantity || 1;
        } else {
          keep.push(item);
        }
      }
      p.inventory = keep;
    }

    // 4️⃣ On fusionne dans gachaTickets
    if (add > 0) {
      p.gachaTickets = (p.gachaTickets || 0) + add;
      migratedCount++;
    }

    await p.save();
  }

  console.log(`✅ Migration terminée : ${migratedCount} joueurs migrés vers gachaTickets.`);
  await mongoose.disconnect();
}

migrateTickets().catch(err => {
  console.error('❌ Erreur migration tickets :', err);
  process.exit(1);
});

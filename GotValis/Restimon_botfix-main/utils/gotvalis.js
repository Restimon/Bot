// GotValis bot utilities
import { Player } from '../database/models/Player.js';
import { GOTVALIS_BOT_ID } from '../config/constants.js';

// Get or create GotValis bot player
export async function getGotValisPlayer() {
  let gotvalis = await Player.findOne({ userId: GOTVALIS_BOT_ID });

  if (!gotvalis) {
    gotvalis = await Player.create({
      userId: GOTVALIS_BOT_ID,
      username: 'GotValis',
      economy: {
        coins: 0,
        totalEarned: 0,
      },
    });
    console.log('✅ GotValis bot player created');
  }

  return gotvalis;
}

// Award coins to GotValis
export async function awardGotValis(amount, reason = 'Unknown') {
  const gotvalis = await getGotValisPlayer();
  gotvalis.economy.coins += amount;
  gotvalis.economy.totalEarned += amount;
  gotvalis.lastUpdated = new Date();
  await gotvalis.save();
  console.log(`💰 GotValis earned ${amount} coins (${reason})`);
}

// Deduct coins from GotValis
export async function deductGotValis(amount, reason = 'Unknown') {
  const gotvalis = await getGotValisPlayer();
  gotvalis.economy.coins -= amount;
  gotvalis.lastUpdated = new Date();
  await gotvalis.save();
  console.log(`💸 GotValis lost ${amount} coins (${reason})`);
}

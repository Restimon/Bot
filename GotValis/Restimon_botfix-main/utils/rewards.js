import { generateRandomItem } from './items.js';

// Status effects available in Special Supply
export const STATUS_EFFECTS = {
  POISON: { name: 'Poison', emoji: '🧪', duration: 60, damage: 2 },
  BURN: { name: 'Brûlure', emoji: '🔥', duration: 45, damage: 3 },
  REGENERATION: { name: 'Régénération', emoji: '💚', duration: 60, heal: 2 },
  VIRUS: { name: 'Virus', emoji: '🦠', duration: 90, damage: 1 },
  INFECTION: { name: 'Infection', emoji: '💉', duration: 75, damage: 2 },
};

// Generate a random reward for Special Supply
export function generateSpecialSupplyReward() {
  const rewardTypes = [
    { type: 'item', weight: 40 },
    { type: 'ticket', weight: 15 },
    { type: 'coins', weight: 25 },
    { type: 'damage', weight: 10 },
    { type: 'heal', weight: 8 },
    { type: 'status_effect', weight: 2 },
  ];

  const totalWeight = rewardTypes.reduce((sum, r) => sum + r.weight, 0);
  let random = Math.random() * totalWeight;

  let rewardType = 'item';
  for (const reward of rewardTypes) {
    random -= reward.weight;
    if (random <= 0) {
      rewardType = reward.type;
      break;
    }
  }

  switch (rewardType) {
    case 'item': {
      // 1-2 items of the same type
      const item = generateRandomItem();
      const quantity = Math.random() > 0.5 ? 2 : 1;
      return {
        type: 'item',
        emoji: item.emoji,
        description: `${item.emoji} ${item.name}${quantity > 1 ? ` x${quantity}` : ''}`,
        details: { ...item, quantity },
      };
    }

    case 'ticket': {
      return {
        type: 'ticket',
        emoji: '🎫',
        description: '🎫 1 Ticket',
        details: { quantity: 1 },
      };
    }

    case 'coins': {
      const amount = Math.floor(Math.random() * 51) + 20; // 20-70
      return {
        type: 'coins',
        emoji: '🪙',
        description: `🪙 ${amount} GotCoins`,
        details: { amount },
      };
    }

    case 'damage': {
      const damage = Math.floor(Math.random() * 10) + 1; // 1-10
      return {
        type: 'damage',
        emoji: '💥',
        description: `💥 ${damage} dégâts (PV: 4)`,
        details: { amount: damage, hp: 4 },
      };
    }

    case 'heal': {
      const heal = Math.floor(Math.random() * 10) + 1; // 1-10
      const critChance = Math.random() > 0.8 ? 20 : 0; // 20% chance of crit
      const critText = critChance > 0 ? ` (Crit ${critChance}%)` : '';
      return {
        type: 'heal',
        emoji: '💚',
        description: `💚 Restaure ${heal} PV${critText}`,
        details: { amount: heal, critChance },
      };
    }

    case 'status_effect': {
      const effects = Object.keys(STATUS_EFFECTS);
      const effectKey = effects[Math.floor(Math.random() * effects.length)];
      const effect = STATUS_EFFECTS[effectKey];
      return {
        type: 'status_effect',
        emoji: effect.emoji,
        description: `${effect.emoji} ${effect.name} (${effect.duration}s)`,
        details: { effectKey, ...effect },
      };
    }

    default:
      return generateSpecialSupplyReward(); // Fallback
  }
}

// Apply reward to player
export async function applyRewardToPlayer(Player, userId, reward) {
  const update = {};

  switch (reward.type) {
    case 'item':
      update.$push = {
        inventory: {
          itemId: reward.details.itemId,
          itemName: reward.details.name,
          quantity: reward.details.quantity,
        }
      };
      update.$inc = {
        'economy.coins': reward.details.value * reward.details.quantity,
        'economy.totalEarned': reward.details.value * reward.details.quantity,
      };
      break;

    case 'ticket':
      update.$inc = { tickets: 1 };
      break;

    case 'coins':
      update.$inc = {
        'economy.coins': reward.details.amount,
        'economy.totalEarned': reward.details.amount,
      };
      break;

    case 'damage':
      update.$inc = { 'stats.damages': reward.details.amount };
      break;

    case 'heal':
      update.$inc = { 'stats.heals': reward.details.amount };
      break;

    case 'status_effect':
      // Store active status effects
      update.$push = {
        activeEffects: {
          effect: reward.details.effectKey,
          appliedAt: new Date(),
          duration: reward.details.duration,
        }
      };
      break;
  }

  await Player.findOneAndUpdate(
    { userId },
    { ...update, lastUpdated: new Date() },
    { upsert: true }
  );
}

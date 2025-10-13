// Status effect definitions with tick mechanics

export const STATUS_EFFECTS = {
  POISON: {
    name: 'Poison',
    emoji: '🧪',
    type: 'damage',
    tickValue: 1, // 1 PV per tick
    tickInterval: 1800, // 30 minutes in seconds
    duration: 10800, // 3 hours in seconds
    description: 'Poison',
    tickMessage: (username, damage, currentHP) =>
      `🧪 <@${username}> subit **1 dégât** *(Poison)*.\n❤️ **${currentHP + damage}** - **1** 🧪 = ❤️ **${currentHP}**`,
  },
  VIRUS: {
    name: 'Virus',
    emoji: '🦠',
    type: 'damage',
    tickValue: 5, // 5 PV per tick
    tickInterval: 3600, // 1 hour in seconds
    duration: 21600, // 6 hours in seconds
    transferable: true, // Can transfer on attack
    description: 'Virus',
    tickMessage: (username, damage, currentHP) =>
      `🦠 <@${username}> subit **5 dégâts** *(Virus)*.\n❤️ **${currentHP + damage}** - **5** 🦠 = ❤️ **${currentHP}**`,
  },
  INFECTION: {
    name: 'Infection',
    emoji: '🧟',
    type: 'damage',
    tickValue: 5, // 5 PV per tick
    tickInterval: 1800, // 30 minutes in seconds
    duration: 10800, // 3 hours in seconds
    attackDamage: 3, // +3 PV damage on attack
    infectChance: 0.25, // 25% chance to infect on attack
    infectDamage: 5, // 5 PV damage on successful infection
    description: 'Infection',
    tickMessage: (username, damage, currentHP) =>
      `🧟 <@${username}> subit **5 dégâts** *(Infection)*.\n❤️ **${currentHP + damage}** - **5** 🧟 = ❤️ **${currentHP}**`,
  },
  BURN: {
    name: 'Brûlure',
    emoji: '🔥',
    type: 'damage',
    tickValue: 1, // 1 PV per tick
    tickInterval: 900, // 15 minutes in seconds
    duration: 3600, // 1 hour in seconds
    description: 'Brûlure',
    tickMessage: (username, damage, currentHP) =>
      `🔥 <@${username}> subit **1 dégât** *(Brûlure)*.\n❤️ **${currentHP + damage}** - **1** 🔥 = ❤️ **${currentHP}**`,
  },
  REGENERATION: {
    name: 'Régénération',
    emoji: '💕',
    type: 'heal',
    tickValue: 2, // +2 PV per tick
    tickInterval: 1800, // 30 minutes in seconds
    duration: 18000, // 5 hours in seconds
    description: 'Régénération',
    tickMessage: (username, heal, currentHP) =>
      `💕 <@${username}> récupère **2 PV** *(💕)*.\n❤️ **${currentHP - heal}** + **2** 💕 = ❤️ **${currentHP}**`,
  },
};

// Status effect item emojis
export const STATUS_EFFECT_ITEMS = {
  '☠️': 'POISON',
  '💉': 'INFECTION',
  '🦠': 'VIRUS',
  '🔥': 'BURN', // Can apply burn when used as offensive
  '💕': 'REGENERATION', // Special regeneration item
  '🌿': 'REGENERATION', // Herbe can apply regeneration
};

// Get status effect by name
export function getStatusEffect(effectName) {
  return STATUS_EFFECTS[effectName];
}

// Get status effect by item emoji
export function getStatusEffectByItem(itemEmoji) {
  const effectName = STATUS_EFFECT_ITEMS[itemEmoji];
  return effectName ? STATUS_EFFECTS[effectName] : null;
}

// Check if item applies a status effect
export function isStatusEffectItem(itemEmoji) {
  return itemEmoji in STATUS_EFFECT_ITEMS;
}

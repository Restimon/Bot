// Healing items for /heal command
export const HEALING_ITEMS = {
  '💊': {
    name: 'Pilule',
    type: 'instant',
    healAmount: 10,
    description: 'Soin',
    emoji: '💊',
  },
  '🧪': {
    name: 'Potion',
    type: 'instant',
    healAmount: 25,
    description: 'Soin',
    emoji: '🧪',
  },
  '💖': {
    name: 'Cœur',
    type: 'instant',
    healAmount: 15,
    description: 'Soin',
    emoji: '💊',
  },
  '🍎': {
    name: 'Pomme',
    type: 'instant',
    healAmount: 10,
    description: 'Soin',
    emoji: '💊',
  },
  '🍖': {
    name: 'Viande',
    type: 'instant',
    healAmount: 20,
    description: 'Soin',
    emoji: '💊',
  },
  '🌿': {
    name: 'Herbe',
    type: 'instant',
    healAmount: 5,
    description: 'Soin',
    emoji: '💊',
  },
  '💡': {
    name: 'Ampoule',
    type: 'instant',
    healAmount: 5,
    description: 'Soin',
    emoji: '💊',
  },
  '🍊': {
    name: 'Orange',
    type: 'instant',
    healAmount: 12,
    description: 'Soin',
    emoji: '💊',
  },
};

// Shield items for /heal command
export const SHIELD_ITEMS = {
  '🛡️': {
    name: 'Bouclier',
    type: 'shield',
    shieldAmount: 20,
    description: 'Soin',
    emoji: '💊',
  },
  '⚙️': {
    name: 'Engrenage',
    type: 'shield',
    shieldAmount: 15,
    description: 'Soin',
    emoji: '💊',
  },
};

// Check if item is a healing item
export function isHealingItem(emoji) {
  return emoji in HEALING_ITEMS || emoji in SHIELD_ITEMS;
}

// Get healing item data
export function getHealingItem(emoji) {
  return HEALING_ITEMS[emoji] || SHIELD_ITEMS[emoji] || null;
}

// Item categories and descriptions for inventory display

export const ITEM_CATEGORIES = {
  // Fight items (offensive) - Spec section 5
  fight: {
    '❄️': {
      name: 'Glace',
      description: '[Dégâts 1]',
      damage: 1,
      critChance: 0.20,
      critMultiplier: 2
    },
    '⚔️': {
      name: 'Épée',
      description: '[Dégâts 3]',
      damage: 3,
      critChance: 0.175,
      critMultiplier: 2
    },
    '🔥': {
      name: 'Feu',
      description: '[Dégâts 5 + Brûlure]',
      damage: 5,
      critChance: 0.15,
      critMultiplier: 2,
      burnChance: 0.30,
      status: 'BURN'
    },
    '⚡': {
      name: 'Éclair',
      description: '[Dégâts 10]',
      damage: 10,
      critChance: 0.125,
      critMultiplier: 2
    },
    '🔫': {
      name: 'Pistolet',
      description: '[Dégâts 15]',
      damage: 15,
      critChance: 0.10,
      critMultiplier: 2
    },
    '🧨': {
      name: 'Dynamite',
      description: '[Dégâts 20]',
      damage: 20,
      critChance: 0.08,
      critMultiplier: 2
    },
    '☠️': {
      name: 'Crâne',
      description: '[Dégâts 24 + AoE]',
      damage: 24,
      critChance: 0.05,
      critMultiplier: 2,
      aoe: true,
      aoeDamage: 12,
      aoeTargets: 2
    },
    '🦠': {
      name: 'Virus',
      description: '[Dégâts 5 + Virus transferable]',
      damage: 5,
      critChance: 0.03,
      critMultiplier: 2,
      status: 'VIRUS',
      dotDamage: 5,
      transferable: true
    },
    '🧪': {
      name: 'Poison',
      description: '[Poison DOT + Réduction -1]',
      damage: 0,
      critChance: 0.025,
      critMultiplier: 2,
      status: 'POISON',
      damageReduction: 1,
      dotMultiplier: 2
    },
    '🧟': {
      name: 'Infection',
      description: '[Infection DOT + Attaque]',
      damage: 0,
      critChance: 0,
      critMultiplier: 1,
      status: 'INFECTION',
      infectChance: 0.25,
      infectDamage: 5
    },
  },

  // Heal items - Spec section 5
  heal: {
    '🍀': {
      name: 'Trèfle',
      description: '[Soigne 1 PV]',
      heal: 1,
      critChance: 0.20,
      critMultiplier: 2
    },
    '🩹': {
      name: 'Bandage',
      description: '[Soigne 5 PV]',
      heal: 5,
      critChance: 0.15,
      critMultiplier: 2
    },
    '🩸': {
      name: 'Sang',
      description: '[Soigne 10 PV]',
      heal: 10,
      critChance: 0.10,
      critMultiplier: 2
    },
    '💊': {
      name: 'Pilule',
      description: '[Soigne 15 PV]',
      heal: 15,
      critChance: 0.05,
      critMultiplier: 2
    },
    '💕': {
      name: 'Régénération',
      description: '[Régén +2 PV/30min sur 5h]',
      heal: 0,
      critChance: 0.02,
      critMultiplier: 2,
      status: 'REGENERATION'
    },
  },

  // Use items (utility) - Spec section 5
  use: {
    '🎁': {
      name: 'Cadeau',
      description: '[Boîte: 3 objets ou 2 objets + 10-30 GC]',
      special: 'gift_box',
      itemCount: 3,
      coinsMin: 10,
      coinsMax: 30
    },
    '🔍': {
      name: 'Loupe',
      description: '[Vole un objet aléatoire]',
      special: 'steal'
    },
    '💉': {
      name: 'Seringue',
      description: '[Soigne virus/poison/infection]',
      special: 'cure_status'
    },
    '🛡️': {
      name: 'Bouclier',
      description: '[+20 PB]',
      shield: 20
    },
    '👟': {
      name: 'Chaussures',
      description: '[Double esquive 6h]',
      special: 'double_dodge',
      duration: 6 * 60 * 60 * 1000 // 6 hours in ms
    },
    '🪖': {
      name: 'Casque',
      description: '[Réduction -50% dégâts 8h]',
      special: 'damage_reduction',
      reduction: 0.5,
      duration: 8 * 60 * 60 * 1000 // 8 hours in ms
    },
    '⭐': {
      name: 'Étoile',
      description: '[Immunité totale 5h]',
      special: 'immunity',
      duration: 5 * 60 * 60 * 1000 // 5 hours in ms
    },
  },
};

// Get item category
export function getItemCategory(emoji) {
  for (const [category, items] of Object.entries(ITEM_CATEGORIES)) {
    if (emoji in items) {
      return { category, ...items[emoji] };
    }
  }
  return null;
}

// Get all items by category
export function getItemsByCategory() {
  return ITEM_CATEGORIES;
}

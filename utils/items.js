// Système d'items avec raretés
export const ITEM_RARITIES = {
  COMMON: {
    name: 'Commun',
    color: '#95A5A6',
    weight: 50,
    valueMultiplier: 1,
  },
  UNCOMMON: {
    name: 'Peu commun',
    color: '#2ECC71',
    weight: 30,
    valueMultiplier: 2,
  },
  RARE: {
    name: 'Rare',
    color: '#3498DB',
    weight: 12,
    valueMultiplier: 5,
  },
  EPIC: {
    name: 'Épique',
    color: '#9B59B6',
    weight: 6,
    valueMultiplier: 10,
  },
  LEGENDARY: {
    name: 'Légendaire',
    color: '#F1C40F',
    weight: 2,
    valueMultiplier: 20,
  },
};

export const ITEM_TYPES = [
  { id: 'wood', name: 'Bois', emoji: '🪵', baseValue: 10 },
  { id: 'stone', name: 'Pierre', emoji: '🪨', baseValue: 15 },
  { id: 'iron', name: 'Fer', emoji: '⚙️', baseValue: 25 },
  { id: 'gold', name: 'Or', emoji: '🪙', baseValue: 50 },
  { id: 'diamond', name: 'Diamant', emoji: '💎', baseValue: 100 },
  { id: 'emerald', name: 'Émeraude', emoji: '💚', baseValue: 150 },
  { id: 'potion', name: 'Potion', emoji: '🧪', baseValue: 30 },
  { id: 'sword', name: 'Épée', emoji: '⚔️', baseValue: 75 },
  { id: 'shield', name: 'Bouclier', emoji: '🛡️', baseValue: 60 },
  { id: 'bow', name: 'Arc', emoji: '🏹', baseValue: 65 },
  { id: 'meat', name: 'Viande', emoji: '🍖', baseValue: 20 },
  { id: 'apple', name: 'Pomme', emoji: '🍎', baseValue: 5 },
  { id: 'key', name: 'Clé', emoji: '🔑', baseValue: 40 },
  { id: 'chest', name: 'Coffre', emoji: '📦', baseValue: 80 },
  { id: 'scroll', name: 'Parchemin', emoji: '📜', baseValue: 35 },
];

// Générer une rareté aléatoire basée sur les poids
export function generateRarity() {
  const totalWeight = Object.values(ITEM_RARITIES).reduce((sum, r) => sum + r.weight, 0);
  let random = Math.random() * totalWeight;

  for (const [key, rarity] of Object.entries(ITEM_RARITIES)) {
    random -= rarity.weight;
    if (random <= 0) {
      return key;
    }
  }

  return 'COMMON';
}

// Générer un item aléatoire
export function generateRandomItem() {
  const rarity = generateRarity();
  const rarityData = ITEM_RARITIES[rarity];
  const itemType = ITEM_TYPES[Math.floor(Math.random() * ITEM_TYPES.length)];

  const value = Math.floor(itemType.baseValue * rarityData.valueMultiplier);

  return {
    itemId: `${itemType.id}_${rarity.toLowerCase()}_${Date.now()}`,
    name: `${itemType.name} ${rarityData.name}`,
    rarity: rarity,
    emoji: itemType.emoji,
    value: value,
    baseType: itemType.id,
  };
}

// Obtenir la couleur d'une rareté
export function getRarityColor(rarity) {
  return ITEM_RARITIES[rarity]?.color || '#95A5A6';
}

// Obtenir le nom d'une rareté
export function getRarityName(rarity) {
  return ITEM_RARITIES[rarity]?.name || 'Commun';
}

// Offensive items for combat system
export const OFFENSIVE_ITEMS = {
  '🧨': {
    name: 'Dynamite',
    baseDamage: 35,
    critChance: 0.15,
    critMultiplier: 1.5,
    description: 'dynamite explosive',
    action: 'a lancé une',
  },
  '🔥': {
    name: 'Flamme',
    baseDamage: 25,
    critChance: 0.20,
    critMultiplier: 1.4,
    description: 'boule de feu',
    action: 'a lancé une',
  },
  '❄️': {
    name: 'Glace',
    baseDamage: 20,
    critChance: 0.10,
    critMultiplier: 1.3,
    description: 'lance de glace',
    action: 'a lancé une',
  },
  '⚡': {
    name: 'Éclair',
    baseDamage: 30,
    critChance: 0.25,
    critMultiplier: 1.6,
    description: 'éclair foudroyant',
    action: 'a invoqué un',
  },
  '💣': {
    name: 'Bombe',
    baseDamage: 40,
    critChance: 0.12,
    critMultiplier: 1.5,
    description: 'bombe',
    action: 'a jeté une',
  },
  '🗡️': {
    name: 'Épée',
    baseDamage: 22,
    critChance: 0.18,
    critMultiplier: 1.4,
    description: 'épée',
    action: 'a frappé avec une',
  },
  '🔫': {
    name: 'Pistolet',
    baseDamage: 18,
    critChance: 0.22,
    critMultiplier: 1.3,
    description: 'pistolet',
    action: 'a tiré avec un',
  },
  '🏹': {
    name: 'Arc',
    baseDamage: 15,
    critChance: 0.30,
    critMultiplier: 1.5,
    description: 'arc',
    action: 'a tiré avec un',
  },
  '🪓': {
    name: 'Hache',
    baseDamage: 28,
    critChance: 0.15,
    critMultiplier: 1.6,
    description: 'hache',
    action: 'a frappé avec une',
  },
  '🔨': {
    name: 'Marteau',
    baseDamage: 26,
    critChance: 0.14,
    critMultiplier: 1.5,
    description: 'marteau',
    action: 'a assommé avec un',
  },
};

// Status effect emojis for damage reduction display
export const STATUS_EFFECT_EMOJIS = {
  POISON: '🧪',
  VIRUS: '🦠',
  INFECTION: '💉',
  BURN: '🔥',
};

// Status effect damage reduction
export const STATUS_EFFECT_REDUCTION = {
  POISON: 0.10,    // 10% damage reduction
  VIRUS: 0.15,     // 15% damage reduction
  INFECTION: 0.12, // 12% damage reduction
  BURN: 0.08,      // 8% damage reduction
};

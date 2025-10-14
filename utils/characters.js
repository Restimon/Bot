// Available characters with passive abilities
export const CHARACTERS = {
  'cielya-morn': {
    name: 'Cielya-Morn',
    passive: 'Régénération passive +2 HP/10s',
    image: 'https://i.imgur.com/placeholder.png', // Placeholder
  },
  'shadow-reaper': {
    name: 'Shadow Reaper',
    passive: 'Dégâts critiques +15%',
    image: 'https://i.imgur.com/placeholder2.png',
  },
  'iron-guardian': {
    name: 'Iron Guardian',
    passive: 'Bouclier maximum +25',
    image: 'https://i.imgur.com/placeholder3.png',
  },
  'mystic-healer': {
    name: 'Mystic Healer',
    passive: 'Soins +20%',
    image: 'https://i.imgur.com/placeholder4.png',
  },
  'void-walker': {
    name: 'Void Walker',
    passive: 'Immunité aux effets de statut pendant 5s',
    image: 'https://i.imgur.com/placeholder5.png',
  },
};

export function getCharacterInfo(characterId) {
  return CHARACTERS[characterId] || null;
}

export function getCharactersList() {
  return Object.keys(CHARACTERS).map(id => ({
    id,
    ...CHARACTERS[id],
  }));
}

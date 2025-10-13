// Shop item catalog with buy/sell prices
// Easily configurable for price adjustments

export const CURRENCY_NAME = "GotValis";

export const SHOP_ITEMS = {
  // Format: emoji: { name, buyPrice, sellPrice, description }
  // Prices easily configurable - Spec section 1.8

  // Fight items
  "❄️": { name: "Glace", buyPrice: 2, sellPrice: 1, description: "Inflige 1 dégât - 20% crit" },
  "⚔️": { name: "Épée", buyPrice: 6, sellPrice: 4, description: "Inflige 3 dégâts - 17.5% crit" },
  "🔥": { name: "Feu", buyPrice: 10, sellPrice: 6, description: "Inflige 5 dégâts + brûlure - 15% crit" },
  "⚡": { name: "Éclair", buyPrice: 20, sellPrice: 12, description: "Inflige 10 dégâts - 12.5% crit" },
  "🔫": { name: "Pistolet", buyPrice: 30, sellPrice: 18, description: "Inflige 15 dégâts - 10% crit" },
  "🧨": { name: "Dynamite", buyPrice: 40, sellPrice: 24, description: "Inflige 20 dégâts - 8% crit" },
  "☠️": { name: "Crâne", buyPrice: 50, sellPrice: 30, description: "Inflige 24 + 12 AoE - 5% crit" },
  "🦠": { name: "Virus", buyPrice: 60, sellPrice: 36, description: "Virus transferable - 3% crit" },
  "🧪": { name: "Poison", buyPrice: 55, sellPrice: 33, description: "Poison DOT + réduction -1" },
  "🧟": { name: "Infection", buyPrice: 70, sellPrice: 42, description: "Infection DOT + attaque" },

  // Heal items
  "🍀": { name: "Trèfle", buyPrice: 2, sellPrice: 1, description: "Soigne 1 PV - 20% crit" },
  "🩹": { name: "Bandage", buyPrice: 10, sellPrice: 6, description: "Soigne 5 PV - 15% crit" },
  "🩸": { name: "Sang", buyPrice: 20, sellPrice: 12, description: "Soigne 10 PV - 10% crit" },
  "💊": { name: "Pilule", buyPrice: 30, sellPrice: 18, description: "Soigne 15 PV - 5% crit" },
  "💕": { name: "Régénération", buyPrice: 40, sellPrice: 24, description: "Régén +2 PV/30min 5h - 2% crit" },

  // Use items
  "🎁": { name: "Cadeau", buyPrice: 50, sellPrice: 30, description: "Boîte surprise avec objets/GC" },
  "🔍": { name: "Loupe", buyPrice: 35, sellPrice: 21, description: "Vole un objet aléatoire" },
  "💉": { name: "Seringue", buyPrice: 25, sellPrice: 15, description: "Soigne virus/poison/infection" },
  "🛡️": { name: "Bouclier", buyPrice: 30, sellPrice: 18, description: "+20 points de bouclier" },
  "👟": { name: "Chaussures", buyPrice: 45, sellPrice: 27, description: "Double esquive 6h" },
  "🪖": { name: "Casque", buyPrice: 50, sellPrice: 30, description: "Réduction -50% dégâts 8h" },
  "⭐": { name: "Étoile", buyPrice: 100, sellPrice: 60, description: "Immunité totale 5h" },

  // Special
  "🎫": { name: "Ticket", buyPrice: 200, sellPrice: 0, description: "Ticket d'invocation gacha" },
};

// Character sell values by rarity
export const RARITY_SELL_VALUES = {
  "Commun": 50,
  "Peu commun": 100, // Uncommon
  "Rare": 100,
  "Épique": 200,
  "Légendaire": 400,
};

// Get item by emoji
export function getShopItem(emoji) {
  return SHOP_ITEMS[emoji];
}

// Get all shop items as array
export function getAllShopItems() {
  return Object.entries(SHOP_ITEMS).map(([emoji, data]) => ({
    emoji,
    ...data,
  }));
}

// Check if item exists in shop
export function isShopItem(emoji) {
  return emoji in SHOP_ITEMS;
}
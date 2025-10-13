// Color constants for Discord embeds
// Using hex color codes

export const COLORS = {
  // Command colors
  INVENTORY: '#2ECC71',      // Green
  INFO: '#9B59B6',           // Purple
  PROFILE: '#5865F2',        // Blue (existing)
  SHOP: '#5865F2',           // Blue (existing)
  SUCCESS: '#2ECC71',        // Green
  ERROR: '#E74C3C',          // Red
  WARNING: '#F39C12',        // Orange

  // Combat action colors
  COMBAT_DAMAGE: '#E74C3C',  // Red
  COMBAT_HEAL: '#90EE90',    // Light green
  COMBAT_UTILITY: '#5F9EA0', // Gray-blue (cadet blue)

  // Status effect colors
  STATUS_POISON: '#90EE90',  // Light green
  STATUS_VIRUS: '#228B22',   // Dark green (forest green)
  STATUS_INFECTION: '#800020', // Burgundy
  STATUS_BURN: '#FF8C00',    // Orange (dark orange)
  STATUS_REGENERATION: '#FFB6C1', // Pink (light pink)

  // Rarity colors
  RARITY_BASIC: '#808080',   // Gray
  RARITY_COMMON: '#3498DB',  // Blue
  RARITY_UNCOMMON: '#3498DB', // Blue (Peu commun)
  RARITY_RARE: '#2ECC71',    // Green
  RARITY_EPIC: '#9B59B6',    // Purple
  RARITY_LEGENDARY: '#F1C40F' // Yellow
};

// Get color by rarity name
export function getRarityColor(rarity) {
  const rarityMap = {
    'Basique': COLORS.RARITY_BASIC,
    'Basic': COLORS.RARITY_BASIC,
    'Commun': COLORS.RARITY_COMMON,
    'Common': COLORS.RARITY_COMMON,
    'Peu commun': COLORS.RARITY_UNCOMMON,
    'Uncommon': COLORS.RARITY_UNCOMMON,
    'Rare': COLORS.RARITY_RARE,
    'Épique': COLORS.RARITY_EPIC,
    'Epic': COLORS.RARITY_EPIC,
    'Légendaire': COLORS.RARITY_LEGENDARY,
    'Legendary': COLORS.RARITY_LEGENDARY
  };

  return rarityMap[rarity] || COLORS.RARITY_COMMON;
}

// Get color by status effect
export function getStatusColor(status) {
  const statusMap = {
    'POISON': COLORS.STATUS_POISON,
    'VIRUS': COLORS.STATUS_VIRUS,
    'INFECTION': COLORS.STATUS_INFECTION,
    'BURN': COLORS.STATUS_BURN,
    'REGENERATION': COLORS.STATUS_REGENERATION
  };

  return statusMap[status] || COLORS.INFO;
}

// Combat utility functions for player management
import { Player } from '../database/models/Player.js';
import { getCharacterById } from '../data/characters.js';

// Apply damage to a player
export async function applyDamage(userId, damageAmount, attackerId = null) {
  const player = await Player.findOne({ userId });

  if (!player) {
    throw new Error('Player not found');
  }

  // Check if player is already KO
  if (player.combat.isKO) {
    return {
      success: false,
      message: 'Player is already KO',
      isKO: true
    };
  }

  let actualDamage = damageAmount;
  let shieldDamage = 0;
  let hpDamage = 0;

  // Apply damage to shield first
  if (player.combat.shield > 0) {
    if (damageAmount <= player.combat.shield) {
      player.combat.shield -= damageAmount;
      shieldDamage = damageAmount;
      actualDamage = 0;
    } else {
      shieldDamage = player.combat.shield;
      actualDamage -= player.combat.shield;
      player.combat.shield = 0;
    }
  }

  // Apply remaining damage to HP
  if (actualDamage > 0) {
    player.combat.hp -= actualDamage;
    hpDamage = actualDamage;

    if (player.combat.hp <= 0) {
      player.combat.hp = 0;
      player.combat.isKO = true;
      player.combat.lastKOAt = new Date();
      player.stats.deaths += 1;

      // Award kill to attacker if provided (+50 GC bonus)
      if (attackerId && attackerId !== userId) {
        await Player.findOneAndUpdate(
          { userId: attackerId },
          {
            $inc: {
              'stats.kills': 1,
              'economy.coins': 50,  // +50 GC per kill
              'economy.totalEarned': 50
            }
          }
        );
      }
    }
  }

  // Update cumulative damage taken
  player.stats.damageTaken += damageAmount;
  player.lastUpdated = new Date();
  await player.save();

  // Update attacker's damage dealt if provided
  if (attackerId && attackerId !== userId) {
    await Player.findOneAndUpdate(
      { userId: attackerId },
      {
        $inc: {
          'stats.damageDealt': damageAmount,
          'stats.damages': damageAmount,  // Legacy field
          'economy.coins': damageAmount,  // +1 GC per HP damage dealt
          'economy.totalEarned': damageAmount
        }
      }
    );
  }

  // Apply death penalty (-25 GC)
  if (player.combat.isKO) {
    player.economy.coins = Math.max(0, player.economy.coins - 25);
    await player.save();
  }

  return {
    success: true,
    shieldDamage,
    hpDamage,
    totalDamage: damageAmount,
    currentHP: player.combat.hp,
    currentShield: player.combat.shield,
    isKO: player.combat.isKO,
  };
}

// Apply healing to a player
export async function applyHealing(userId, healAmount, healerId = null) {
  const player = await Player.findOne({ userId });

  if (!player) {
    throw new Error('Player not found');
  }

  // Can't heal if KO
  if (player.combat.isKO) {
    return {
      success: false,
      message: 'Cannot heal a KO player',
      isKO: true
    };
  }

  const previousHP = player.combat.hp;
  player.combat.hp = Math.min(player.combat.hp + healAmount, player.combat.maxHp);
  const actualHealing = player.combat.hp - previousHP;

  // Update cumulative healing
  player.stats.healingDone += actualHealing;
  player.stats.heals += actualHealing; // Legacy field
  player.lastUpdated = new Date();
  await player.save();

  // Update healer's stats if provided (+1 GC per HP healed)
  if (healerId && healerId !== userId) {
    await Player.findOneAndUpdate(
      { userId: healerId },
      {
        $inc: {
          'stats.healingDone': actualHealing,
          'stats.heals': actualHealing,  // Legacy field
          'economy.coins': actualHealing,  // +1 GC per HP healed
          'economy.totalEarned': actualHealing
        }
      }
    );
  }

  return {
    success: true,
    healAmount: actualHealing,
    currentHP: player.combat.hp,
    maxHP: player.combat.maxHp,
  };
}

// Revive a KO player
export async function revivePlayer(userId) {
  const player = await Player.findOne({ userId });

  if (!player) {
    throw new Error('Player not found');
  }

  if (!player.combat.isKO) {
    return {
      success: false,
      message: 'Player is not KO',
    };
  }

  player.combat.isKO = false;
  player.combat.hp = Math.floor(player.combat.maxHp * 0.3); // Revive with 30% HP
  player.lastUpdated = new Date();
  await player.save();

  return {
    success: true,
    currentHP: player.combat.hp,
    maxHP: player.combat.maxHp,
  };
}

// Add shield to player
export async function addShield(userId, shieldAmount) {
  const player = await Player.findOne({ userId });

  if (!player) {
    throw new Error('Player not found');
  }

  const previousShield = player.combat.shield;
  player.combat.shield = Math.min(player.combat.shield + shieldAmount, player.combat.maxShield);
  const actualShield = player.combat.shield - previousShield;

  player.lastUpdated = new Date();
  await player.save();

  return {
    success: true,
    shieldAdded: actualShield,
    currentShield: player.combat.shield,
    maxShield: player.combat.maxShield,
  };
}

// Get player combat status
export async function getPlayerCombatStatus(userId) {
  const player = await Player.findOne({ userId });

  if (!player) {
    throw new Error('Player not found');
  }

  // Get equipped character passives
  let passives = [];
  if (player.equippedCharacter?.characterId) {
    const character = getCharacterById(player.equippedCharacter.characterId);
    if (character) {
      passives.push({
        name: character.passive,
        description: character.passiveDescription,
      });
    }
  }

  // Get active status effects
  const now = new Date();
  const activeEffects = player.activeEffects?.filter(effect => {
    const elapsedSeconds = (now - effect.appliedAt) / 1000;
    return elapsedSeconds < effect.duration;
  }) || [];

  return {
    hp: player.combat.hp,
    maxHp: player.combat.maxHp,
    shield: player.combat.shield,
    maxShield: player.combat.maxShield,
    isKO: player.combat.isKO,
    lastKOAt: player.combat.lastKOAt,
    passives,
    activeEffects,
    stats: {
      damageDealt: player.stats.damageDealt,
      damageTaken: player.stats.damageTaken,
      healingDone: player.stats.healingDone,
      kills: player.stats.kills,
      deaths: player.stats.deaths,
      assists: player.stats.assists,
    },
  };
}

// Calculate KDA ratio
export function calculateKDA(kills, deaths, assists) {
  if (deaths === 0) return (kills + assists).toFixed(2);
  return ((kills + assists) / deaths).toFixed(2);
}

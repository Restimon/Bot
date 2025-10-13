# Player Management System (2.0)

## ✅ Complete Player Statistics Tracking

All player statistics are stored in MongoDB and persist across restarts.

---

## 📊 Player Stats Structure

### Combat Stats (Real-time):
- **HP (Health Points)**: Current health
- **Max HP**: Maximum health capacity
- **Shield Points (SP)**: Current shield
- **Max Shield**: Maximum shield capacity
- **KO Status**: Alive or dead (boolean)
- **Last KO Timestamp**: When player was last knocked out

### Cumulative Stats (Lifetime):
- **Total Damage Dealt**: All damage dealt since account creation
- **Total Damage Taken**: All damage taken since account creation
- **Total Healing Done**: All healing performed since account creation
- **Kills**: Total enemy kills
- **Deaths**: Total times knocked out
- **Assists**: Combat assists

### Equipped Passives:
- **Character Passive**: Ability from equipped character
- **Status Effects**: Active buffs/debuffs (poison, burn, regen, etc.)

---

## 🛠️ Combat Utility Functions

All functions available in `/utils/combat.js`:

### 1. Apply Damage
```javascript
applyDamage(userId, damageAmount, attackerId = null)
```
- Damages shield first, then HP
- Automatically handles KO when HP reaches 0
- Updates both victim's damage taken and attacker's damage dealt
- Awards kill to attacker
- Returns: damage breakdown, current stats, KO status

### 2. Apply Healing
```javascript
applyHealing(userId, healAmount, healerId = null)
```
- Heals up to max HP
- Cannot heal KO players
- Updates healer's healing stats
- Returns: actual healing amount, current HP

### 3. Revive Player
```javascript
revivePlayer(userId)
```
- Revives KO player with 30% HP
- Removes KO status
- Returns: new HP status

### 4. Add Shield
```javascript
addShield(userId, shieldAmount)
```
- Adds shield up to max shield
- Returns: shield added, current shield

### 5. Get Combat Status
```javascript
getPlayerCombatStatus(userId)
```
- Returns complete combat status
- Includes: HP, shield, KO status, passives, active effects, all stats

### 6. Calculate KDA
```javascript
calculateKDA(kills, deaths, assists)
```
- Returns KDA ratio as formatted string

---

## 💾 Database Schema

### Player Model Fields:

```javascript
{
  // Combat - Real-time
  combat: {
    hp: Number (default: 100),
    maxHp: Number (default: 100),
    shield: Number (default: 0),
    maxShield: Number (default: 50),
    isKO: Boolean (default: false),
    lastKOAt: Date
  },

  // Stats - Cumulative
  stats: {
    damageDealt: Number (default: 0),
    damageTaken: Number (default: 0),
    healingDone: Number (default: 0),
    kills: Number (default: 0),
    deaths: Number (default: 0),
    assists: Number (default: 0),
    // Legacy fields for backward compatibility
    damages: Number,
    heals: Number
  },

  // Equipped Character
  equippedCharacter: {
    characterId: String,
    equippedAt: Date
  },

  // Active Effects
  activeEffects: [{
    effect: String, // POISON, BURN, REGENERATION, etc.
    appliedAt: Date,
    duration: Number // in seconds
  }]
}
```

---

## 🎮 Usage Examples

### Example 1: Player takes damage
```javascript
import { applyDamage } from './utils/combat.js';

// Player takes 50 damage from attacker
const result = await applyDamage('victim_user_id', 50, 'attacker_user_id');

console.log(result);
// {
//   success: true,
//   shieldDamage: 0,
//   hpDamage: 50,
//   totalDamage: 50,
//   currentHP: 50,
//   currentShield: 0,
//   isKO: false
// }
```

### Example 2: Player gets healed
```javascript
import { applyHealing } from './utils/combat.js';

const result = await applyHealing('player_user_id', 30, 'healer_user_id');

console.log(result);
// {
//   success: true,
//   healAmount: 30,
//   currentHP: 80,
//   maxHP: 100
// }
```

### Example 3: Check player status
```javascript
import { getPlayerCombatStatus } from './utils/combat.js';

const status = await getPlayerCombatStatus('player_user_id');

console.log(status);
// {
//   hp: 80,
//   maxHp: 100,
//   shield: 0,
//   maxShield: 50,
//   isKO: false,
//   passives: [{ name: 'Marque de l\'Hôte', description: '...' }],
//   activeEffects: [{ effect: 'POISON', appliedAt: Date, duration: 60 }],
//   stats: {
//     damageDealt: 150,
//     damageTaken: 50,
//     healingDone: 30,
//     kills: 2,
//     deaths: 1,
//     assists: 3
//   }
// }
```

---

## 🔄 Automatic Updates

The system automatically:
- ✅ Updates damage dealt when attacking
- ✅ Updates damage taken when hit
- ✅ Updates healing done when healing
- ✅ Awards kills on KO
- ✅ Increments deaths on KO
- ✅ Tracks shield damage separately from HP damage
- ✅ Prevents healing/damage on KO players
- ✅ Stores KO timestamp
- ✅ Syncs legacy fields for backward compatibility

---

## 🎯 Integration Points

This system can be integrated with:

1. **Combat Commands** (`/attack`, `/heal`, `/fight`)
2. **Special Supply** (damage/healing rewards)
3. **Status Effects** (poison damage over time)
4. **Character Passives** (automatic healing, damage boosts)
5. **Leaderboards** (damage dealt, kills, etc.)
6. **Profile Display** (shows all stats in `/profile`)

---

## 📈 Viewing Stats

Players can view their stats using:
- `/profile` - Complete profile with HP, shield, stats
- `/info` - Quick stats view
- Future: `/stats` - Detailed combat statistics

All stats are permanently stored and accessible!

---

## ✨ Features

- ✅ Real-time HP and shield tracking
- ✅ Cumulative damage/healing statistics
- ✅ KO system with timestamps
- ✅ Kill/death tracking
- ✅ Shield priority damage system
- ✅ Heal prevention on KO players
- ✅ Automatic stat updates
- ✅ Character passive integration
- ✅ Status effect tracking
- ✅ MongoDB persistence

**All player management features are complete and ready to use!** 🎮

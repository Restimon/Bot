# Slash Commands

## Available Commands

### 1. `/info [joueur]`
Display detailed player statistics including:
- Combat stats (damage, heals, K/D/A)
- Discord activity (messages, voice time)
- Economy (coins, casino balance)
- Inventory preview
- Level, XP, and leaderboard rank
- AI-generated description (French)

### 2. `/inventaire [joueur]`
Display a player's complete inventory with:
- All items grouped by type
- Item quantities
- Total item count
- Coin balance

### 3. `/ouvrir`
Open your last received loot box to reveal the item inside.

### 4. `/welcome` (Admin only)
Configure the server welcome system:
- `/welcome activer #channel` - Enable welcome messages in a specific channel
- `/welcome desactiver` - Disable welcome system
- `/welcome message <text>` - Set custom welcome message (use `{user}`, `{server}`, `{username}`)
- `/welcome info` - Show current configuration

## Automatic Features

### Regular Loot Boxes
- Trigger: Every 5-15 messages (random)
- Duration: 30 seconds
- Max participants: 5 players
- Rewards: Random items with different rarities
- Bot ignores messages from other bots

### Special Supply Drops
- Frequency: Up to 3 times per day
- Restrictions: Never between 00:00 and 06:30
- Cooldown: 3 hours + 30 messages between spawns
- Duration: 5 minutes
- Max participants: 5 players
- Rewards:
  - Items (1-2 of same type)
  - Tickets
  - GotCoins (20-70)
  - Damage (1-10)
  - Heal (1-10)
  - Status effects (poison, burn, regeneration, virus, infection)

### Welcome System
- Automatic welcome messages for new members
- Customizable per server
- AI-enhanced messages (French)
- Elegant embeds with member info

## All Responses in French
All bot responses, embeds, and AI-generated content are in French.

import { SlashCommandBuilder, EmbedBuilder } from 'discord.js';
import { Player } from '../database/models/Player.js';
import { SHOP_ITEMS } from '../data/shop.js';
import { getItemCategory } from '../data/itemCategories.js';

export const data = new SlashCommandBuilder()
  .setName('daily')
  .setDescription('Réclamez votre récompense quotidienne');

const DAILY_COOLDOWN = 24 * 60 * 60 * 1000; // 24 hours in milliseconds
const MAX_STREAK = 20;
const BASE_COINS_MIN = 10;
const BASE_COINS_MAX = 20;
const DAILY_TICKETS = 1;
const DAILY_ITEMS = 2;

// Possible items for daily rewards (low tier items)
const DAILY_ITEM_POOL = ['🍀', '🩹']; // Trèfle (heal 1) and Bandage (heal 5)

export async function execute(interaction) {
  await interaction.deferReply();

  try {
    // Get or create player
    let player = await Player.findOne({ userId: interaction.user.id });

    if (!player) {
      player = await Player.create({
        userId: interaction.user.id,
        username: interaction.user.username,
        daily: {
          lastClaimed: null,
          currentStreak: 0,
          maxStreak: 0,
        }
      });
    }

    const now = new Date();
    const lastClaimed = player.daily?.lastClaimed;

    // Check if 24 hours have passed
    if (lastClaimed) {
      const timeSinceLastClaim = now - lastClaimed;
      const timeRemaining = DAILY_COOLDOWN - timeSinceLastClaim;

      if (timeRemaining > 0) {
        // Still on cooldown
        const hoursRemaining = Math.floor(timeRemaining / (1000 * 60 * 60));
        const minutesRemaining = Math.floor((timeRemaining % (1000 * 60 * 60)) / (1000 * 60));

        const embed = new EmbedBuilder()
          .setColor('#E74C3C')
          .setTitle('⏰ Récompense quotidienne déjà réclamée')
          .setDescription(
            `Vous avez déjà réclamé votre récompense quotidienne aujourd'hui.\n\n` +
            `⏱️ Prochain daily dans : **${hoursRemaining}h ${minutesRemaining}m**`
          )
          .setFooter({ text: `Streak actuel : ${player.daily.currentStreak} jour${player.daily.currentStreak > 1 ? 's' : ''}` })
          .setTimestamp();

        return await interaction.editReply({ embeds: [embed] });
      }
    }

    // Calculate streak
    let newStreak = 1;

    if (lastClaimed) {
      const hoursSinceLastClaim = (now - lastClaimed) / (1000 * 60 * 60);

      // If claimed within 48 hours, continue streak
      if (hoursSinceLastClaim <= 48) {
        newStreak = Math.min((player.daily.currentStreak || 0) + 1, MAX_STREAK);
      } else {
        // Streak broken, reset to 1
        newStreak = 1;
      }
    }

    // Calculate rewards
    const baseCoins = Math.floor(Math.random() * (BASE_COINS_MAX - BASE_COINS_MIN + 1)) + BASE_COINS_MIN;
    const streakBonus = Math.min(newStreak, MAX_STREAK); // +1 coin per streak day (max 20)
    const totalCoins = baseCoins + streakBonus;

    // Generate 2 random items from pool
    const items = [];
    for (let i = 0; i < DAILY_ITEMS; i++) {
      const randomEmoji = DAILY_ITEM_POOL[Math.floor(Math.random() * DAILY_ITEM_POOL.length)];
      items.push(randomEmoji);
    }

    // Apply rewards
    player.economy.coins += totalCoins;
    player.economy.totalEarned = (player.economy.totalEarned || 0) + totalCoins;
    player.economy.tickets = (player.economy.tickets || 0) + DAILY_TICKETS;

    // Add items to inventory
    for (const itemEmoji of items) {
      const existingItem = player.inventory.find(item => item.itemName === itemEmoji);
      if (existingItem) {
        existingItem.quantity += 1;
      } else {
        player.inventory.push({
          itemName: itemEmoji,
          quantity: 1
        });
      }
    }

    // Update daily data
    if (!player.daily) {
      player.daily = {};
    }
    player.daily.lastClaimed = now;
    player.daily.currentStreak = newStreak;
    player.daily.maxStreak = Math.max(player.daily.maxStreak || 0, newStreak);
    player.lastUpdated = now;

    await player.save();

    // Create items display
    const itemsList = items.map(emoji => {
      const itemData = getItemCategory(emoji);
      return `1x ${emoji} [${itemData.description}]`;
    });

    // Count total tickets
    const totalTickets = player.economy.tickets;

    // Format tickets and items in columns
    let rewardsText = `🎟️ **Tickets**${' '.repeat(15)}**Objets**\n`;
    rewardsText += `+${DAILY_TICKETS} (total: ${totalTickets})${' '.repeat(10)}${itemsList[0] || ''}\n`;
    for (let i = 1; i < itemsList.length; i++) {
      rewardsText += `${' '.repeat(25)}${itemsList[i]}\n`;
    }

    // Create embed
    const embed = new EmbedBuilder()
      .setColor('#F39C12')
      .setTitle('🎁 Récompense quotidienne')
      .setDescription(
        `**Streak : ${newStreak}** (bonus +${streakBonus})\n\n` +
        `**GotCoins gagnés**\n+${totalCoins}\n\n` +
        rewardsText + '\n' +
        `**Solde actuel**\n${player.economy.coins.toLocaleString()}`
      )
      .setFooter({
        text: `Prochaine récompense dans 24h • Streak max: ${player.daily.maxStreak}`
      })
      .setTimestamp();

    await interaction.editReply({ embeds: [embed] });

  } catch (error) {
    console.error('Error in /daily command:', error);
    await interaction.editReply({
      content: '❌ Une erreur est survenue lors de la réclamation de votre récompense quotidienne.',
      ephemeral: true,
    });
  }
}

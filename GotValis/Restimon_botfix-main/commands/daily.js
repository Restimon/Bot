import { SlashCommandBuilder, EmbedBuilder } from 'discord.js';
import { Player } from '../database/models/Player.js';
import { SHOP_ITEMS } from '../data/shop.js';
import { getItemCategory } from '../data/itemCategories.js';

export const data = new SlashCommandBuilder()
  .setName('daily')
  .setDescription('Réclamez votre récompense quotidienne');

const DAILY_COOLDOWN = 24 * 60 * 60 * 1000; // 24h
const MAX_STREAK = 20;
const BASE_COINS_MIN = 10;
const BASE_COINS_MAX = 20;
const DAILY_TICKETS = 1;
const DAILY_ITEMS = 2;
const DAILY_ITEM_POOL = ['🍀', '🩹']; // Trèfle (Soin 1), Bandage (Soin 5)

function formatItem(emoji) {
  if (emoji === '🍀') return '1x 🍀 [Soin 1]';
  if (emoji === '🩹') return '1x 🩹 [Soin 5]';
  return `1x ${emoji}`;
}

export async function execute(interaction) {
  await interaction.deferReply();

  try {
    // Récupère ou crée le joueur
    let player = await Player.findOne({ userId: interaction.user.id });

    if (!player) {
      player = await Player.create({
        userId: interaction.user.id,
        username: interaction.user.username,
        economy: { coins: 0, totalEarned: 0, tickets: 0 },
        inventory: [],
        daily: { lastClaimed: null, currentStreak: 0, maxStreak: 0 },
      });
    }

    const now = new Date();
    const lastClaimed = player.daily?.lastClaimed;

    // Vérifie le cooldown 24h
    if (lastClaimed) {
      const timeSinceLastClaim = now - lastClaimed;
      const timeRemaining = DAILY_COOLDOWN - timeSinceLastClaim;

      if (timeRemaining > 0) {
        const hoursRemaining = Math.floor(timeRemaining / (1000 * 60 * 60));
        const minutesRemaining = Math.floor((timeRemaining % (1000 * 60 * 60)) / (1000 * 60));

        const embed = new EmbedBuilder()
          .setColor('#E74C3C')
          .setTitle('⏰ Récompense quotidienne déjà réclamée')
          .setDescription(
            `Vous avez déjà réclamé votre récompense quotidienne aujourd'hui.\n\n` +
            `⏱️ Prochain daily dans : **${hoursRemaining}h ${minutesRemaining}m**`
          )
          .setFooter({ text: `Streak actuel : ${player.daily.currentStreak}` })
          .setTimestamp();

        return await interaction.editReply({ embeds: [embed] });
      }
    }

    // Calcule le streak
    let newStreak = 1;
    if (lastClaimed) {
      const hoursSinceLastClaim = (now - lastClaimed) / (1000 * 60 * 60);
      if (hoursSinceLastClaim <= 48) {
        newStreak = Math.min((player.daily.currentStreak || 0) + 1, MAX_STREAK);
      }
    }

    // Calcule les récompenses
    const baseCoins = Math.floor(Math.random() * (BASE_COINS_MAX - BASE_COINS_MIN + 1)) + BASE_COINS_MIN;
    const streakBonus = Math.min(newStreak, MAX_STREAK);
    const totalCoins = baseCoins + streakBonus;

    // Tire les objets
    const items = [];
    for (let i = 0; i < DAILY_ITEMS; i++) {
      const randomEmoji = DAILY_ITEM_POOL[Math.floor(Math.random() * DAILY_ITEM_POOL.length)];
      items.push(randomEmoji);
    }

    // Ajoute les récompenses
    player.economy.coins += totalCoins;
    player.economy.totalEarned = (player.economy.totalEarned || 0) + totalCoins;
    player.economy.tickets = (player.economy.tickets || 0) + DAILY_TICKETS;

    // Ajoute les objets
    for (const itemEmoji of items) {
      const existing = player.inventory.find(i => i.itemName === itemEmoji);
      if (existing) existing.quantity += 1;
      else player.inventory.push({ itemName: itemEmoji, quantity: 1 });
    }

    // Met à jour le streak
    player.daily.lastClaimed = now;
    player.daily.currentStreak = newStreak;
    player.daily.maxStreak = Math.max(player.daily.maxStreak || 0, newStreak);
    player.lastUpdated = now;
    await player.save();

    // Format affichage objets
    const itemLines = items.map(formatItem).join('\n') || '—';
    const totalTickets = player.economy.tickets;
    const nextReward = new Date(now.getTime() + DAILY_COOLDOWN);
    const nextTime = `${nextReward.toLocaleDateString('fr-FR')} à ${nextReward.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })}`;

    // Création embed final
    const embed = new EmbedBuilder()
      .setColor('#F39C12')
      .setTitle('🎁 Récompense quotidienne')
      .addFields(
        { name: '🔥 Streak', value: `${newStreak} (bonus +${streakBonus})`, inline: true },
        { name: '💰 GotCoins gagnés', value: `+${totalCoins} *(= ${baseCoins} base + ${streakBonus} bonus)*`, inline: true },
        { name: '🎟️ Tickets', value: `+${DAILY_TICKETS} (total: ${totalTickets})`, inline: false },
        { name: '🎒 Objets obtenus', value: itemLines, inline: false },
        { name: '💳 Solde actuel', value: `${player.economy.coins.toLocaleString()} GC`, inline: false },
      )
      .setFooter({ text: `Prochaine récompense : ${nextTime} • Streak max : ${player.daily.maxStreak}` })
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

import { SlashCommandBuilder, EmbedBuilder } from 'discord.js';
import { Player } from '../database/models/Player.js';
import { SHOP_ITEMS } from '../data/shop.js';
import { getItemCategory } from '../data/itemCategories.js';

export const data = new SlashCommandBuilder()
  .setName('daily')
  .setDescription('Réclamez votre récompense quotidienne');

const DAILY_COOLDOWN = 24 * 60 * 60 * 1000;
const MAX_STREAK = 20;
const BASE_COINS_MIN = 10;
const BASE_COINS_MAX = 20;
const DAILY_TICKETS = 1;
const DAILY_ITEMS = 2;
const DAILY_ITEM_POOL = ['🍀', '🩹'];

function cleanItemLabel(raw) {
  const t = String(raw ?? '').trim().replace(/^\[+|\]+$/g, '');
  const m = /Soigne\s+(\d+)\s*PV?/i.exec(t);
  return m ? `Soin ${m[1]}` : t;
}

export async function execute(interaction) {
  await interaction.deferReply();

  try {
    let player = await Player.findOne({ userId: interaction.user.id });

    if (!player) {
      player = await Player.create({
        userId: interaction.user.id,
        username: interaction.user.username,
        daily: {
          lastClaimed: null,
          currentStreak: 0,
          maxStreak: 0,
        },
      });
    }

    const now = new Date();
    const lastClaimed = player.daily?.lastClaimed;

    if (lastClaimed) {
      const timeSinceLastClaim = now - lastClaimed;
      const timeRemaining = DAILY_COOLDOWN - timeSinceLastClaim;

      if (timeRemaining > 0) {
        const hoursRemaining = Math.floor(timeRemaining / (1000 * 60 * 60));
        const minutesRemaining = Math.floor(
          (timeRemaining % (1000 * 60 * 60)) / (1000 * 60)
        );

        const embed = new EmbedBuilder()
          .setColor('#E74C3C')
          .setTitle('⏰ Récompense quotidienne déjà réclamée')
          .setDescription(
            `Vous avez déjà réclamé votre récompense quotidienne aujourd'hui.\n\n` +
              `⏱️ Prochain daily dans : **${hoursRemaining}h ${minutesRemaining}m**`
          )
          .setFooter({
            text: `Streak actuel : ${player.daily.currentStreak} jour${
              player.daily.currentStreak > 1 ? 's' : ''
            }`,
          })
          .setTimestamp();

        return await interaction.editReply({ embeds: [embed] });
      }
    }

    let newStreak = 1;
    if (lastClaimed) {
      const hoursSinceLastClaim = (now - lastClaimed) / (1000 * 60 * 60);
      if (hoursSinceLastClaim <= 48) {
        newStreak = Math.min((player.daily.currentStreak || 0) + 1, MAX_STREAK);
      } else {
        newStreak = 1;
      }
    }

    const baseCoins =
      Math.floor(Math.random() * (BASE_COINS_MAX - BASE_COINS_MIN + 1)) +
      BASE_COINS_MIN;
    const streakBonus = Math.min(newStreak, MAX_STREAK);
    const totalCoins = baseCoins + streakBonus;

    const items = [];
    for (let i = 0; i < DAILY_ITEMS; i++) {
      const randomEmoji =
        DAILY_ITEM_POOL[Math.floor(Math.random() * DAILY_ITEM_POOL.length)];
      items.push(randomEmoji);
    }

    player.economy.coins += totalCoins;
    player.economy.totalEarned = (player.economy.totalEarned || 0) + totalCoins;
    player.economy.tickets = (player.economy.tickets || 0) + DAILY_TICKETS;

    for (const itemEmoji of items) {
      const existingItem = player.inventory.find(
        (item) => item.itemName === itemEmoji
      );
      if (existingItem) {
        existingItem.quantity += 1;
      } else {
        player.inventory.push({
          itemName: itemEmoji,
          quantity: 1,
        });
      }
    }

    if (!player.daily) player.daily = {};
    player.daily.lastClaimed = now;
    player.daily.currentStreak = newStreak;
    player.daily.maxStreak = Math.max(
      player.daily.maxStreak || 0,
      newStreak
    );
    player.lastUpdated = now;
    await player.save();

    const grouped = new Map();
    for (const emoji of items) {
      const itemData = getItemCategory(emoji);
      const label = cleanItemLabel(itemData?.description || '');
      if (!grouped.has(emoji)) grouped.set(emoji, { emoji, qty: 0, label });
      grouped.get(emoji).qty += 1;
    }

    const objetsLines = [...grouped.values()].map(
      ({ emoji, qty, label }) => `${qty}x ${emoji} [${label}]`
    );
    const objetsValue = objetsLines.length ? objetsLines.join('\n') : '—';

    const totalTickets = player.economy.tickets;

    const embed = new EmbedBuilder()
      .setColor('#F39C12')
      .setTitle('🎁 Récompense quotidienne')
      .addFields(
        { name: 'Streak :', value: `${newStreak} (bonus +${streakBonus})`, inline: false },
        { name: 'GotCoins gagnés', value: `+${totalCoins} (base ${baseCoins} + bonus +${streakBonus})`, inline: false },
        { name: '🎟️ Tickets', value: `+${DAILY_TICKETS} (total: ${totalTickets})`, inline: true },
        { name: 'Objets', value: objetsValue, inline: true },
        { name: 'Solde actuel', value: `${player.economy.coins.toLocaleString()}`, inline: false }
      )
      .setFooter({
        text: `Prochaine récompense dans 24h • Streak max: ${player.daily.maxStreak}`,
      })
      .setTimestamp();

    await interaction.editReply({ embeds: [embed] });
  } catch (error) {
    console.error('Error in /daily command:', error);
    await interaction.editReply({
      content:
        '❌ Une erreur est survenue lors de la réclamation de votre récompense quotidienne.',
      ephemeral: true,
    });
  }
}

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

const DAILY_GACHA_TICKETS = 1;   // on crédite gachaTickets
const DAILY_ITEMS_COUNT = 2;     // nombre d'objets donnés

// ——— pool limité aux catégories autorisées ———
const ALLOWED_CATEGORIES = new Set(['utility', 'utilitaire', 'heal', 'soins', 'fight', 'combat']);

function buildDailyPool() {
  // SHOP_ITEMS attendu au format [{ id, name, emoji?, rarity?, ... }]
  // getItemCategory(id) -> "heal"/"fight"/"utility"/...
  return SHOP_ITEMS.filter(it => {
    const cat = (getItemCategory?.(it.id) || '').toLowerCase();
    return ALLOWED_CATEGORIES.has(cat);
  });
}

function pickOne(arr) {
  return arr[Math.floor(Math.random() * arr.length)];
}

function formatWonItem(it) {
  const icon = it.emoji ? `${it.emoji} ` : '';
  return `1x ${icon}[${it.name}]`;
}

export async function execute(interaction) {
  await interaction.deferReply();

  try {
    let player = await Player.findOne({ userId: interaction.user.id });

    if (!player) {
      player = await Player.create({
        userId: interaction.user.id,
        username: interaction.user.username,
        economy: { coins: 0, totalEarned: 0 },
        gachaTickets: 0,
        inventory: [],
        daily: { lastClaimed: null, currentStreak: 0, maxStreak: 0 },
      });
    }

    const now = new Date();
    const lastClaimed = player.daily?.lastClaimed;

    // Cooldown 24h
    if (lastClaimed) {
      const timeSince = now - lastClaimed;
      const remaining = DAILY_COOLDOWN - timeSince;
      if (remaining > 0) {
        const h = Math.floor(remaining / (1000 * 60 * 60));
        const m = Math.floor((remaining % (1000 * 60 * 60)) / (1000 * 60));
        const embed = new EmbedBuilder()
          .setColor('#E74C3C')
          .setTitle('⏰ Récompense quotidienne déjà réclamée')
          .setDescription(`Prochain daily dans : **${h}h ${m}m**`)
          .setFooter({ text: `Streak actuel : ${player.daily.currentStreak || 0}` })
          .setTimestamp();
        return await interaction.editReply({ embeds: [embed] });
      }
    }

    // Streak
    let newStreak = 1;
    if (lastClaimed) {
      const hoursSince = (now - lastClaimed) / (1000 * 60 * 60);
      if (hoursSince <= 48) newStreak = Math.min((player.daily.currentStreak || 0) + 1, MAX_STREAK);
    }

    // GC
    const baseCoins = Math.floor(Math.random() * (BASE_COINS_MAX - BASE_COINS_MIN + 1)) + BASE_COINS_MIN;
    const streakBonus = Math.min(newStreak, MAX_STREAK);
    const totalCoins = baseCoins + streakBonus;

    // Tirage objets depuis le pool autorisé
    const pool = buildDailyPool();
    if (pool.length === 0) {
      console.error('Daily pool vide : vérifie SHOP_ITEMS / getItemCategory');
    }
    const wonItems = [];
    for (let i = 0; i < DAILY_ITEMS_COUNT; i++) {
      wonItems.push(pickOne(pool));
    }

    // Appliquer récompenses
    player.economy.coins = (player.economy.coins || 0) + totalCoins;
    player.economy.totalEarned = (player.economy.totalEarned || 0) + totalCoins;
    player.gachaTickets = (player.gachaTickets || 0) + DAILY_GACHA_TICKETS;

    // Ajout objets à l’inventaire (canon: itemId + itemName)
    for (const it of wonItems) {
      const idx = player.inventory.findIndex(x => x.itemId === it.id);
      if (idx >= 0) player.inventory[idx].quantity = (player.inventory[idx].quantity || 0) + 1;
      else player.inventory.push({ itemId: it.id, itemName: it.name, quantity: 1 });
    }

    // Streak + timestamps
    player.daily.lastClaimed = now;
    player.daily.currentStreak = newStreak;
    player.daily.maxStreak = Math.max(player.daily.maxStreak || 0, newStreak);
    player.lastUpdated = now;
    await player.save();

    // Affichage
    const itemLines = wonItems.map(formatWonItem).join('\n') || '—';
    const next = new Date(now.getTime() + DAILY_COOLDOWN);
    const nextStr = `${next.toLocaleDateString('fr-FR')} à ${next.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })}`;

    const embed = new EmbedBuilder()
      .setColor('#F39C12')
      .setTitle('🎁 Récompense quotidienne')
      .addFields(
        { name: '🔥 Streak', value: `${newStreak} (bonus +${streakBonus})`, inline: true },
        { name: '💰 GotCoins gagnés', value: `+${totalCoins} *(= ${baseCoins} base + ${streakBonus} bonus)*`, inline: true },
        { name: '🎟️ Tickets', value: `+${DAILY_GACHA_TICKETS} (total: ${player.gachaTickets})`, inline: false },
        { name: '🎒 Objets obtenus', value: itemLines, inline: false },
        { name: '💳 Solde actuel', value: `${(player.economy.coins || 0).toLocaleString()} GC`, inline: false },
      )
      .setFooter({ text: `Prochaine récompense : ${nextStr} • Streak max : ${player.daily.maxStreak || 0}` })
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

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
const DAILY_GACHA_TICKETS = 1;
const DAILY_ITEMS_COUNT = 2;

// Catégories autorisées pour le daily
const ALLOWED_CATEGORIES = new Set(['fight', 'soins', 'heal', 'utilitaire', 'utility']);

function buildDailyPool() {
  // SHOP_ITEMS est un objet -> on le transforme en tableau
  return Object.entries(SHOP_ITEMS)
    .filter(([emoji, data]) => {
      // getItemCategory peut renvoyer un objet { category, description }
      const meta =
        (typeof getItemCategory === 'function'
          ? (getItemCategory(emoji) || (data?.id ? getItemCategory(data.id) : null))
          : null);

      const rawCat =
        (meta && typeof meta === 'object' ? meta.category : undefined) ??
        (typeof data?.category === 'string' ? data.category : undefined) ??
        (typeof data?.type === 'string' ? data.type : undefined) ??
        '';

      const cat = String(rawCat).toLowerCase();
      return ALLOWED_CATEGORIES.has(cat);
    })
    .map(([emoji, data]) => ({
      emoji,                                      // ex: '🧪'
      id: data?.id,
      name: data?.name || data?.displayName || 'Objet',
      ...data,
    })); // => tableau d’items { emoji, id, name, ... }
}

function pickOne(arr) { return arr[Math.floor(Math.random() * arr.length)]; }
function formatWonItem(it) { return `1x ${it.emoji ?? ''} [${it.name}]`; }

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
    const last = player.daily?.lastClaimed;

    // Cooldown 24h
    if (last) {
      const remaining = DAILY_COOLDOWN - (now - last);
      if (remaining > 0) {
        const h = Math.floor(remaining / 3600000);
        const m = Math.floor((remaining % 3600000) / 60000);
        const embed = new EmbedBuilder()
          .setColor('#E74C3C')
          .setTitle('⏰ Récompense quotidienne déjà réclamée')
          .setDescription(`Prochain daily dans : **${h}h ${m}m**`)
          .setFooter({ text: `Streak actuel : ${player.daily.currentStreak || 0}` })
          .setTimestamp();
        await interaction.editReply({ embeds: [embed] });
        return;
      }
    }

    // Streak
    let newStreak = 1;
    if (last && (now - last) / 3600000 <= 48) {
      newStreak = Math.min((player.daily.currentStreak || 0) + 1, MAX_STREAK);
    }

    // Coins
    const baseCoins = Math.floor(Math.random() * (BASE_COINS_MAX - BASE_COINS_MIN + 1)) + BASE_COINS_MIN;
    const streakBonus = Math.min(newStreak, MAX_STREAK);
    const totalCoins = baseCoins + streakBonus;

    // Tirage objets (pool filtré)
    const pool = buildDailyPool();
    const won = [];
    for (let i = 0; i < DAILY_ITEMS_COUNT; i++) {
      won.push(pickOne(pool));
    }

    // Récompenses
    player.economy.coins = (player.economy.coins || 0) + totalCoins;
    player.economy.totalEarned = (player.economy.totalEarned || 0) + totalCoins;
    player.gachaTickets = (player.gachaTickets || 0) + DAILY_GACHA_TICKETS;

    // Ajout inventaire (structure canon)
    for (const it of won) {
      const idx = (player.inventory || []).findIndex(x => x.itemId === it.id || x.itemName === it.emoji);
      if (idx >= 0) {
        player.inventory[idx].quantity = (player.inventory[idx].quantity || 0) + 1;
      } else {
        player.inventory.push({ itemId: it.id ?? undefined, itemName: it.emoji, quantity: 1 });
      }
    }

    // MàJ streak
    player.daily.lastClaimed = now;
    player.daily.currentStreak = newStreak;
    player.daily.maxStreak = Math.max(player.daily.maxStreak || 0, newStreak);
    player.lastUpdated = now;
    await player.save();

    // Embed
    const itemLines = won.map(formatWonItem).join('\n') || '—';
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

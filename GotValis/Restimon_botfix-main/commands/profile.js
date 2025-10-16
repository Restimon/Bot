import { SlashCommandBuilder, EmbedBuilder } from 'discord.js';
import { Player } from '../database/models/Player.js';
import { SHOP_ITEMS } from '../data/shop.js';
import { getItemCategory } from '../data/itemCategories.js';
import { getCharacterById } from '../data/characters.js';
import { getAIDescription } from '../utils/openai.js';

export const data = new SlashCommandBuilder()
  .setName('profile')
  .setNameLocalizations({ fr: 'profil' })
  .setDescription("Affiche le profil complet d'un joueur")
  .addUserOption(option =>
    option
      .setName('joueur')
      .setDescription('Le joueur dont vous voulez voir le profil')
      .setRequired(false)
  );

export async function execute(interaction) {
  await interaction.deferReply();

  const targetUser = interaction.options.getUser('joueur') || interaction.user;

  try {
    // Get or create player
    let player = await Player.findOne({ userId: targetUser.id });
    if (!player) {
      player = await Player.create({
        userId: targetUser.id,
        username: targetUser.username,
      });
    }

    // Classement par coins
    const guild = interaction.guild;
    const allPlayers = await Player.find({ userId: { $exists: true } }).sort({ 'economy.coins': -1 });
    const rank = allPlayers.findIndex(p => p.userId === targetUser.id) + 1;
    const rankText = rank > 0 ? `#${rank}` : 'Non classé';

    // Date de join
    const member = await guild.members.fetch(targetUser.id);
    const joinDate = member.joinedAt
      ? member.joinedAt.toLocaleDateString('fr-FR', {
          day: '2-digit',
          month: 'long',
          year: 'numeric',
          hour: '2-digit',
          minute: '2-digit',
          timeZone: 'UTC',
        })
      : 'Inconnu';

    // (Conservé si tu veux l'utiliser ailleurs)
    await getAIDescription(player).catch(() => null);

    // Perso équipé & passif
    const equippedCharId = player.equippedCharacter?.characterId;
    const characterInfo = equippedCharId ? getCharacterById(equippedCharId) : null;
    const characterDisplay = characterInfo ? characterInfo.name : 'Aucun';
    const passiveDisplay   = characterInfo
      ? `**${characterInfo.passive}** — ${characterInfo.passiveDescription}`
      : 'Aucun';

    // Inventaire (regroupe, masque tickets) => emoji + [Nom] — description
    const inventoryMap = {};
    for (const item of (player.inventory || [])) {
      const key = item.itemName || item.itemId || '';
      if (!key || /ticket|🎟️/i.test(key)) continue; // pas d’affichage de tickets ici
      inventoryMap[key] = (inventoryMap[key] || 0) + (item.quantity || 1);
    }

    const toLine = (emojiKey, qty) => {
      const metaShop = SHOP_ITEMS[emojiKey] || {};
      const label    = metaShop.name || metaShop.displayName || 'Objet';
      const descMeta = getItemCategory?.(emojiKey)?.description || '';
      return `${qty}x ${emojiKey} [${label}]${descMeta ? ` — ${descMeta}` : ''}`;
    };

    const inventoryItems = Object.entries(inventoryMap)
      .map(([key, qty]) => toLine(key, qty))
      .slice(0, 12);

    const inventoryLeft  = inventoryItems.slice(0, 6).join('\n') || 'Vide';
    const inventoryRight = inventoryItems.slice(6, 12).join('\n') || '';

    // Effets actifs
    const now = new Date();
    const activeEffects =
      player.activeEffects?.filter(effect => {
        const elapsedSeconds = (now - effect.appliedAt) / 1000;
        return elapsedSeconds < effect.duration;
      }) || [];

    const effectsDisplay =
      activeEffects.length > 0
        ? activeEffects
            .map(e => `${e.effect} (${Math.floor(e.duration - (now - e.appliedAt) / 1000)}s restantes)`)
            .join('\n')
        : 'Aucun effet détecté.';

    const embed = new EmbedBuilder()
      .setColor('#5865F2')
      .setTitle(`📋 Profil GotValis de ${targetUser.username}`)
      .setDescription('_Analyse médicale et opérationnelle en cours..._') // ✅ description fixe
      .setThumbnail(targetUser.displayAvatarURL({ dynamic: true }))
      .addFields(
        { name: '❤️ Points de vie', value: `${player.combat?.hp || 100} / ${player.combat?.maxHp || 100}`, inline: true },
        { name: '🛡️ Bouclier', value: `${player.combat?.shield || 0} / ${player.combat?.maxShield || 50}`, inline: true },
        { name: '\u200b', value: '\u200b', inline: true },

        { name: '🏆 GotCoins totaux (carrière)', value: `${player.economy?.totalEarned || player.economy?.coins || 0}`, inline: true },
        { name: '💰 Solde actuel (dépensable)', value: `${player.economy?.coins || 0}`, inline: true },
        { name: '🎟️ Tickets', value: `${player.economy?.tickets || 0}`, inline: true }, // ✅ lit economy.tickets (daily)

        { name: '🗓️ Membre du serveur depuis', value: joinDate, inline: false },

        // ✅ Passif une ligne sous “Personnage équipé”
        { name: '🎭 Personnage équipé', value: characterDisplay, inline: true },
        { name: '⚡ Passif', value: passiveDisplay, inline: true },
        { name: '\u200b', value: '\u200b', inline: true },

        // ✅ Classement avec emoji, sans “serveur”
        { name: '🏅 Classement', value: rankText, inline: false },

        // ✅ Inventaire avec descriptions
        { name: '🎒 Inventaire', value: inventoryLeft, inline: true }
      );

    if (inventoryRight) {
      embed.addFields({ name: '\u200b', value: inventoryRight, inline: true });
    }

    embed.addFields({ name: '🧬 État', value: effectsDisplay, inline: false });
    embed.setFooter({ text: `Niveau ${player.level} • ${player.xp} XP` });
    embed.setTimestamp();

    await interaction.editReply({ embeds: [embed] });
  } catch (error) {
    console.error('Error in /profile command:', error);
    await interaction.editReply({
      content: '❌ Une erreur est survenue lors de la récupération du profil.',
      ephemeral: true,
    });
  }
}

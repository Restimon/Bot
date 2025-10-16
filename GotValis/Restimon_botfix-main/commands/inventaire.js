import { SlashCommandBuilder, EmbedBuilder } from 'discord.js';
import { Player } from '../database/models/Player.js';
import { getItemCategory } from '../data/itemCategories.js';
import { COLORS } from '../utils/colors.js';

export const data = new SlashCommandBuilder()
  .setName('inventaire')
  .setNameLocalizations({ fr: 'inventaire' })
  .setDescription('Affiche votre inventaire complet')
  .addUserOption(option =>
    option
      .setName('joueur')
      .setDescription("Le membre dont vous voulez voir l'inventaire")
      .setRequired(false)
  );

export async function execute(interaction) {
  await interaction.deferReply();

  const targetUser = interaction.options.getUser('joueur') || interaction.user;

  try {
    const player = await Player.findOne({ userId: targetUser.id });

    if (!player) {
      return await interaction.editReply({
        content: '❌ Profil non trouvé.',
        ephemeral: true,
      });
    }

    // ---- Tickets (source de vérité = gachaTickets) ----
    const gachaTickets = Number(player.gachaTickets ?? 0);

    // ---- Regroupe les items (et filtre les "tickets" de l'inventaire) ----
    const itemGroups = {};
    for (const it of (player.inventory || [])) {
      const name = it.itemName || it.itemId || '';
      // On exclut les vieux items "ticket" pour éviter le doublon d’affichage
      if (/ticket|🎟️/i.test(name)) continue;

      const qty = Number(it.quantity ?? 1);
      itemGroups[name] = (itemGroups[name] || 0) + qty;
    }

    // ---- Catégorisation ----
    const categorized = {
      fight: [],
      heal: [],
      use: [],
      other: [],
    };

    for (const [emojiOrKey, quantity] of Object.entries(itemGroups)) {
      // getItemCategory(emojiOrKey) doit renvoyer { category, description } ou similaire
      const meta = getItemCategory?.(emojiOrKey) || {};
      const cat = (meta.category || '').toLowerCase();

      const entry = {
        emoji: emojiOrKey,            // on garde l’emoji / clé telle quelle
        quantity,
        description: meta.description || '', // courte description si dispo
      };

      if (cat === 'fight') categorized.fight.push(entry);
      else if (cat === 'heal' || cat === 'soins') categorized.heal.push(entry);
      else if (cat === 'use' || cat === 'utilitaire' || cat === 'utility') categorized.use.push(entry);
      else categorized.other.push(entry);
    }

    // ---- Construction du texte d'objets (une colonne) ----
    function section(label, arr) {
      if (!arr.length) return '';
      const lines = arr
        .sort((a, b) => (a.emoji || '').localeCompare(b.emoji || ''))
        .map(i => `${i.quantity}x ${i.emoji}${i.description ? ` — ${i.description}` : ''}`)
        .join('\n');
      return `**${label}**\n${lines}\n\n`;
    }

    let objectsText = '';
    objectsText += section('Fight', categorized.fight);
    objectsText += section('Soins', categorized.heal);
    objectsText += section('Utilitaires', categorized.use);
    if (!objectsText) {
      // S’il n’y a rien dans les 3 catégories, on montre Divers ou “Aucun objet”
      objectsText = categorized.other.length
        ? section('Divers', categorized.other)
        : '*Aucun objet*';
    }

    // ---- Thumbnail : perso équipé sinon avatar ----
    const equippedChar = player.equippedCharacter;
    const thumbnailURL = equippedChar?.image
      ? equippedChar.image
      : targetUser.displayAvatarURL({ dynamic: true });

    const embed = new EmbedBuilder()
      .setColor(COLORS?.INVENTORY || '#3498DB')
      .setTitle(`🎒 Inventaire — ${targetUser.username}`)
      .setDescription(objectsText)
      .setThumbnail(thumbnailURL)
      .addFields(
        {
          name: '💰 GotCoins',
          value: String(player.economy?.coins ?? 0),
          inline: true,
        },
        {
          name: '🎟️ Tickets',
          value: String(gachaTickets), // ✅ gachaTickets (plus economy.tickets)
          inline: true,
        }
      )
      .setTimestamp();

    await interaction.editReply({ embeds: [embed] });

  } catch (error) {
    console.error('Erreur dans la commande /inventaire:', error);
    await interaction.editReply({
      content: '❌ Une erreur est survenue lors de la récupération de l’inventaire.',
      ephemeral: true,
    });
  }
}

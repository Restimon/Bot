import { SlashCommandBuilder, EmbedBuilder, PermissionFlagsBits } from 'discord.js';
import { LootBox } from '../database/models/LootBox.js';
import { MessageCounter } from '../database/models/MessageCounter.js';
import { Player } from '../database/models/Player.js';
import { generateRandomItem } from '../utils/items.js';

export const data = new SlashCommandBuilder()
  .setName('test-loot')
  .setDescription('[TEST] Déclenche manuellement un loot box')
  .setDefaultMemberPermissions(PermissionFlagsBits.Administrator);

const LOOT_EMOJI = '📦';
const LOOT_TIMEOUT = 30000; // 30 seconds
const MAX_PARTICIPANTS = 5;

export async function execute(interaction) {
  await interaction.deferReply({ ephemeral: true });

  try {
    // Check if there's already an active loot box
    const counter = await MessageCounter.findOne({ guildId: interaction.guild.id });

    if (counter && counter.hasActiveLootBox) {
      return await interaction.editReply({
        content: '❌ Un loot box est déjà actif sur ce serveur.',
        ephemeral: true,
      });
    }

    // Create the embed
    const embed = new EmbedBuilder()
      .setColor('#5865F2')
      .setTitle('📦 Ravitaillement détruit')
      .setDescription('Réagissez avec 📦 pour participer !\n**5 premiers joueurs seulement**')
      .setFooter({ text: 'Expire dans 30 secondes • [TEST MODE]' })
      .setTimestamp(Date.now() + LOOT_TIMEOUT);

    const lootMessage = await interaction.channel.send({ embeds: [embed] });
    await lootMessage.react(LOOT_EMOJI);

    // Create loot box entry
    const lootBox = await LootBox.create({
      guildId: interaction.guild.id,
      channelId: interaction.channel.id,
      messageId: lootMessage.id,
      participants: [],
      isActive: true,
      isOpened: false,
    });

    // Update counter
    if (counter) {
      counter.hasActiveLootBox = true;
      await counter.save();
    } else {
      await MessageCounter.create({
        guildId: interaction.guild.id,
        messageCount: 0,
        nextTrigger: Math.floor(Math.random() * 11) + 5,
        hasActiveLootBox: true,
      });
    }

    await interaction.editReply({
      content: '✅ Loot box de test créé !',
      ephemeral: true,
    });

    // Create reaction collector
    const filter = (reaction, user) => {
      return reaction.emoji.name === LOOT_EMOJI && !user.bot;
    };

    const collector = lootMessage.createReactionCollector({
      filter,
      time: LOOT_TIMEOUT,
      max: MAX_PARTICIPANTS,
    });

    collector.on('collect', async (reaction, user) => {
      const alreadyParticipated = lootBox.participants.some(p => p.userId === user.id);

      if (!alreadyParticipated && lootBox.participants.length < MAX_PARTICIPANTS) {
        const item = generateRandomItem();

        lootBox.participants.push({
          userId: user.id,
          username: user.username,
          reactedAt: new Date(),
        });

        lootBox.rewards.push({
          userId: user.id,
          item: item,
        });

        await lootBox.save();
        console.log(`${user.username} joined test loot box (${lootBox.participants.length}/${MAX_PARTICIPANTS})`);
      }
    });

    collector.on('end', async () => {
      await handleLootBoxExpiry(lootMessage, lootBox, counter || await MessageCounter.findOne({ guildId: interaction.guild.id }));
    });

  } catch (error) {
    console.error('Error in /test-loot:', error);
    await interaction.editReply({
      content: '❌ Erreur lors de la création du loot box de test.',
      ephemeral: true,
    });
  }
}

async function handleLootBoxExpiry(lootMessage, lootBox, counter) {
  try {
    const updatedLootBox = await LootBox.findById(lootBox._id);
    if (!updatedLootBox) return;

    const participantCount = updatedLootBox.participants.length;

    if (participantCount === 0) {
      const embed = new EmbedBuilder()
        .setColor('#95A5A6')
        .setTitle('📦 Ravitaillement détruit')
        .setDescription('❌ Personne n\'a participé au ravitaillement.')
        .setTimestamp();

      await lootMessage.edit({ embeds: [embed] });
    } else {
      const participantsList = updatedLootBox.participants
        .map((p, index) => `${index + 1}. <@${p.userId}>`)
        .join('\n');

      const embed = new EmbedBuilder()
        .setColor('#F1C40F')
        .setTitle('📦 Ravitaillement récupéré')
        .setDescription(
          `✅ **${participantCount} joueur${participantCount > 1 ? 's ont' : ' a'} récupéré${participantCount > 1 ? 's' : ''} le ravitaillement !**\n\n${participantsList}\n\n*Utilisez la commande \`/ouvrir\` pour ouvrir votre loot box*`
        )
        .setFooter({ text: `${participantCount} participant${participantCount > 1 ? 's' : ''}` })
        .setTimestamp();

      await lootMessage.edit({ embeds: [embed] });

      for (const reward of updatedLootBox.rewards) {
        await Player.findOneAndUpdate(
          { userId: reward.userId },
          {
            $push: {
              inventory: {
                itemId: reward.item.itemId,
                itemName: reward.item.name,
                quantity: 1,
              }
            },
            $inc: {
              'economy.coins': reward.item.value,
            }
          },
          { upsert: true }
        );
      }
    }

    updatedLootBox.isActive = false;
    updatedLootBox.openedAt = new Date();
    await updatedLootBox.save();

    if (counter) {
      counter.hasActiveLootBox = false;
      await counter.save();
    }

  } catch (error) {
    console.error('Error handling loot box expiry:', error);
  }
}

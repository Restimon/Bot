import { Events, EmbedBuilder } from 'discord.js';
import { MessageCounter } from '../database/models/MessageCounter.js';
import { LootBox } from '../database/models/LootBox.js';
import { Player } from '../database/models/Player.js';
import { SpecialSupplyTracker } from '../database/models/SpecialSupplyTracker.js';
import { ActivitySession } from '../database/models/ActivitySession.js';
import { generateRandomItem, getRarityColor } from '../utils/items.js';
import { checkAndSpawnSpecialSupply } from '../utils/specialSupplyManager.js';
import { handleAIReply } from '../utils/ai-reply.js';

export const name = Events.MessageCreate;

const LOOT_EMOJI = '📦';
const LOOT_TIMEOUT = 30000; // 30 secondes
const MAX_PARTICIPANTS = 5;

export async function execute(message) {
  // Ignorer les DMs
  if (!message.guild) return;

  // Handle AI replies (before bot check so GotValis can reply)
  if (!message.author.bot) {
    await handleAIReply(message, message.client.user);
  }

  // Ignorer les messages de bots pour le reste
  if (message.author.bot) return;

  try {
    // Incrémenter le compteur de messages pour les stats et reward (1-3 GC per message, 15s cooldown)
    const player = await Player.findOne({ userId: message.author.id });

    let updates = {
      userId: message.author.id,
      username: message.author.username,
      $inc: { 'activity.messagesSent': 1 },
      lastUpdated: new Date(),
    };

    // Check if eligible for message reward (15s cooldown)
    const now = new Date();
    const canReward = !player?.activity?.lastMessageReward ||
                      (now - player.activity.lastMessageReward) >= 15000;

    if (canReward) {
      const reward = Math.floor(Math.random() * 3) + 1; // 1-3 GC
      updates.$inc['economy.coins'] = reward;
      updates.$inc['economy.totalEarned'] = reward;
      updates['activity.lastMessageReward'] = now;
    }

    await Player.findOneAndUpdate(
      { userId: message.author.id },
      updates,
      { upsert: true }
    );

    // Create message activity session (for 7-day tracking)
    await ActivitySession.create({
      userId: message.author.id,
      username: message.author.username,
      guildId: message.guild.id,
      type: 'message',
      startTime: now,
      endTime: now,  // Messages are instant
      duration: 0,
    });

    // Gérer le compteur de loot box
    let counter = await MessageCounter.findOne({ guildId: message.guild.id });

    if (!counter) {
      counter = await MessageCounter.create({
        guildId: message.guild.id,
        messageCount: 1,
        nextTrigger: Math.floor(Math.random() * 11) + 5, // 5-15
      });
      return;
    }

    // Increment special supply tracker
    let specialTracker = await SpecialSupplyTracker.findOne({ guildId: message.guild.id });
    if (specialTracker) {
      specialTracker.messagesSinceLastSupply += 1;
      await specialTracker.save();

      // Check for special supply spawn
      await checkAndSpawnSpecialSupply(message.guild, message.channel);
    }

    // Ne pas créer de loot box s'il y en a déjà un actif
    if (counter.hasActiveLootBox) {
      return;
    }

    // Incrémenter le compteur
    counter.messageCount += 1;
    counter.lastMessageAt = new Date();

    // Vérifier si on doit déclencher un loot box
    if (counter.messageCount >= counter.nextTrigger) {
      // Créer le loot box
      await createLootBox(message, counter);

      // Réinitialiser le compteur
      counter.messageCount = 0;
      counter.nextTrigger = Math.floor(Math.random() * 11) + 5; // 5-15
      counter.hasActiveLootBox = true;
      counter.lastLootBoxAt = new Date();
    }

    await counter.save();

  } catch (error) {
    console.error('Erreur dans messageCreate:', error);
  }
}

async function createLootBox(message, counter) {
  try {
    // Créer l'embed
    const embed = new EmbedBuilder()
      .setColor('#5865F2')
      .setTitle('📦 Ravitaillement détruit')
      .setDescription('Réagissez avec 📦 pour participer !\n**5 premiers joueurs seulement**')
      .setFooter({ text: 'Expire dans 30 secondes' })
      .setTimestamp(Date.now() + LOOT_TIMEOUT);

    const lootMessage = await message.channel.send({ embeds: [embed] });
    await lootMessage.react(LOOT_EMOJI);

    // Créer l'entrée dans la base de données
    const lootBox = await LootBox.create({
      guildId: message.guild.id,
      channelId: message.channel.id,
      messageId: lootMessage.id,
      participants: [],
      isActive: true,
      isOpened: false,
    });

    // Créer le collector
    const filter = (reaction, user) => {
      return reaction.emoji.name === LOOT_EMOJI && !user.bot;
    };

    const collector = lootMessage.createReactionCollector({
      filter,
      time: LOOT_TIMEOUT,
      max: MAX_PARTICIPANTS,
    });

    collector.on('collect', async (reaction, user) => {
      // Vérifier si l'utilisateur n'a pas déjà participé
      const alreadyParticipated = lootBox.participants.some(p => p.userId === user.id);

      if (!alreadyParticipated && lootBox.participants.length < MAX_PARTICIPANTS) {
        lootBox.participants.push({
          userId: user.id,
          username: user.username,
          reactedAt: new Date(),
        });

        // Générer un item pour ce participant
        const item = generateRandomItem();
        lootBox.rewards.push({
          userId: user.id,
          item: item,
        });

        await lootBox.save();

        console.log(`${user.username} a rejoint le loot box (${lootBox.participants.length}/${MAX_PARTICIPANTS})`);
      }
    });

    collector.on('end', async () => {
      await handleLootBoxExpiry(lootMessage, lootBox, counter);
    });

  } catch (error) {
    console.error('Erreur lors de la création du loot box:', error);
  }
}

async function handleLootBoxExpiry(lootMessage, lootBox, counter) {
  try {
    // Recharger le loot box
    const updatedLootBox = await LootBox.findById(lootBox._id);

    if (!updatedLootBox) return;

    const participantCount = updatedLootBox.participants.length;

    // Si personne n'a réagi
    if (participantCount === 0) {
      const noParticipantsEmbed = new EmbedBuilder()
        .setColor('#95A5A6')
        .setTitle('📦 Ravitaillement détruit')
        .setDescription('❌ Personne n\'a participé au ravitaillement.')
        .setTimestamp();

      await lootMessage.edit({ embeds: [noParticipantsEmbed] });
    } else {
      // Si des personnes ont réagi
      const participantsList = updatedLootBox.participants
        .map((p, index) => `${index + 1}. <@${p.userId}>`)
        .join('\n');

      const hasParticipantsEmbed = new EmbedBuilder()
        .setColor('#F1C40F')
        .setTitle('📦 Ravitaillement récupéré')
        .setDescription(
          `✅ **${participantCount} joueur${participantCount > 1 ? 's ont' : ' a'} récupéré${participantCount > 1 ? 's' : ''} le ravitaillement !**\n\n${participantsList}\n\n*Utilisez la commande \`/ouvrir\` pour ouvrir votre loot box*`
        )
        .setFooter({ text: `${participantCount} participant${participantCount > 1 ? 's' : ''}` })
        .setTimestamp();

      await lootMessage.edit({ embeds: [hasParticipantsEmbed] });

      // Ajouter les loot boxes à l'inventaire des joueurs
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

    // Marquer le loot box comme inactif
    updatedLootBox.isActive = false;
    updatedLootBox.openedAt = new Date();
    await updatedLootBox.save();

    // Réinitialiser le flag du serveur
    counter.hasActiveLootBox = false;
    await counter.save();

  } catch (error) {
    console.error('Erreur lors de l\'expiration du loot box:', error);
  }
}

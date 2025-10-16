import { Events, EmbedBuilder, PermissionFlagsBits } from 'discord.js';
import { MessageCounter } from '../database/models/MessageCounter.js';
import { LootBox } from '../database/models/LootBox.js';
import { Player } from '../database/models/Player.js';
import { SpecialSupplyTracker } from '../database/models/SpecialSupplyTracker.js';
import { ActivitySession } from '../database/models/ActivitySession.js';
import { generateRandomItem } from '../utils/items.js';
import { checkAndSpawnSpecialSupply } from '../utils/specialSupplyManager.js';
import { handleAIReply } from '../utils/ai-reply.js';

export const name = Events.MessageCreate;

const LOOT_EMOJI = '📦';
const BASIC_TIMEOUT = 30000;
const BASIC_MAX = 4;

export async function execute(message) {
  if (!message.guild) return;

  if (!message.author.bot) {
    await handleAIReply(message, message.client.user);
  }
  if (message.author.bot) return;

  try {
    const now = new Date();

    const player = await Player.findOne({ userId: message.author.id });
    const updates = {
      userId: message.author.id,
      username: message.author.username,
      $inc: { 'activity.messagesSent': 1 },
      lastUpdated: now,
    };

    const canReward = !player?.activity?.lastMessageReward || (now - player.activity.lastMessageReward) >= 15000;
    if (canReward) {
      const reward = Math.floor(Math.random() * 3) + 1;
      updates.$inc['economy.coins'] = reward;
      updates.$inc['economy.totalEarned'] = reward;
      updates['activity.lastMessageReward'] = now;
    }

    await Player.findOneAndUpdate({ userId: message.author.id }, updates, { upsert: true });

    await ActivitySession.create({
      userId: message.author.id,
      username: message.author.username,
      guildId: message.guild.id,
      type: 'message',
      startTime: now,
      endTime: now,
      duration: 0,
    });

    let counter = await MessageCounter.findOne({ guildId: message.guild.id });
    if (!counter) {
      counter = await MessageCounter.create({
        guildId: message.guild.id,
        messageCount: 1,
        nextTrigger: Math.floor(Math.random() * 11) + 5,
        hasActiveLootBox: false,
      });
      return;
    }

    let specialTracker = await SpecialSupplyTracker.findOne({ guildId: message.guild.id });
    if (specialTracker) {
      specialTracker.messagesSinceLastSupply += 1;
      await specialTracker.save();
      await checkAndSpawnSpecialSupply(message.guild, message.channel);
    }

    if (counter.hasActiveLootBox) return;

    counter.messageCount += 1;
    counter.lastMessageAt = now;

    if (counter.messageCount >= counter.nextTrigger) {
      counter.messageCount = 0;
      counter.nextTrigger = Math.floor(Math.random() * 11) + 5;
      counter.hasActiveLootBox = true;
      counter.lastLootBoxAt = now;
      await counter.save();

      await createLootBoxBasic(message, counter);
      return;
    }

    await counter.save();
  } catch (error) {
    console.error('Erreur dans messageCreate:', error);
  }
}

async function createLootBoxBasic(anchorMessage, counter) {
  try {
    const me = await anchorMessage.guild.members.fetchMe();
    const perms = anchorMessage.channel.permissionsFor(me);
    if (!perms?.has(PermissionFlagsBits.AddReactions) || !perms?.has(PermissionFlagsBits.SendMessages)) {
      counter.hasActiveLootBox = false;
      await counter.save().catch(() => {});
      return;
    }

    await anchorMessage.react(LOOT_EMOJI);

    const lootBox = await LootBox.create({
      guildId: anchorMessage.guild.id,
      channelId: anchorMessage.channel.id,
      messageId: anchorMessage.id,
      participants: [],
      rewards: [],
      isActive: true,
      isOpened: false,
    });

    const filter = (reaction, user) => reaction.emoji.name === LOOT_EMOJI && !user.bot;

    const collector = anchorMessage.createReactionCollector({
      filter,
      time: BASIC_TIMEOUT,
      max: BASIC_MAX,
    });

    collector.on('collect', async (reaction, user) => {
      if (lootBox.participants.some(p => p.userId === user.id)) return;
      if (lootBox.participants.length >= BASIC_MAX) return;

      lootBox.participants.push({
        userId: user.id,
        username: user.username,
        reactedAt: new Date(),
      });

      const item = generateRandomItem();
      lootBox.rewards.push({ userId: user.id, item });
      await lootBox.save();
    });

    collector.on('end', async () => {
      await handleLootBoxBasicExpiry(anchorMessage, lootBox, counter);
    });
  } catch (error) {
    console.error('Erreur createLootBoxBasic:', error);
    counter.hasActiveLootBox = false;
    await counter.save().catch(() => {});
  }
}

async function handleLootBoxBasicExpiry(anchorMessage, lootBox, counter) {
  try {
    const updatedLootBox = await LootBox.findById(lootBox._id);
    if (!updatedLootBox) return;

    const participantCount = updatedLootBox.participants.length;

    if (participantCount === 0) {
      const noParticipantsEmbed = new EmbedBuilder()
        .setColor('#95A5A6')
        .setTitle('📦 Ravitaillement détruit')
        .setDescription('❌ Personne n’a participé au ravitaillement.')
        .setTimestamp();

      await anchorMessage.channel.send({ embeds: [noParticipantsEmbed] });
    } else {
      const lines = updatedLootBox.rewards
        .map(r => {
          const icon = r.item.emoji || '⚡';
          return `✅ <@${r.userId}> a récupéré : ${icon}`;
        })
        .join('\n');

      const hasParticipantsEmbed = new EmbedBuilder()
        .setColor('#2ECC71')
        .setTitle('📦 Ravitaillement récupéré')
        .setDescription(lines)
        .setTimestamp();

      await anchorMessage.channel.send({ embeds: [hasParticipantsEmbed] });

      for (const reward of updatedLootBox.rewards) {
        await Player.findOneAndUpdate(
          { userId: reward.userId },
          {
            $push: {
              inventory: {
                itemId: reward.item.itemId,
                itemName: reward.item.name,
                quantity: 1,
              },
            },
            $inc: { 'economy.coins': reward.item.value },
          },
          { upsert: true }
        );
      }
    }

    updatedLootBox.isActive = false;
    updatedLootBox.openedAt = new Date();
    await updatedLootBox.save();

    counter.hasActiveLootBox = false;
    await counter.save();
  } catch (error) {
    console.error('Erreur handleLootBoxBasicExpiry:', error);
    counter.hasActiveLootBox = false;
    await counter.save().catch(() => {});
  }
}

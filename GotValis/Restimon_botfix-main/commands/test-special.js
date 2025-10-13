import { SlashCommandBuilder, EmbedBuilder, PermissionFlagsBits } from 'discord.js';
import { SpecialSupply } from '../database/models/SpecialSupply.js';
import { SpecialSupplyTracker } from '../database/models/SpecialSupplyTracker.js';
import { Player } from '../database/models/Player.js';
import { generateSpecialSupplyReward, applyRewardToPlayer } from '../utils/rewards.js';

export const data = new SlashCommandBuilder()
  .setName('test-special')
  .setDescription('[TEST] Déclenche manuellement un ravitaillement spécial')
  .setDefaultMemberPermissions(PermissionFlagsBits.Administrator);

const SPECIAL_SUPPLY_EMOJI = '📦';
const SPECIAL_SUPPLY_DURATION = 300000; // 5 minutes
const MAX_PARTICIPANTS = 5;

export async function execute(interaction) {
  await interaction.deferReply({ ephemeral: true });

  try {
    // Check if there's already an active special supply
    const tracker = await SpecialSupplyTracker.findOne({ guildId: interaction.guild.id });

    if (tracker && tracker.hasActiveSupply) {
      return await interaction.editReply({
        content: '❌ Un ravitaillement spécial est déjà actif sur ce serveur.',
        ephemeral: true,
      });
    }

    // Create the embed
    const embed = new EmbedBuilder()
      .setColor('#F39C12')
      .setTitle('📦 Ravitaillement spécial GotValis')
      .setDescription(
        `Réagissez avec ${SPECIAL_SUPPLY_EMOJI} pour récupérer une récompense surprise !\n` +
        `⏱️ Disponible pendant 5 minutes, maximum 5 personnes.`
      )
      .setTimestamp(Date.now() + SPECIAL_SUPPLY_DURATION)
      .setFooter({ text: 'Ravitaillement spécial • [TEST MODE]' });

    const message = await interaction.channel.send({ embeds: [embed] });
    await message.react(SPECIAL_SUPPLY_EMOJI);

    // Create database entry
    const specialSupply = await SpecialSupply.create({
      guildId: interaction.guild.id,
      channelId: interaction.channel.id,
      messageId: message.id,
      participants: [],
      isActive: true,
      isCompleted: false,
    });

    // Update or create tracker
    if (tracker) {
      tracker.hasActiveSupply = true;
      tracker.activeSupplyId = specialSupply._id;
      await tracker.save();
    } else {
      await SpecialSupplyTracker.create({
        guildId: interaction.guild.id,
        lastActiveChannelId: interaction.channel.id,
        hasActiveSupply: true,
        activeSupplyId: specialSupply._id,
        messagesSinceLastSupply: 0,
      });
    }

    await interaction.editReply({
      content: '✅ Ravitaillement spécial de test créé !',
      ephemeral: true,
    });

    console.log(`✨ TEST: Special supply spawned in ${interaction.channel.name}`);

    // Create reaction collector
    const filter = (reaction, user) => {
      return reaction.emoji.name === SPECIAL_SUPPLY_EMOJI && !user.bot;
    };

    const collector = message.createReactionCollector({
      filter,
      time: SPECIAL_SUPPLY_DURATION,
      max: MAX_PARTICIPANTS,
    });

    collector.on('collect', async (reaction, user) => {
      await handleParticipant(specialSupply, user);
    });

    collector.on('end', async () => {
      await completeSpecialSupply(message, specialSupply, tracker || await SpecialSupplyTracker.findOne({ guildId: interaction.guild.id }));
    });

  } catch (error) {
    console.error('Error in /test-special:', error);
    await interaction.editReply({
      content: '❌ Erreur lors de la création du ravitaillement spécial de test.',
      ephemeral: true,
    });
  }
}

async function handleParticipant(specialSupply, user) {
  try {
    const supply = await SpecialSupply.findById(specialSupply._id);
    if (!supply || !supply.isActive) return;

    const alreadyParticipated = supply.participants.some(p => p.userId === user.id);
    if (alreadyParticipated || supply.participants.length >= MAX_PARTICIPANTS) return;

    const reward = generateSpecialSupplyReward();

    supply.participants.push({
      userId: user.id,
      username: user.username,
      reactedAt: new Date(),
      reward: {
        type: reward.type,
        details: reward.details,
      }
    });

    await supply.save();
    console.log(`${user.username} joined special supply (${supply.participants.length}/${MAX_PARTICIPANTS})`);

  } catch (error) {
    console.error('Error handling participant:', error);
  }
}

async function completeSpecialSupply(message, specialSupply, tracker) {
  try {
    const supply = await SpecialSupply.findById(specialSupply._id);
    if (!supply) return;

    const participantCount = supply.participants.length;

    if (participantCount === 0) {
      const embed = new EmbedBuilder()
        .setColor('#95A5A6')
        .setTitle('📦 Ravitaillement spécial GotValis')
        .setDescription('❌ Personne n\'a récupéré le ravitaillement spécial.')
        .setTimestamp();

      await message.edit({ embeds: [embed] });
    } else {
      const rewardLines = [];

      for (const participant of supply.participants) {
        const reward = participant.reward;
        let rewardDescription = '';

        switch (reward.type) {
          case 'item':
            rewardDescription = `${reward.details.emoji} ${reward.details.name}${reward.details.quantity > 1 ? ` x${reward.details.quantity}` : ''}`;
            break;
          case 'ticket':
            rewardDescription = '🎫 1 Ticket';
            break;
          case 'coins':
            rewardDescription = `🪙 ${reward.details.amount} GotCoins`;
            break;
          case 'damage':
            rewardDescription = `${reward.details.amount} dégâts (PV: ${reward.details.hp})`;
            break;
          case 'heal':
            const critText = reward.details.critChance > 0 ? ` (Crit ${reward.details.critChance}%)` : '';
            rewardDescription = `Restaure ${reward.details.amount} PV${critText}`;
            break;
          case 'status_effect':
            rewardDescription = `${reward.details.emoji} ${reward.details.name}`;
            break;
        }

        let rewardEmoji = '🎁';
        if (reward.type === 'damage') rewardEmoji = '💥';
        else if (reward.type === 'heal') rewardEmoji = '💚';
        else if (reward.type === 'item') rewardEmoji = reward.details.emoji;

        rewardLines.push(`${rewardEmoji} @${participant.username} a obtenu ${rewardDescription}`);

        await applyRewardToPlayer(Player, participant.userId, {
          type: reward.type,
          details: reward.details,
          description: rewardDescription,
        });
      }

      const embed = new EmbedBuilder()
        .setColor('#2ECC71')
        .setTitle('📦 Récapitulatif du ravitaillement')
        .setDescription(rewardLines.join('\n'))
        .setFooter({ text: `${participantCount} participant${participantCount > 1 ? 's' : ''}` })
        .setTimestamp();

      await message.edit({ embeds: [embed] });
    }

    supply.isActive = false;
    supply.isCompleted = true;
    supply.completedAt = new Date();
    await supply.save();

    if (tracker) {
      tracker.hasActiveSupply = false;
      tracker.activeSupplyId = null;
      await tracker.save();
    }

  } catch (error) {
    console.error('Error completing special supply:', error);
  }
}

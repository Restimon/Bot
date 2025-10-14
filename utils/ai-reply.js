import OpenAI from 'openai';
import { config } from '../config.js';
import { AI_REPLY_CHANCE, AI_ALWAYS_REPLY_ON_MENTION, GOTVALIS_BOT_ID } from '../config/constants.js';
import { awardGotValis } from './gotvalis.js';

const openai = new OpenAI({
  apiKey: config.openaiApiKey,
});

// Check if bot should reply to a message
export function shouldReply(message, botUser) {
  // Always reply if mentioned
  if (AI_ALWAYS_REPLY_ON_MENTION && message.mentions.has(botUser)) {
    return true;
  }

  // Reply to direct replies
  if (message.reference && message.reference.userId === botUser.id) {
    return true;
  }

  // Only reply on mention or reply - no random chance
  return false;
}

// Generate AI reply using ChatGPT
export async function generateAIReply(message) {
  try {
    const messageContent = message.content.replace(/<@!?\d+>/g, '').trim();

    const completion = await openai.chat.completions.create({
      model: 'gpt-3.5-turbo',
      messages: [
        {
          role: 'system',
          content: 'Tu es GotValis, un bot Discord amical et utile qui parle français. Tu es là pour aider les joueurs avec leur progression dans le jeu. Réponds de manière naturelle, amicale et en français. Garde tes réponses courtes (2-3 phrases maximum).'
        },
        {
          role: 'user',
          content: messageContent || 'Salut!'
        }
      ],
      max_tokens: 150,
      temperature: 0.8,
    });

    return completion.choices[0].message.content.trim();

  } catch (error) {
    console.error('Error generating AI reply:', error);

    // Fallback responses in French
    const fallbacks = [
      'Désolé, je n\'ai pas pu comprendre. Peux-tu reformuler?',
      'Hmm, je réfléchis... Essaie de me poser une question différemment!',
      'Je suis un peu occupé en ce moment, mais je suis là pour t\'aider!',
      'Intéressant! Dis-m\'en plus.',
    ];

    return fallbacks[Math.floor(Math.random() * fallbacks.length)];
  }
}

// Handle AI reply and award coins to GotValis
export async function handleAIReply(message, botUser) {
  try {
    if (!shouldReply(message, botUser)) {
      return false;
    }

    await message.channel.sendTyping();

    const reply = await generateAIReply(message);

    await message.reply(reply);

    // Award GotValis for replying
    await awardGotValis(1, 'AI message reply');

    console.log(`🤖 GotValis replied to ${message.author.username}: "${reply}"`);

    return true;

  } catch (error) {
    console.error('Error handling AI reply:', error);
    return false;
  }
}

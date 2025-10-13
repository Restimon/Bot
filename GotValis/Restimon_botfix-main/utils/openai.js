import OpenAI from 'openai';
import { config } from '../config.js';

const openai = new OpenAI({
  apiKey: config.openaiApiKey,
});

export async function getAIDescription(player) {
  try {
    const prompt = `Tu es un narrateur de jeu vidéo. Génère une courte description personnalisée (max 2 phrases) pour ce joueur basée sur ses stats:
- Dégâts: ${player.stats.damages}
- Soins: ${player.stats.heals}
- K/D/A: ${player.stats.kills}/${player.stats.deaths}/${player.stats.assists}
- Messages: ${player.activity.messagesSent}
- Niveau: ${player.level}

Réponds uniquement en français et sois créatif et encourageant.`;

    const completion = await openai.chat.completions.create({
      model: 'gpt-3.5-turbo',
      messages: [
        {
          role: 'system',
          content: 'Tu es un narrateur enthousiaste qui crée des descriptions courtes et motivantes pour les joueurs.'
        },
        {
          role: 'user',
          content: prompt
        }
      ],
      max_tokens: 100,
      temperature: 0.8,
    });

    return completion.choices[0].message.content.trim();

  } catch (error) {
    console.error('Erreur OpenAI:', error);
    return `Voici le profil de ${player.username}, un joueur prometteur !`;
  }
}

export async function generateWelcomeMessage(member, customMessage) {
  try {
    // Remplacer les variables dans le message personnalisé
    let message = customMessage
      .replace('{user}', `<@${member.id}>`)
      .replace('{server}', member.guild.name)
      .replace('{username}', member.user.username);

    // Ajouter une touche d'IA si demandé
    const completion = await openai.chat.completions.create({
      model: 'gpt-3.5-turbo',
      messages: [
        {
          role: 'system',
          content: 'Tu génères des messages de bienvenue chaleureux et courts (1-2 phrases) en français.'
        },
        {
          role: 'user',
          content: `Améliore ce message de bienvenue: "${message}"`
        }
      ],
      max_tokens: 80,
      temperature: 0.7,
    });

    return completion.choices[0].message.content.trim();

  } catch (error) {
    console.error('Erreur OpenAI pour message de bienvenue:', error);
    return customMessage
      .replace('{user}', `<@${member.id}>`)
      .replace('{server}', member.guild.name)
      .replace('{username}', member.user.username);
  }
}

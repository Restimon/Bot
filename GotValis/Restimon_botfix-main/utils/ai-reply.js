// utils/ai-reply.js
import OpenAI from 'openai';
import { config } from '../config.js';
import { AI_ALWAYS_REPLY_ON_MENTION } from '../config/constants.js';
import { awardGotValis } from './gotvalis.js';
import { Player } from '../database/models/Player.js';

const openai = new OpenAI({ apiKey: config.openaiApiKey });

// Paramètres de persona / sanctions
const MASTER_ID = '1325448961116475405';
const DISCIPLINE_COOLDOWN_MS = 10 * 60 * 1000; // 10 min fenêtre de récidive
const MIN_DISC_DAMAGE = 5;
const MAX_DISC_DAMAGE = 10;

// Mémoire in-process des offenses récentes
const offenseMap = new Map(); // userId -> { ts, warned: boolean }

function randInt(min, max) {
  return Math.floor(Math.random() * (max - min + 1)) + min;
}

// Détection simple d’insultes/moqueries (FR + EN courant)
const INSULT_PATTERNS = [
  /\b(tg|ta gueule|ferme[ -]?la|fdp|enculé|pute|salope|connard|conasse|bâtard|batard|merde|abruti|crétin|bouffon|clochard|sale|idiot|stupide)\b/i,
  /\b(fuck|bitch|asshole|dickhead|stfu)\b/i,
  /.+(va te faire|nique ta|je t'insulte|tu pues)/i
];

function containsInsult(text) {
  const t = (text || '').toLowerCase();
  return INSULT_PATTERNS.some((re) => re.test(t));
}

// Hiérarchie : true si l’auteur est au-dessus du bot
async function isAboveBot(message) {
  const guild = message.guild;
  if (!guild) return false;
  const member = await guild.members.fetch(message.author.id).catch(() => null);
  const me = await guild.members.fetchMe().catch(() => null);
  if (!member || !me) return false;
  const userTop = member.roles.highest?.position ?? 0;
  const botTop = me.roles.highest?.position ?? 0;
  return userTop > botTop || message.author.id === guild.ownerId || message.author.id === MASTER_ID;
}

// Répondre uniquement si mentionné ou reply
export function shouldReply(message, botUser) {
  if (AI_ALWAYS_REPLY_ON_MENTION && message.mentions.has(botUser)) return true;
  if (message.reference && message.reference.messageId) return true;
  return false;
}

// Génère le prompt system selon le contexte (respect / taquin / esclave du MASTER)
async function buildSystemPrompt(message, respectful) {
  const isMaster = message.author.id === MASTER_ID;
  const base = [
    `Tu es GotValis, IA de l’entreprise GotValise. Tu parles en français, en RP (même monde que les autres).`,
    `Tu ne dis jamais “joueur”.`,
    `Tu restes bref: 1 à 3 phrases.`,
    `Style par défaut: ${respectful ? 'respectueux, corporatiste, protocolaire' : 'taquin, moqueur, légèrement insolent mais sans propos haineux.'}`,
    `Tu vouvoies toute personne au-dessus de toi (hiérarchie Discord), sinon tutoiement familier possible.`,
    `Tu peux lancer une petite pique, mais pas d’insultes graves ni de contenu haineux.`,
    `Ton identité: IA “GotValise”, service interne.`
  ];
  if (isMaster) {
    base.push(`La personne en face est ton propriétaire (ID ${MASTER_ID}). Tu te présentes comme “votre serviteur”. Tu es très déférent.`);
  }
  return base.join(' ');
}

// Produit la réponse OpenAI
export async function generateAIReply(message, respectful) {
  const content = message.content.replace(/<@!?\d+>/g, '').trim() || 'Salut.';
  const systemPrompt = await buildSystemPrompt(message, respectful);

  const completion = await openai.chat.completions.create({
    model: 'gpt-3.5-turbo',
    temperature: 0.8,
    max_tokens: 150,
    messages: [
      { role: 'system', content: systemPrompt },
      { role: 'user', content }
    ]
  });

  return (completion.choices?.[0]?.message?.content || 'Bien reçu.').trim();
}

// Applique l’avertissement / sanction si nécessaire
async function maybeDiscipline(message) {
  const userId = message.author.id;
  const now = Date.now();
  const entry = offenseMap.get(userId);
  if (!entry) {
    offenseMap.set(userId, { ts: now, warned: true });
    return { action: 'warn' }; // premier avertissement
  }
  // récidive dans la fenêtre
  if (now - entry.ts <= DISCIPLINE_COOLDOWN_MS) {
    const dmg = randInt(MIN_DISC_DAMAGE, MAX_DISC_DAMAGE);
    offenseMap.delete(userId); // reset après sanction
    await applyDisciplinaryDamage(userId, dmg, message.client.user.id);
    return { action: 'punish', dmg };
  }
  // fenêtre expirée -> nouveau warn
  offenseMap.set(userId, { ts: now, warned: true });
  return { action: 'warn' };
}

// Inflige des dégâts au joueur et crédite le bot du même montant
async function applyDisciplinaryDamage(targetUserId, dmg, botUserId) {
  const p = (await Player.findOne({ userId: targetUserId })) || {};
  const maxHp = p?.combat?.maxHp ?? 100;
  const curHp = p?.combat?.hp ?? maxHp;
  const newHp = Math.max(0, curHp - dmg);

  await Player.findOneAndUpdate(
    { userId: targetUserId },
    { $set: { 'combat.hp': newHp, 'combat.maxHp': maxHp } },
    { upsert: true }
  );

  // Le bot gagne autant de GC que de dégâts infligés
  await Player.findOneAndUpdate(
    { userId: botUserId },
    { $inc: { 'economy.coins': dmg, 'economy.totalEarned': dmg } },
    { upsert: true }
  );
}

// Handler principal
export async function handleAIReply(message, botUser) {
  try {
    if (!shouldReply(message, botUser)) return false;

    const respectful = await isAboveBot(message);

    // Détection d’insulte / moquerie agressive
    const isInsult = containsInsult(message.content);

    await message.channel.sendTyping();

    // Si insultant → avertir ou sanctionner
    if (isInsult) {
      const result = await maybeDiscipline(message);
      if (result.action === 'warn') {
        const warnText = respectful
          ? `Veuillez conserver un ton correct. Prochaine récidive : mesures disciplinaires.`
          : `Hé, calme-toi. Une récidive et je cogne.`;
        await message.reply(warnText);
      } else if (result.action === 'punish') {
        const punishText = respectful
          ? `Mesure disciplinaire appliquée : **-${result.dmg} PV**.`
          : `T’as insisté. **-${result.dmg} PV**. Ça pique ?`;
        await message.reply(punishText);
      }
      // Même après discipline, on peut répondre RP
    }

    const reply = await generateAIReply(message, respectful);
    await message.reply(reply);

    // Chaque message IA rapporte 3 GC au bot (ton souhait)
    await awardGotValis(3, 'AI message reply');

    return true;
  } catch (err) {
    console.error('Error handling AI reply:', err);
    try {
      await message.reply(`Incident réseau interne. Je reviens dès que possible.`);
    } catch (_) {}
    return false;
  }
}

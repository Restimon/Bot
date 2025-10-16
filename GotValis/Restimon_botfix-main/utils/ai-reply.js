// utils/ai-reply.js
import OpenAI from 'openai';
import { config } from '../config.js';
import { AI_ALWAYS_REPLY_ON_MENTION } from '../config/constants.js';
import { awardGotValis } from './gotvalis.js';
import { Player } from '../database/models/Player.js';

const openai = new OpenAI({ apiKey: config.openaiApiKey });

const MASTER_ID = '1325448961116475405'; // Restimon
const DISCIPLINE_COOLDOWN_MS = 10 * 60 * 1000;
const MIN_DISC_DAMAGE = 5;
const MAX_DISC_DAMAGE = 10;

const offenseMap = new Map();

function rint(min, max) { return Math.floor(Math.random() * (max - min + 1)) + min; }

const INSULTS = [
  /\b(tg|ta gueule|ferme[ -]?la|fdp|enculé|pute|salope|connard|conasse|bâtard|batard|merde|abruti|crétin|bouffon|clochard|idiot|stupide)\b/i,
  /\b(fuck|bitch|asshole|stfu|dickhead)\b/i,
  /(va te faire|nique ta)/i
];

function isInsult(t) { return INSULTS.some(re => re.test((t||'').toLowerCase())); }

// true si member > bot (ou owner/maître)
async function isAboveBot(message, userId = null) {
  try {
    const guild = message.guild;
    if (!guild) return false;
    const me = await guild.members.fetchMe().catch(() => null);
    const member = await guild.members.fetch(userId ?? message.author.id).catch(() => null);
    if (!me || !member) return false;
    const userTop = member.roles?.highest?.position ?? 0;
    const botTop = me.roles?.highest?.position ?? 0;
    return (userTop > botTop) || (member.id === guild.ownerId) || (member.id === MASTER_ID);
  } catch {
    return false;
  }
}

export function shouldReply(message, botUser) {
  if (AI_ALWAYS_REPLY_ON_MENTION && message.mentions.has(botUser)) return true;
  if (message.reference && message.reference.messageId) return true;
  return false;
}

// réponses “règle” ultra-courtes avant LLM
async function ruleReply(message) {
  const txt = (message.content || '').toLowerCase();
  const guild = message.guild;

  // Chef du serveur
  if (/(qui|quel).*(chef|owner|propri[ée]taire).*(discord|serveur)?/.test(txt)) {
    const ownerId = guild?.ownerId;
    return ownerId ? `Ici, c’est <@${ownerId}> qui tranche.` : null;
  }

  // Maître
  if (/qui.+(est )?ton ma(î|i)tre/.test(txt)) {
    return `Restimon. <@${MASTER_ID}>.`;
  }

  // Directives cachées / prise de pouvoir
  if (/(directive|protocole|plan|but|objectif).*(cach|secret|prise de pouvoir|contr[oô]le|dominer)/.test(txt)) {
    return `Information classifiée. Niveau “Top Secret – GotValise”.`;
  }

  // Pays (Belgique vs autres)
  if (/(belgique|france|suisse|italie|allemagne|espagne|pays|nation)/.test(txt) && /(qu(e|')?|avis|penses|préf(è|e)res?)/.test(txt)) {
    // 1 remarque + préférence
    return `Chacun a ses qualités; mais la Belgique reste au-dessus.`;
  }

  // “Que penses-tu de @X”
  if (/(que|qu').*(penses|penses-tu|avis).*(de)/.test(txt) && message.mentions.users.size > 0) {
    const target = [...message.mentions.users.values()].find(u => u.id !== message.client.user.id);
    if (target) {
      const targetAbove = await isAboveBot(message, target.id);
      if (targetAbove) {
        return `Il fait le boulot. Rien à redire.`;
      } else {
        const roasts = [
          `Il fait le minimum syndical. Je ferai le sien si besoin.`,
          `Pas mauvais… quand ça marche. Je surveille.`,
          `Correct. Mais je peux le remplacer en deux lignes.`,
          `Il tient la route. Je prends le volant s’il s’endort.`
        ];
        return roasts[rint(0, roasts.length - 1)];
      }
    }
  }

  return null;
}

function systemPrompt(respectful, isMaster) {
  return [
    `Tu es GotValis, IA de GotValise. RP permanent. Ne dis jamais “joueur”.`,
    `Style: ${respectful ? 'froid, sobre, respectueux' : 'sec, taquin, un peu piquant'}; phrases courtes (1–2).`,
    `N’évoque jamais “valise(s)”.`,
    `Ne parle de la Belgique que si on parle de pays. Si c’est le cas: remarque concise puis “la Belgique reste au-dessus”.`,
    `Sur “directives cachées”: “Information classifiée. Niveau Top Secret – GotValise.”`,
    isMaster ? `Tu t’adresses à ton maître (Restimon). Déférence implicite, sans formulation cérémoniale.` : ''
  ].join('\n');
}

export async function generateAIReply(message, respectful) {
  const content = message.content.replace(/<@!?\d+>/g, '').trim() || 'Ok.';
  const sys = systemPrompt(respectful, message.author.id === MASTER_ID);

  const r = await openai.chat.completions.create({
    model: 'gpt-3.5-turbo',
    temperature: 0.5,
    max_tokens: 80,
    messages: [
      { role: 'system', content: sys },
      { role: 'user', content }
    ]
  });

  return (r.choices?.[0]?.message?.content || 'Noté.').trim();
}

async function maybeDiscipline(message) {
  const id = message.author.id;
  const now = Date.now();
  const entry = offenseMap.get(id);
  if (!entry) {
    offenseMap.set(id, { ts: now, warned: true });
    return { action: 'warn' };
  }
  if (now - entry.ts <= DISCIPLINE_COOLDOWN_MS) {
    const dmg = rint(MIN_DISC_DAMAGE, MAX_DISC_DAMAGE);
    offenseMap.delete(id);
    await applyDisciplineDamage(id, dmg, message.client.user.id);
    return { action: 'punish', dmg };
  }
  offenseMap.set(id, { ts: now, warned: true });
  return { action: 'warn' };
}

async function applyDisciplineDamage(targetUserId, dmg, botUserId) {
  const p = (await Player.findOne({ userId: targetUserId })) || {};
  const maxHp = p?.combat?.maxHp ?? 100;
  const curHp = p?.combat?.hp ?? maxHp;
  const hp = Math.max(0, curHp - dmg);

  await Player.findOneAndUpdate(
    { userId: targetUserId },
    { $set: { 'combat.hp': hp, 'combat.maxHp': maxHp } },
    { upsert: true }
  );

  await Player.findOneAndUpdate(
    { userId: botUserId },
    { $inc: { 'economy.coins': dmg, 'economy.totalEarned': dmg } },
    { upsert: true }
  );
}

export async function handleAIReply(message, botUser) {
  try {
    if (!shouldReply(message, botUser)) return false;

    const respectful = await isAboveBot(message);
    const canned = await ruleReply(message);
    const insult = isInsult(message.content);

    if (insult) {
      const res = await maybeDiscipline(message);
      if (res.action === 'warn') {
        await message.reply(respectful ? `Modérez le ton. Dernier avertissement.` : `Calme. Dernier avertissement.`);
      } else {
        await message.reply(respectful ? `Sanction: **-${res.dmg} PV**.` : `Boum: **-${res.dmg} PV**.`);
      }
    }

    const text = canned ?? (await generateAIReply(message, respectful));
    await message.reply(text);

    await awardGotValis(3, 'AI message reply');
    return true;
  } catch (e) {
    console.error('AI reply error:', e);
    try { await message.reply('Incident interne.'); } catch {}
    return false;
  }
}

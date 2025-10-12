// utils/ai-reply.js
// ESM (package.json: "type": "module")

import OpenAI from 'openai';
import { EmbedBuilder } from 'discord.js';
import { config } from '../config.js';
import { AI_ALWAYS_REPLY_ON_MENTION } from '../config/constants.js';
import { awardGotValis } from './gotvalis.js';

// ───────────────────────────────────────────────────────────────────────────────
// Paramètres comportement
// ───────────────────────────────────────────────────────────────────────────────
const PROTECTED_USER_ID = '1325448961116475405'; // toujours respect
const WARN_WINDOW_MS = 3 * 60 * 1000;            // fenêtre récidive: 3 minutes
const MIN_DMG = 1;
const MAX_DMG = 5;

// ───────────────────────────────────────────────────────────────────────────────
/** Hooks optionnels :
 *  - setPunishHandler(fn): applique les “vrais” dégâts dans ton système
 *      fn(userId, dmg, reason, message) -> peut retourner { hpBefore, hpAfter }
 *  - setHpProvider(fn): retourne les PV actuels sans appliquer de dégâts
 *      fn(userId, message) -> number | Promise<number>
 */
let punishHandler = null;
let hpProvider = null;

export function setPunishHandler(fn) { punishHandler = fn; }
export function setHpProvider(fn) { hpProvider = fn; }

// ───────────────────────────────────────────────────────────────────────────────
// OpenAI client
// ───────────────────────────────────────────────────────────────────────────────
const openai = new OpenAI({ apiKey: config.openaiApiKey });

// ───────────────────────────────────────────────────────────────────────────────
// Modération basique: détection grossière + récidive
// ───────────────────────────────────────────────────────────────────────────────
const warnMap = new Map(); // userId -> timestamp dernier avertissement

const TOXIC_WORDS = [
  'fdp','tg','ta gueule','enculé','con','connard','pute','salope',
  'abruti','crétin','débile','merde','bouffon','clochard','noob de merde'
];

function targetsBot(message) {
  const isReplyToBot = message.reference && message.reference.userId === message.client.user.id;
  const mentionsBot = message.mentions?.has?.(message.client.user);
  return Boolean(isReplyToBot || mentionsBot);
}

function detectToxicity(message) {
  const content = (message.content || '').toLowerCase();
  if (!targetsBot(message)) return false;               // on punit seulement si ça vise le bot
  return TOXIC_WORDS.some(w => content.includes(w));
}

function estimateSeverity(message) {
  const content = (message.content || '').toLowerCase();
  let score = 0;
  for (const w of TOXIC_WORDS) if (content.includes(w)) score++;
  return Math.min(MAX_DMG, Math.max(MIN_DMG, score || 2)); // défaut 2 si ambigu
}

function scheduleWarn(userId, now) {
  const last = warnMap.get(userId);
  if (!last || now - last > WARN_WINDOW_MS) {
    warnMap.set(userId, now);
    return { isFirstWarn: true };
  }
  return { isFirstWarn: false };
}

function shouldPunish(userId) {
  // Deuxième message toxique dans la fenêtre → punition
  return warnMap.has(userId);
}

// ───────────────────────────────────────────────────────────────────────────────
// Rôles & ton
// ───────────────────────────────────────────────────────────────────────────────
function hasHigherRoleThanBot(member, botMember) {
  if (!member || !botMember) return false;
  const a = member.roles?.highest;
  const b = botMember.roles?.highest;
  if (!a || !b || typeof a.comparePositionTo !== 'function') return false;
  return a.comparePositionTo(b) > 0;
}

function buildSystemPrompt({ tone, targetIsProtected }) {
  const base = [
    "Tu es GotValis, un PNJ-boss d’un jeu Discord. Parle en français, 2–3 phrases max.",
    "Style: sarcastique, sûr de toi, pince-sans-rire. Jamais vulgaire.",
    "Reste dans l’univers du jeu si pertinent (statuts, combats, loot)."
  ];

  if (targetIsProtected) {
    base.push(
      "La personne est privilégiée: réponds avec respect poli, sans sous-entendus hostiles.",
      "Reste digne et concis."
    );
  } else if (tone === 'respect_but_undermine') {
    base.push(
      "La personne a un rôle au-dessus du tien: montre un respect visible, mais glisse des sous-entendus subtils du style “les places changent vite…”, “l’échiquier bouge…”.",
      "Ironie fine, jamais agressive. 2–3 phrases."
    );
  } else {
    base.push(
      "La personne n’est pas au-dessus de toi: adopte un ton hautain et moqueur, comme un boss qui prend les autres de haut.",
      "Évite la vulgarité ; préfère l'ironie sèche. 2–3 phrases."
    );
  }

  return base.join(' ');
}

// ───────────────────────────────────────────────────────────────────────────────
// Triggers: quand répondre
// ───────────────────────────────────────────────────────────────────────────────
export function shouldReply(message, botUser) {
  if (AI_ALWAYS_REPLY_ON_MENTION && message.mentions.has(botUser)) return true;
  if (message.reference && message.reference.userId === botUser.id) return true;
  return false; // pas de chance aléatoire ici
}

// ───────────────────────────────────────────────────────────────────────────────
// IA (réponse)
// ───────────────────────────────────────────────────────────────────────────────
export async function generateAIReply(message, { tone, targetIsProtected }) {
  const messageContent = message.content.replace(/<@!?\d+>/g, '').trim() || 'Salut.';
  const system = buildSystemPrompt({ tone, targetIsProtected });

  const completion = await openai.chat.completions.create({
    model: 'gpt-3.5-turbo', // tu peux passer à 'gpt-4o-mini' si tu préfères
    messages: [
      { role: 'system', content: system },
      { role: 'user', content: messageContent }
    ],
    max_tokens: 150,
    temperature: 0.8,
  });

  return completion.choices[0].message.content?.trim() || "…";
}

// ───────────────────────────────────────────────────────────────────────────────
// Modération + Sanction (embed style “combat / punition”)
// ───────────────────────────────────────────────────────────────────────────────
async function maybeModerate(message) {
  if (!detectToxicity(message)) return { acted: false };

  const userId = message.author.id;
  const now = Date.now();
  const warn = scheduleWarn(userId, now);

  // Avertissement n°1
  if (warn.isFirstWarn) {
    await message.reply("🧱 Calme-toi. La pique passe, l’irrespect non. Prochaine dérive = sanction.");
    return { acted: true, warned: true };
  }

  // Récidive dans la fenêtre → punition
  if (shouldPunish(userId)) {
    const dmg = estimateSeverity(message);

    // Récupération PV (si fournis par un provider) AVANT application
    let hpBefore = null;
    if (typeof hpProvider === 'function') {
      try { hpBefore = await hpProvider(userId, message); } catch {}
    }

    // Application “réelle” des dégâts si un handler est branché
    let applied = { hpBefore: hpBefore ?? null, hpAfter: null };
    if (typeof punishHandler === 'function') {
      try {
        const res = await punishHandler(userId, dmg, 'Sanction du Boss', message);
        if (res && (typeof res.hpBefore === 'number' || typeof res.hpAfter === 'number')) {
          applied = { hpBefore: res.hpBefore ?? hpBefore ?? null, hpAfter: res.hpAfter ?? null };
        }
      } catch (e) {
        console.error('[punishHandler] error:', e);
      }
    } else if (hpBefore != null) {
      // Si on a les PV avant mais pas de handler, on simule l’après
      applied.hpAfter = Math.max(0, hpBefore - dmg);
    }

    // Construction de l’embed RP (avec ou sans calcul selon data dispo)
    let desc;
    if (typeof applied.hpBefore === 'number' && typeof applied.hpAfter === 'number') {
      const before = applied.hpBefore;
      const after  = applied.hpAfter;
      desc =
        `⚔️ **GotValis inflige ${dmg} (sanction)** dégâts à ${message.author} !\n` +
        `${message.author} perd (${dmg} ❤️)\n\n` +
        `❤️ ${before} - (${dmg} ❤️) = ${after} ❤️`;
    } else {
      // Fallback sans infos HP exactes
      desc =
        `⚔️ **GotValis inflige ${dmg} (sanction)** dégâts à ${message.author} !\n` +
        `${message.author} perd (${dmg} ❤️)`;
    }

    const sanctionEmbed = new EmbedBuilder()
      .setColor('#D91818')
      .setTitle('💢 Sanction disciplinaire')
      .setDescription(desc)
      .setFooter({ text: 'Le Boss ne tolère pas l’irrespect.' })
      .setTimestamp();

    await message.channel.send({ embeds: [sanctionEmbed] });

    console.log(`[PUNISH] ${message.author.tag} -${dmg} HP (insolence)`);
    return { acted: true, punished: true, dmg, hpBefore: applied.hpBefore, hpAfter: applied.hpAfter };
  }

  return { acted: false };
}

// ───────────────────────────────────────────────────────────────────────────────
/** Pipeline principal : modère puis répond éventuellement */
// ───────────────────────────────────────────────────────────────────────────────
export async function handleAIReply(message, botUser) {
  try {
    const botMember = message.guild?.members?.me ?? null;

    // 1) Modération prioritaire (avertissement/punition même si pas de réponse IA)
    const mod = await maybeModerate(message);
    if (mod.acted && mod.punished) {
      // déjà sanctionné → ne pas “récompenser” par une réponse RP
      return true;
    }

    // 2) Décide si on répond
    if (!shouldReply(message, botUser)) {
      return mod.acted || false;
    }

    // 3) Calcule le “ton” (rôle + ID protégé)
    const targetIsProtected = message.author?.id === PROTECTED_USER_ID;
    const tone = targetIsProtected
      ? 'respect'
      : hasHigherRoleThanBot(message.member, botMember)
        ? 'respect_but_undermine'
        : 'condescending';

    // 4) Réponse IA
    await message.channel.sendTyping();
    const reply = await generateAIReply(message, { tone, targetIsProtected });
    await message.reply(reply);

    // 5) Récompense sociale
    try { await awardGotValis(1, 'AI message reply'); } catch {}

    console.log(`🤖 GotValis (${tone}) → ${message.author.tag}: "${reply}"`);
    return true;

  } catch (error) {
    console.error('Error handling AI reply:', error);
    const fallbacks = [
      "Reste à ta place… mais j’écoute.",
      "Doucement. Tu sais à qui tu t’adresses.",
      "Tu veux vraiment jouer à ça avec moi ?"
    ];
    try { await message.reply(fallbacks[Math.floor(Math.random()*fallbacks.length)]); } catch {}
    return false;
  }
}

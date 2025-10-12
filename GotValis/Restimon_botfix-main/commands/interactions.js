// commands/interactions.js
import { SlashCommandBuilder } from 'discord.js';

// Messages d'interaction
const INTERACTIONS = {
  slap: {
    self: (user) => `${user} se gifle lui-même... 🤦`,
    other: (user, target) => `${user} gifle ${target}! 👋💥`,
  },
  kiss: {
    self: (user) => `${user} s'embrasse dans le miroir... 💋`,
    other: (user, target) => `${user} embrasse ${target}! 💋❤️`,
  },
  hug: {
    self: (user) => `${user} se fait un câlin... 🤗`,
    other: (user, target) => `${user} fait un câlin à ${target}! 🤗💕`,
  },
  pat: {
    self: (user) => `${user} se tapote la tête... 😊`,
    other: (user, target) => `${user} tapote la tête de ${target}! 😊👋`,
  },
  bit: {
    self: (user) => `${user} se mord lui-même... 😬`,
    other: (user, target) => `${user} mord ${target}! 😬🦷`,
  },
  punch: {
    self: (user) => `${user} se donne un coup de poing... 🥊`,
    other: (user, target) => `${user} frappe ${target}! 🥊💥`,
  },
  love: {
    self: (user) => `${user} s'aime beaucoup... 💖`,
    other: (user, target) => `${user} aime ${target}! 💖✨`,
  },
  lick: {
    self: (user) => `${user} se lèche... 👅`,
    other: (user, target) => `${user} lèche ${target}! 👅💦`,
  },
};

// Liste d’actions pour les choix
const ACTIONS = Object.keys(INTERACTIONS);

// ✅ Une seule commande exportée (data + execute)
export const data = new SlashCommandBuilder()
  .setName('interactions')
  .setDescription('Effectue une interaction (slap, kiss, hug, etc.)')
  .addStringOption(option =>
    option
      .setName('action')
      .setDescription('Type d’interaction')
      .setRequired(true)
      .addChoices(
        ...ACTIONS.map(a => ({ name: a.charAt(0).toUpperCase() + a.slice(1), value: a }))
      )
  )
  .addUserOption(option =>
    option
      .setName('cible')
      .setDescription('La personne à cibler')
      .setRequired(false)
  );

export async function execute(interaction) {
  const action = interaction.options.getString('action');
  const target = interaction.options.getUser('cible');
  const user = interaction.user;

  const messages = INTERACTIONS[action];
  if (!messages) {
    return interaction.reply({ content: 'Interaction inconnue.', ephemeral: true });
  }

  const content =
    !target || target.id === user.id
      ? messages.self(user.toString())
      : messages.other(user.toString(), target.toString());

  await interaction.reply({ content });
}

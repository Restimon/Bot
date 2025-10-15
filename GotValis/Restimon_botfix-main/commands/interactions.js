import { SlashCommandBuilder } from 'discord.js';

const INTERACTIONS = {
  slap: {
    self: (user) => `${user} se gifle lui-même... 🤦`,
    other: (user, target) => `${user} gifle ${target}! 👋💥`
  },
  kiss: {
    self: (user) => `${user} s'embrasse dans le miroir... 💋`,
    other: (user, target) => `${user} embrasse ${target}! 💋❤️`
  },
  hug: {
    self: (user) => `${user} se fait un câlin... 🤗`,
    other: (user, target) => `${user} fait un câlin à ${target}! 🤗💕`
  },
  pat: {
    self: (user) => `${user} se tapote la tête... 😊`,
    other: (user, target) => `${user} tapote la tête de ${target}! 😊👋`
  },
  bit: {
    self: (user) => `${user} se mord lui-même... 😬`,
    other: (user, target) => `${user} mord ${target}! 😬🦷`
  },
  punch: {
    self: (user) => `${user} se donne un coup de poing... 🥊`,
    other: (user, target) => `${user} frappe ${target}! 🥊💥`
  },
  love: {
    self: (user) => `${user} s'aime beaucoup... 💖`,
    other: (user, target) => `${user} aime ${target}! 💖✨`
  },
  lick: {
    self: (user) => `${user} se lèche... 👅`,
    other: (user, target) => `${user} lèche ${target}! 👅💦`
  }
};

export const commands = [];

for (const [action, messages] of Object.entries(INTERACTIONS)) {
  const command = {
    data: new SlashCommandBuilder()
      .setName(action)
      .setDescription(`${action.charAt(0).toUpperCase() + action.slice(1)} quelqu'un`)
      .addUserOption(option =>
        option
          .setName('cible')
          .setDescription('La personne à cibler')
          .setRequired(false)
      ),
    async execute(interaction) {
      const target = interaction.options.getUser('cible');
      const user = interaction.user;

      const message = !target || target.id === user.id
        ? messages.self(user.toString())
        : messages.other(user.toString(), target.toString());

      await interaction.reply({ content: message });
    }
  };

  commands.push(command);
}

// Exports optionnels si tu veux aussi les importer individuellement
export const slap = commands[0];
export const kiss = commands[1];
export const hug = commands[2];
export const pat = commands[3];
export const bit = commands[4];
export const punch = commands[5];
export const love = commands[6];
export const lick = commands[7];

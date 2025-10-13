import { SlashCommandBuilder } from 'discord.js';

export const data = new SlashCommandBuilder()
  .setName('slap')
  .setDescription('Gifle quelqu\'un')
  .addUserOption(option =>
    option
      .setName('cible')
      .setDescription('La personne à gifler')
      .setRequired(false)
  );

export async function execute(interaction) {
  const target = interaction.options.getUser('cible');
  const user = interaction.user;

  let message;
  if (!target || target.id === user.id) {
    message = `${user} se gifle lui-même... 🤦`;
  } else {
    message = `${user} gifle ${target}! 👋💥`;
  }

  await interaction.reply({ content: message });
}

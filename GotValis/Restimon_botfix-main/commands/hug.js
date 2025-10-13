import { SlashCommandBuilder } from 'discord.js';

export const data = new SlashCommandBuilder()
  .setName('hug')
  .setDescription('Fait un câlin à quelqu\'un')
  .addUserOption(option =>
    option
      .setName('cible')
      .setDescription('La personne à câliner')
      .setRequired(false)
  );

export async function execute(interaction) {
  const target = interaction.options.getUser('cible');
  const user = interaction.user;

  let message;
  if (!target || target.id === user.id) {
    message = `${user} se fait un câlin... 🤗`;
  } else {
    message = `${user} fait un câlin à ${target}! 🤗💕`;
  }

  await interaction.reply({ content: message });
}

import { SlashCommandBuilder } from 'discord.js';

export const data = new SlashCommandBuilder()
  .setName('pat')
  .setDescription('Tapote la tête de quelqu\'un')
  .addUserOption(option =>
    option
      .setName('cible')
      .setDescription('La personne à tapoter')
      .setRequired(false)
  );

export async function execute(interaction) {
  const target = interaction.options.getUser('cible');
  const user = interaction.user;

  let message;
  if (!target || target.id === user.id) {
    message = `${user} se tapote la tête... 😊`;
  } else {
    message = `${user} tapote la tête de ${target}! 😊👋`;
  }

  await interaction.reply({ content: message });
}

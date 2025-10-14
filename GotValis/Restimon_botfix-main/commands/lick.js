import { SlashCommandBuilder } from 'discord.js';

export const data = new SlashCommandBuilder()
  .setName('lick')
  .setDescription('Lèche quelqu\'un')
  .addUserOption(option =>
    option
      .setName('cible')
      .setDescription('La personne à lécher')
      .setRequired(false)
  );

export async function execute(interaction) {
  const target = interaction.options.getUser('cible');
  const user = interaction.user;

  let message;
  if (!target || target.id === user.id) {
    message = `${user} se lèche... 👅`;
  } else {
    message = `${user} lèche ${target}! 👅💦`;
  }

  await interaction.reply({ content: message });
}

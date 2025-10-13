import { SlashCommandBuilder } from 'discord.js';

export const data = new SlashCommandBuilder()
  .setName('punch')
  .setDescription('Frappe quelqu\'un')
  .addUserOption(option =>
    option
      .setName('cible')
      .setDescription('La personne à frapper')
      .setRequired(false)
  );

export async function execute(interaction) {
  const target = interaction.options.getUser('cible');
  const user = interaction.user;

  let message;
  if (!target || target.id === user.id) {
    message = `${user} se donne un coup de poing... 🥊`;
  } else {
    message = `${user} frappe ${target}! 🥊💥`;
  }

  await interaction.reply({ content: message });
}

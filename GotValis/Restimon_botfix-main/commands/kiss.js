import { SlashCommandBuilder } from 'discord.js';

export const data = new SlashCommandBuilder()
  .setName('kiss')
  .setDescription('Embrasse quelqu\'un')
  .addUserOption(option =>
    option
      .setName('cible')
      .setDescription('La personne à embrasser')
      .setRequired(false)
  );

export async function execute(interaction) {
  const target = interaction.options.getUser('cible');
  const user = interaction.user;

  let message;
  if (!target || target.id === user.id) {
    message = `${user} s'embrasse dans le miroir... 💋`;
  } else {
    message = `${user} embrasse ${target}! 💋❤️`;
  }

  await interaction.reply({ content: message });
}

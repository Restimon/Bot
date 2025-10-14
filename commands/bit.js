import { SlashCommandBuilder } from 'discord.js';

export const data = new SlashCommandBuilder()
  .setName('bit')
  .setDescription('Mord quelqu\'un')
  .addUserOption(option =>
    option
      .setName('cible')
      .setDescription('La personne à mordre')
      .setRequired(false)
  );

export async function execute(interaction) {
  const target = interaction.options.getUser('cible');
  const user = interaction.user;

  let message;
  if (!target || target.id === user.id) {
    message = `${user} se mord lui-même... 😬`;
  } else {
    message = `${user} mord ${target}! 😬🦷`;
  }

  await interaction.reply({ content: message });
}

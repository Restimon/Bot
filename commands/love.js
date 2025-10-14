import { SlashCommandBuilder } from 'discord.js';

export const data = new SlashCommandBuilder()
  .setName('love')
  .setDescription('Montre ton amour à quelqu\'un')
  .addUserOption(option =>
    option
      .setName('cible')
      .setDescription('La personne à aimer')
      .setRequired(false)
  );

export async function execute(interaction) {
  const target = interaction.options.getUser('cible');
  const user = interaction.user;

  let message;
  if (!target || target.id === user.id) {
    message = `${user} s'aime beaucoup... 💖`;
  } else {
    message = `${user} aime ${target}! 💖✨`;
  }

  await interaction.reply({ content: message });
}

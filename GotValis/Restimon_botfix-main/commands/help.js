import { SlashCommandBuilder, EmbedBuilder } from 'discord.js';

export const data = new SlashCommandBuilder()
  .setName('help')
  .setNameLocalizations({ fr: 'aide' })
  .setDescription('Affiche la liste des commandes disponibles');

export async function execute(interaction) {
  const embed = new EmbedBuilder()
    .setColor('#5865F2')
    .setTitle('📚 Manuel crypté — Réseau GotValis')
    .setDescription(
      '**Bienvenue dans GotValis !**\n\n' +
      'Un bot Discord complet avec système de combat, loot boxes, économie, gacha, boutique et bien plus !\n\n' +
      '**Liste des interfaces civiles autorisées:**'
    )
    .addFields(
      {
        name: '📊 Profil & Statistiques',
        value:
          '`/profile`\n' +
          '📊 Affiche ton profil GotValis (PV, PB, tickets, or, perso équipé).\n\n' +
          '`/info [user]`\n' +
          '📈 Affiche tes stats d\'activité (messages, vocal, classement, KDA).\n\n' +
          '`/inventaire` (ou `/inv`)\n' +
          '🎒 Ouvre ton inventaire (objets, quantités, tickets, GoldValis).',
        inline: false,
      },
      {
        name: '💰 Économie & Récompenses',
        value:
          '`/daily`\n' +
          '📅 Récupère ton paquet quotidien (ticket + items + or).\n\n' +
          '`/shop`\n' +
          '🏪 Achète ou vends des objets et personnages.\n' +
          '  • `/shop list` - Voir tous les articles\n' +
          '  • `/shop buy <emoji>` - Acheter un objet\n' +
          '  • `/shop sell <objet>` - Vendre un objet\n' +
          '  • `/shop sell-character` - Vendre un personnage',
        inline: false,
      },
      {
        name: '🎴 Gacha & Personnages',
        value:
          '`/summon` (ou `/invocation`)\n' +
          '🎫 Utilise un ticket pour invoquer un personnage.\n\n' +
          '`/equip`\n' +
          '🎭 Équipe un personnage de ta collection.\n\n' +
          '`/unequip`\n' +
          '❌ Déséquipe ton personnage actuel (cooldown: 1h).',
        inline: false,
      },
      {
        name: '📦 Loot & Items',
        value:
          '`/ouvrir`\n' +
          '📦 Ouvre ton dernier loot box reçu.\n\n' +
          '**Loot automatiques:**\n' +
          '• Loot boxes toutes les 5-15 messages (30s, 5 joueurs max)\n' +
          '• Ravitaillements spéciaux (max 3/jour, 5 min, récompenses variées)',
        inline: false,
      },
      {
        name: '⚔️ Combat & Soins',
        value:
          '`/fight <cible> <objet>`\n' +
          '⚔️ Attaque un joueur avec un objet offensif.\n\n' +
          '`/heal <objet> [cible]`\n' +
          '💊 Soigne un joueur avec un objet de soin.\n\n' +
          '`/use <objet> [cible]`\n' +
          '🛡️ Utilise un objet utilitaire (soin, bouclier).',
        inline: false,
      },
      {
        name: '🏆 Classement',
        value:
          '`/lb_set <10|20>`\n' +
          '🏆 Configure le leaderboard (admin).\n\n' +
          '`/lb_refresh`\n' +
          '🔄 Force une mise à jour du leaderboard (admin).\n\n' +
          '`/lb_stop`\n' +
          '🛑 Supprime le leaderboard (admin).',
        inline: false,
      },
      {
        name: '🎮 Autres Commandes',
        value:
          '`/help`\n' +
          '📚 Ce manuel crypté GotValis.',
        inline: false,
      }
    )
    .setFooter({
      text: 'Modules administratifs non listés.\n💡 Astuce: Envoyez des messages pour déclencher des loot boxes automatiques !'
    })
    .setTimestamp();

  await interaction.reply({ embeds: [embed], ephemeral: true });
}

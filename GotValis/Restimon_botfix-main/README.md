# Bot Discord avec Stats et IA 🤖

Bot Discord avancé avec système de statistiques, économie, bienvenue personnalisé et intégration OpenAI - entièrement en français.

## 🌟 Fonctionnalités

### Commandes Slash

- **`/info [joueur]`** - Affiche les statistiques détaillées d'un joueur
  - Stats de combat (dégâts, soins, K/D/A)
  - Activité Discord (messages, temps vocal)
  - Économie (pièces, solde casino)
  - Inventaire et items
  - Niveau, XP et classement
  - Description générée par IA

- **`/welcome`** - Configuration du système de bienvenue (admin uniquement)
  - `/welcome activer #salon` - Active les messages de bienvenue
  - `/welcome desactiver` - Désactive le système
  - `/welcome message <texte>` - Définit un message personnalisé
  - `/welcome info` - Affiche la configuration actuelle

### Système de Bienvenue

- Messages personnalisés par serveur
- Variables dynamiques: `{user}`, `{server}`, `{username}`
- Messages améliorés par OpenAI
- Embeds élégants avec avatar et statistiques

### Base de Données

Toutes les données sont stockées dans MongoDB:
- Statistiques de joueurs (combat, activité, économie)
- Inventaire et items
- Configuration par serveur
- XP, niveaux et classement

## 🚀 Installation

### Prérequis

- Node.js 18+
- MongoDB (local ou Atlas)
- Compte Discord Developer
- Clé API OpenAI

### Étapes

1. **Cloner et installer les dépendances**
   ```bash
   npm install
   ```

2. **Configurer les variables d'environnement**

   Copiez `.env.example` vers `.env` et remplissez:
   ```bash
   cp .env.example .env
   ```

   Puis éditez `.env`:
   ```env
   DISCORD_TOKEN=votre_token_discord
   CLIENT_ID=votre_client_id
   MONGO_URI=mongodb://localhost:27017/discord-bot
   OPENAI_API_KEY=votre_cle_openai
   ```

3. **Créer votre application Discord**

   - Allez sur https://discord.com/developers/applications
   - Créez une nouvelle application
   - Dans "Bot", créez un bot et copiez le token
   - Dans "OAuth2", copiez le Client ID
   - Invitez le bot avec ces permissions:
     - `applications.commands`
     - `bot` (Send Messages, Embed Links, Read Message History, Add Reactions)

4. **Déployer les commandes slash**
   ```bash
   node deploy-commands.js
   ```

5. **Lancer le bot**
   ```bash
   npm start
   ```

   Pour le développement avec auto-reload:
   ```bash
   npm run dev
   ```

## 📁 Structure du Projet

```
.
├── commands/           # Commandes slash
│   ├── info.js        # Commande /info
│   └── welcome.js     # Commande /welcome
├── database/
│   ├── connection.js  # Connexion MongoDB
│   └── models/
│       ├── Player.js  # Modèle joueur
│       └── Guild.js   # Modèle serveur
├── events/            # Gestionnaires d'événements
│   ├── ready.js
│   ├── interactionCreate.js
│   └── guildMemberAdd.js
├── utils/
│   └── openai.js      # Intégration OpenAI
├── config.js          # Configuration
├── index.js           # Point d'entrée
└── deploy-commands.js # Script de déploiement
```

## 🔧 Utilisation

### Configurer le système de bienvenue

```
/welcome activer #bienvenue
/welcome message Bienvenue {user} sur {server} ! Nous sommes maintenant {memberCount} membres 🎉
```

### Voir les stats d'un joueur

```
/info
/info @utilisateur
```

### Ajouter des stats (exemple pour développeurs)

```javascript
import { Player } from './database/models/Player.js';

// Mettre à jour les stats d'un joueur
await Player.findOneAndUpdate(
  { userId: '123456789' },
  {
    $inc: {
      'stats.damages': 150,
      'stats.kills': 1,
      'activity.messagesSent': 1,
      'economy.coins': 10,
    }
  }
);
```

## 🎨 Personnalisation

### Modifier les descriptions IA

Éditez `utils/openai.js` pour changer les prompts OpenAI.

### Ajouter de nouvelles commandes

1. Créez un fichier dans `commands/`
2. Exportez `data` (SlashCommandBuilder) et `execute(interaction)`
3. Redéployez avec `node deploy-commands.js`

### Ajouter des statistiques

Modifiez `database/models/Player.js` pour ajouter de nouveaux champs.

## 📝 License

MIT

## 🤝 Support

Pour toute question ou problème, créez une issue sur GitHub.
# Restimon_botfix

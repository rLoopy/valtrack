# Bot Discord - Notifications Valorant Duo

Bot Discord qui vous notifie quand votre duo termine une partie de Valorant, avec les détails de victoire/défaite et les changements de RR.

## 🚂 Déploiement sur Railway

**Pour déployer sur Railway (hébergement gratuit 24/7), consultez [DEPLOY.md](DEPLOY.md)**

## 🚀 Installation

### Prérequis

- Python 3.8 ou plus récent
- Un bot Discord (créer sur [Discord Developer Portal](https://discord.com/developers/applications))
- Une clé API Valorant (déjà fournie)

### Étapes d'installation

1. **Cloner ou télécharger ce projet**

2. **Créer et activer un environnement virtuel (recommandé, surtout sur Linux/WSL)**
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # Sur Linux/WSL
   # ou
   venv\Scripts\activate  # Sur Windows
   ```

3. **Installer les dépendances**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configurer le bot Discord**
   - Allez sur [Discord Developer Portal](https://discord.com/developers/applications)
   - Créez une nouvelle application
   - Allez dans l'onglet "Bot" et créez un bot
   - Copiez le token du bot
   - Activez les "Privileged Gateway Intents" suivants:
     - ✅ PRESENCE INTENT
     - ✅ SERVER MEMBERS INTENT
     - ✅ MESSAGE CONTENT INTENT
   - Invitez le bot sur votre serveur avec les permissions nécessaires (Envoyer des messages, Lire l'historique des messages)

4. **Configurer les variables d'environnement**
   - Copiez le fichier `.env.example` vers `.env`
   - Remplissez les valeurs:
     ```
     DISCORD_TOKEN=votre_token_discord
     VALORANT_API_KEY=HDEV-c797c6bf-6699-49b0-9bc8-a369c13e5cac
     DUO_NAME=NomDuJoueur
     DUO_TAG=TagDuJoueur
     DISCORD_CHANNEL_ID=id_du_canal
     POLL_INTERVAL=60
     ```

5. **Obtenir l'ID du canal Discord**
   - Activez le mode développeur dans Discord (Paramètres > Avancé > Mode développeur)
   - Clic droit sur le canal où vous voulez les notifications > Copier l'ID
   - Collez cet ID dans `DISCORD_CHANNEL_ID`

6. **Trouver le nom et tag du duo**
   - Le format est généralement: `Nom#Tag`
   - Exemple: `Loopy#EUW`
   - Entrez `Loopy` dans `DUO_NAME` et `EUW` dans `DUO_TAG`

## 🎮 Utilisation

### Lancer le bot

**Avec l'environnement virtuel activé:**
```bash
python bot.py
```

**Ou utilisez le script (Linux/WSL):**
```bash
./run.sh
```

**Note:** Si vous utilisez un environnement virtuel, assurez-vous de l'activer avant de lancer le bot:
```bash
source venv/bin/activate  # Linux/WSL
python bot.py
```

Le bot va:
- Se connecter à Discord
- Récupérer les informations du duo
- Vérifier périodiquement les nouveaux matchs (selon `POLL_INTERVAL`)
- Envoyer des notifications quand un nouveau match est détecté

### Commandes Discord

- `!test` - Teste si le bot fonctionne
- `!status` - Affiche le statut actuel du bot
- `!forcecheck` - Force une vérification immédiate des matchs

## 📊 Informations affichées

Quand un match est détecté, le bot envoie une notification avec:
- ✅/❌ Victoire ou Défaite
- 📊 Score du match (ex: 13-7)
- 📈/📉 Changement de RR (+25 RR ou -18 RR)
- 🏆 Rang actuel du joueur
- 🗺️ Map jouée
- 🎮 Mode de jeu

## ⚠️ Limitations de l'API

- **Basic Key**: 30 requêtes par minute
- **Advanced Key**: 90 requêtes par minute (c'est votre cas)

Assurez-vous que `POLL_INTERVAL` respecte ces limites. Avec 90 req/min, vous pouvez vérifier toutes les 60 secondes sans problème.

## 🔧 Configuration avancée

### Intervalle de vérification

Modifiez `POLL_INTERVAL` dans `.env`:
- `30` = vérification toutes les 30 secondes
- `60` = vérification toutes les minutes (recommandé)
- `120` = vérification toutes les 2 minutes

### Région

Par défaut, le bot utilise la région `eu`. Pour changer, modifiez le paramètre `region` dans les fonctions `get_match_history()` et `get_mmr_history()` dans `bot.py`.

## 📝 Notes importantes

- ⚠️ **Consentement**: Assurez-vous d'avoir le consentement du joueur avant de suivre ses matchs
- 🔒 **Sécurité**: Ne partagez jamais votre fichier `.env` ou votre token Discord
- 🐛 **Bugs**: Si le bot ne détecte pas de matchs, vérifiez les logs dans la console

## 🛠️ Dépannage

### Le bot ne démarre pas
- Vérifiez que tous les champs du `.env` sont remplis
- Vérifiez que le token Discord est correct
- Assurez-vous que Python 3.8+ est installé

### Aucune notification n'est envoyée
- Vérifiez que le bot a les permissions d'envoyer des messages dans le canal
- Vérifiez que `DUO_NAME` et `DUO_TAG` sont corrects
- Vérifiez que le `DISCORD_CHANNEL_ID` est correct
- Utilisez `!status` pour voir l'état du bot

### Erreur "Rate Limited"
- Vous dépassez les limites de l'API
- Augmentez `POLL_INTERVAL` (ex: 120 secondes)

## 📚 Ressources

- [API Documentation](https://docs.henrikdev.xyz/)
- [Discord.py Documentation](https://discordpy.readthedocs.io/)
- [Discord Developer Portal](https://discord.com/developers/applications)

## ⚖️ Licence

Ce projet est fourni à titre éducatif. Respectez les conditions d'utilisation de l'API Valorant non officielle.


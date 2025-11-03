# 🚂 Déploiement sur Railway

Guide complet pour déployer le bot Discord sur Railway.

## 📋 Prérequis

- Un compte GitHub
- Un compte Railway (gratuit) : https://railway.app
- Votre bot Discord déjà créé avec le token

## 🚀 Étapes de déploiement

### 1. Préparer le repository Git

```bash
# Initialiser git (si pas déjà fait)
git init

# Ajouter tous les fichiers
git add .

# Faire un commit
git commit -m "Initial commit - Valorant Discord Bot"

# Créer un repo sur GitHub et le lier
git remote add origin https://github.com/VOTRE_USERNAME/valtrack.git
git branch -M main
git push -u origin main
```

### 2. Déployer sur Railway

1. Allez sur https://railway.app
2. Cliquez sur **"New Project"**
3. Sélectionnez **"Deploy from GitHub repo"**
4. Autorisez Railway à accéder à vos repos GitHub
5. Sélectionnez le repo `valtrack`
6. Railway détectera automatiquement que c'est une app Python

### 3. Configurer les variables d'environnement

Dans Railway, allez dans l'onglet **"Variables"** et ajoutez :

```
DISCORD_TOKEN=votre_token_discord
VALORANT_API_KEY=HDEV-c797c6bf-6699-49b0-9bc8-a369c13e5cac
DUO_NAME=Lowack
DUO_TAG=lowh
DISCORD_CHANNEL_ID=votre_id_de_canal
POLL_INTERVAL=90
```

**Important :** Ne mettez PAS de guillemets autour des valeurs !

### 4. Déploiement

Railway va automatiquement :
- ✅ Installer Python 3.12
- ✅ Installer les dépendances (`requirements.txt`)
- ✅ Lancer le bot avec `python bot.py`

Le bot démarrera automatiquement après le déploiement.

## 📊 Surveillance

### Logs
- Cliquez sur l'onglet **"Deployments"** puis **"View Logs"**
- Vous verrez les messages du bot en temps réel

### Redémarrage
- Le bot redémarre automatiquement en cas d'erreur
- Pour forcer un redémarrage : cliquez sur les 3 points → **"Restart"**

## 💰 Coûts

Railway offre un plan gratuit avec :
- 500 heures d'exécution par mois
- 512 MB de RAM
- Largement suffisant pour un bot Discord

**Important :** Le bot consomme environ ~15h par jour = ~450h/mois, donc ça rentre dans le plan gratuit !

## 🔄 Mises à jour

Pour mettre à jour le bot après des modifications :

```bash
# Modifier le code localement
# Puis push sur GitHub
git add .
git commit -m "Update bot"
git push

# Railway détectera automatiquement le push et redéploiera
```

## ⚠️ Troubleshooting

### Le bot ne démarre pas
1. Vérifiez les logs dans Railway
2. Vérifiez que toutes les variables d'environnement sont définies
3. Vérifiez que `DISCORD_TOKEN` est correct

### Le bot se déconnecte
1. Vérifiez les logs pour voir l'erreur
2. Railway a peut-être atteint la limite de RAM → augmentez le plan

### Le bot ne répond pas aux commandes
1. Vérifiez que `MESSAGE CONTENT INTENT` est activé sur Discord
2. Vérifiez les logs pour voir si le bot reçoit les messages

## 📝 Fichiers importants pour Railway

- `Procfile` : Commande pour démarrer le bot
- `runtime.txt` : Version de Python
- `requirements.txt` : Dépendances Python
- `railway.json` : Configuration Railway
- `.gitignore` : Fichiers à ne pas versionner

## 🔒 Sécurité

- ✅ Le fichier `.env` est dans `.gitignore` (ne sera pas pushé)
- ✅ Les variables sensibles sont sur Railway (pas dans le code)
- ✅ Le token Discord n'est jamais exposé publiquement

## 🎉 C'est tout !

Votre bot devrait maintenant tourner 24/7 sur Railway et notifier automatiquement quand votre duo termine un match !


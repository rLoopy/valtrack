# 🚀 Guide Rapide - Déploiement Railway

## Commandes à exécuter (dans WSL/Linux)

### 1. Initialiser Git et pousser sur GitHub

```bash
# Aller dans le dossier du projet
cd /mnt/c/Users/Loopy/valtrack

# Initialiser git (si pas déjà fait)
git init

# Ajouter tous les fichiers
git add .

# Faire un commit
git commit -m "Bot Discord Valorant - Ready for Railway"

# Créer un repo sur GitHub et le lier (remplacez VOTRE_USERNAME)
git remote add origin https://github.com/LoopyR/valtrack.git

# Pousser sur GitHub
git branch -M main
git push -u origin main
```

### 2. Déployer sur Railway

1. **Créer un compte** : https://railway.app (connexion avec GitHub)

2. **Nouveau projet** :
   - Cliquez sur "New Project"
   - Sélectionnez "Deploy from GitHub repo"
   - Choisissez `valtrack`

3. **Variables d'environnement** (onglet Variables) :
   ```
   DISCORD_TOKEN=<votre_token>
   VALORANT_API_KEY=HDEV-c797c6bf-6699-49b0-9bc8-a369c13e5cac
   DUO_NAME=lowack
   DUO_TAG=lowh
   DISCORD_CHANNEL_ID=<votre_id_canal>
   POLL_INTERVAL=90
   ```

4. **Déploiement** : Railway déploie automatiquement !

### 3. Vérifier que ça marche

- Onglet "Deployments" → "View Logs"
- Vous devriez voir :
  ```
  val track#XXXX est connecté!
  Récupération des informations pour lowack#lowh...
  PUUID du duo: ...
  Bot prêt!
  ```

## ✅ C'est tout !

Votre bot tourne maintenant 24/7 gratuitement sur Railway !

## 🔄 Pour mettre à jour après modifications

```bash
git add .
git commit -m "Update"
git push
```

Railway redéploie automatiquement.


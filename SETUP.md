# Guide de démarrage rapide

## 🚀 Démarrage en 5 minutes

### 1. Installer Python et les dépendances

```bash
pip install -r requirements.txt
```

### 2. Créer votre bot Discord

1. Allez sur https://discord.com/developers/applications
2. Cliquez sur "New Application"
3. Donnez-lui un nom (ex: "Valorant Notifier")
4. Allez dans l'onglet **Bot** (à gauche)
5. Cliquez sur **Add Bot** et confirmez
6. **Copiez le token** (cliquez sur "Reset Token" si besoin)
7. Activez ces **Privileged Gateway Intents**:
   - ✅ PRESENCE INTENT
   - ✅ SERVER MEMBERS INTENT
   - ✅ MESSAGE CONTENT INTENT
8. Allez dans l'onglet **OAuth2 > URL Generator**
   - Cochez **bot** dans "SCOPES"
   - Cochez les permissions: **Send Messages**, **Read Message History**
   - **Copiez l'URL** générée en bas
   - Ouvrez cette URL dans votre navigateur pour inviter le bot sur votre serveur

### 3. Obtenir l'ID du canal Discord

1. Dans Discord, allez dans **Paramètres utilisateur > Avancé**
2. Activez le **Mode développeur**
3. Clic droit sur le canal où vous voulez les notifications
4. Cliquez sur **Copier l'ID**
5. Collez cet ID (c'est un long nombre, ex: 123456789012345678)

### 4. Configurer le fichier .env

Créez un fichier `.env` à la racine du projet avec ce contenu:

```env
DISCORD_TOKEN=votre_token_discord_ici
VALORANT_API_KEY=HDEV-c797c6bf-6699-49b0-9bc8-a369c13e5cac
DUO_NAME=Loopy
DUO_TAG=EUW
DISCORD_CHANNEL_ID=votre_id_de_canal_ici
POLL_INTERVAL=60
```

**Remplacez:**
- `votre_token_discord_ici` par le token du bot copié à l'étape 2
- `Loopy` et `EUW` par le nom et tag Riot de votre duo (format: Nom#Tag)
- `votre_id_de_canal_ici` par l'ID du canal copié à l'étape 3

### 5. Lancer le bot

```bash
python bot.py
```

Si tout fonctionne, vous devriez voir:
```
NomDuBot#1234 est connecté!
Récupération des informations pour Loopy#EUW...
PUUID du duo: abc123...
Bot prêt! Vérification des matchs toutes les 60 secondes.
```

### 6. Tester le bot

Dans Discord, tapez dans le canal:
```
!test
!status
```

Le bot devrait répondre.

## ✅ Vérification

Une fois configuré:
- Le bot vérifie automatiquement les nouveaux matchs toutes les 60 secondes
- Quand votre duo termine un match, vous recevez une notification automatique
- Les notifications incluent: Victoire/Défaite, Score, Changement de RR, Map, Rang actuel

## 🆘 Problèmes courants

**"Bot non configuré correctement"**
→ Vérifiez que tous les champs du `.env` sont remplis

**"Impossible de trouver le canal"**
→ Vérifiez que l'ID du canal est correct et que le bot a les permissions

**"Impossible de récupérer le PUUID"**
→ Vérifiez que `DUO_NAME` et `DUO_TAG` sont corrects (format: Nom#Tag)

**Aucune notification**
→ Attendez qu'un nouveau match soit joué, ou utilisez `!forcecheck` pour forcer une vérification


# 🔧 Guide de dépannage

## Erreur: PrivilegedIntentsRequired

### Problème
```
discord.errors.PrivilegedIntentsRequired: Shard ID None is requesting privileged intents that have not been explicitly enabled in the developer portal.
```

### Solution 1: Activer les Privileged Intents (Recommandé)

1. Allez sur https://discord.com/developers/applications
2. Sélectionnez votre application/bot
3. Allez dans l'onglet **Bot** (à gauche)
4. Faites défiler jusqu'à **Privileged Gateway Intents**
5. Activez les intents suivants:
   - ✅ **PRESENCE INTENT** (optionnel, seulement si vous voulez voir le statut)
   - ✅ **SERVER MEMBERS INTENT** (optionnel, seulement si vous voulez voir les membres)
   - ✅ **MESSAGE CONTENT INTENT** (requis pour les commandes `!test`, `!status`, etc.)

6. **Enregistrez les modifications**
7. Relancez le bot

### Solution 2: Désactiver message_content (Si vous ne voulez pas activer les intents)

Si vous ne voulez pas activer les Privileged Intents dans le portail, vous pouvez modifier le bot pour désactiver `message_content`. **Note:** Les commandes Discord (`!test`, `!status`, etc.) ne fonctionneront plus, mais les notifications automatiques continueront.

1. Ouvrez `bot.py`
2. Trouvez cette ligne:
   ```python
   intents.message_content = True
   ```
3. Remplacez par:
   ```python
   intents.message_content = False
   ```
4. (Optionnel) Supprimez ou commentez les commandes `@bot.command()` si vous voulez

5. Relancez le bot

**Note:** Les notifications automatiques fonctionneront toujours sans `message_content` car elles utilisent `channel.send()` et non la lecture de messages.

## Autres problèmes courants

### Le bot ne démarre pas
- ✅ Vérifiez que le fichier `.env` existe et contient tous les champs requis
- ✅ Vérifiez que `DISCORD_TOKEN` est correct
- ✅ Vérifiez que vous avez activé l'environnement virtuel: `source venv/bin/activate`

### "Impossible de récupérer le PUUID"
- ✅ Vérifiez que `DUO_NAME` et `DUO_TAG` sont corrects (sans le `#`)
- ✅ Vérifiez que le joueur existe et a joué au moins un match
- ✅ Vérifiez que la région est correcte (eu, na, ap, etc.)

### "Impossible de trouver le canal"
- ✅ Vérifiez que `DISCORD_CHANNEL_ID` est correct (c'est un long nombre)
- ✅ Vérifiez que le bot est bien invité sur le serveur
- ✅ Vérifiez que le bot a les permissions "Envoyer des messages" dans ce canal

### Aucune notification n'est envoyée
- ✅ Attendez qu'un nouveau match soit joué (le bot vérifie toutes les 60 secondes)
- ✅ Utilisez `!forcecheck` (si les commandes sont activées) pour forcer une vérification
- ✅ Vérifiez les logs dans la console pour voir s'il y a des erreurs

### Erreur "Rate Limited"
- ✅ Vous dépassez les limites de l'API (90 req/min pour Advanced)
- ✅ Augmentez `POLL_INTERVAL` dans `.env` (ex: 120 pour vérifier toutes les 2 minutes)

### Le bot se déconnecte
- ✅ Vérifiez votre connexion internet
- ✅ Le bot devrait se reconnecter automatiquement
- ✅ Si le problème persiste, vérifiez les logs


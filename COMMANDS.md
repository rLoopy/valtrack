# 🎮 Commandes Discord

Liste des commandes disponibles pour gérer le bot de tracking Valorant.

## 👥 Gestion des joueurs

### `!addplayer <nom> <tag>`
Ajoute un joueur à la liste de tracking.

**Exemple :**
```
!addplayer Lowack lowh
!addplayer TenZ SEN
```

**Réponse :**
```
✅ Joueur ajouté !
Lowack#lowh est maintenant tracké
Région: EU | Niveau: 371 | Total trackés: 2
```

---

### `!removeplayer <nom> <tag>`
Retire un joueur de la liste de tracking.

**Exemple :**
```
!removeplayer Lowack lowh
```

**Réponse :**
```
✅ Lowack#lowh retiré du tracking
```

---

### `!listplayers`
Affiche la liste de tous les joueurs trackés.

**Exemple :**
```
!listplayers
```

**Réponse :**
```
📋 Joueurs trackés
2 joueur(s) surveillé(s)

Lowack#lowh
Dernier match: fe23fd3b...

TenZ#SEN
Dernier match: a1b2c3d4...
```

---

## 🔧 Commandes utilitaires

### `!status`
Affiche le statut actuel du bot.

**Exemple :**
```
!status
```

**Réponse :**
```
Status du bot
Bot: 🟢 Actif
Joueurs trackés: 2
Intervalle: 90s

Liste des joueurs:
• Lowack#lowh
• TenZ#SEN
```

---

### `!test`
Teste si le bot est actif.

**Exemple :**
```
!test
```

**Réponse :**
```
Bot actif! ✅
```

---

### `!forcecheck`
Force une vérification immédiate des matchs pour tous les joueurs.

**Exemple :**
```
!forcecheck
```

---

### `!testapi [nom] [tag]`
Teste l'API pour un joueur spécifique.

**Exemple :**
```
!testapi Lowack lowh
!testapi
```

**Réponse :**
```
✅ Compte trouvé - PUUID: 6c588cc5...
✅ MMR History: 3 matchs trouvés

Derniers matchs:
1. Immortal 1 | -21 RR | Pearl
   Match ID: fe23fd3b...
2. Immortal 1 | +23 RR | Bind
   Match ID: a1b2c3d4...
```

---

## 💡 Notes importantes

1. **Nom et Tag** : Le format est toujours `nom tag` (sans le `#`)
   - ✅ Bon : `!addplayer Lowack lowh`
   - ❌ Mauvais : `!addplayer Lowack#lowh`

2. **Casse** : Peu importe les majuscules/minuscules
   - `!addplayer lowack LOWH` fonctionne aussi

3. **Limite** : Vous pouvez tracker autant de joueurs que vous voulez, mais attention au rate limit de l'API (30 req/min)
   - Avec `POLL_INTERVAL=90`, vous pouvez tracker ~10 joueurs sans problème

4. **Permissions** : Toutes les commandes peuvent être utilisées par n'importe qui dans le channel
   - Si vous voulez restreindre, modifiez le code pour vérifier les permissions

5. **Persistance** : Les joueurs trackés sont sauvegardés dans `tracked_players.json`
   - Ils restent même si le bot redémarre
   - Sur Railway, ce fichier persiste entre les déploiements


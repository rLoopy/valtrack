import discord
from discord.ext import tasks, commands
import requests
import asyncio
import os
import json
from dotenv import load_dotenv
from datetime import datetime, timezone

# Charger les variables d'environnement
load_dotenv()

# Configuration
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
API_KEY = os.getenv('VALORANT_API_KEY', 'HDEV-c797c6bf-6699-49b0-9bc8-a369c13e5cac')
DUO_NAME = os.getenv('DUO_NAME')  # Nom du joueur (ex: "Loopy")
DUO_TAG = os.getenv('DUO_TAG')    # Tag du joueur (ex: "EUW")
CHANNEL_ID = int(os.getenv('DISCORD_CHANNEL_ID', '0'))
# Intervalle par défaut: 90 secondes pour respecter le rate limit (90 req/min pour Advanced key)
# Cela fait environ 40 requêtes/heure, ce qui est sûr
POLL_INTERVAL = int(os.getenv('POLL_INTERVAL', '90'))  # Secondes entre les vérifications

# Configuration Discord
intents = discord.Intents.default()
intents.message_content = True  # Nécessaire pour lire le contenu des messages (commandes)
# Note: Si vous ne voulez pas activer les Privileged Intents, vous pouvez désactiver
# les commandes et utiliser seulement les notifications automatiques
bot = commands.Bot(command_prefix='!', intents=intents)

# Base URL de l'API
API_BASE_URL = 'https://api.henrikdev.xyz/valorant/v1'

# Stockage du dernier match vérifié
last_match_id = None
duo_puuid = None
LAST_MATCH_FILE = 'last_match.json'

def load_last_match_id():
    """Charge le dernier match ID depuis le fichier"""
    try:
        if os.path.exists(LAST_MATCH_FILE):
            with open(LAST_MATCH_FILE, 'r') as f:
                data = json.load(f)
                return data.get('last_match_id')
    except Exception as e:
        print(f"Erreur lors du chargement du dernier match: {e}")
    return None

def save_last_match_id(match_id):
    """Sauvegarde le dernier match ID dans un fichier"""
    try:
        with open(LAST_MATCH_FILE, 'w') as f:
            json.dump({'last_match_id': match_id}, f)
    except Exception as e:
        print(f"Erreur lors de la sauvegarde du dernier match: {e}")

async def check_if_match_already_posted(channel, match_id):
    """Vérifie si le match a déjà été posté dans le channel"""
    try:
        # Récupérer les 50 derniers messages du channel
        async for message in channel.history(limit=50):
            # Vérifier si le message contient le match_id
            if message.author == bot.user and message.embeds:
                for embed in message.embeds:
                    if embed.footer and embed.footer.text:
                        if match_id in embed.footer.text:
                            return True
        return False
    except Exception as e:
        print(f"Erreur lors de la vérification des messages: {e}")
        return False

def get_account_info(name, tag):
    """Récupère les informations du compte (incluant PUUID)"""
    url = f'{API_BASE_URL}/account/{name}/{tag}'
    headers = {'Authorization': API_KEY}

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()

        if data.get('status') == 200:
            return data.get('data')
        else:
            print(f"Erreur API: {data.get('message', 'Erreur inconnue')}")
            return None
    except requests.exceptions.RequestException as e:
        print(f"Erreur lors de la récupération du compte: {e}")
        return None

# Les endpoints lifetime-matches et matchlist ne fonctionnent pas dans l'API v1
# On utilise uniquement mmr-history pour obtenir les match_id

def get_match_details(match_id):
    """Récupère les détails d'un match spécifique (utilise l'API v2)"""
    # L'API v1 ne fonctionne pas pour les détails de match, on utilise v2
    url = f'https://api.henrikdev.xyz/valorant/v2/match/{match_id}'
    headers = {'Authorization': API_KEY}

    try:
        response = requests.get(url, headers=headers, timeout=10)

        # Gérer le rate limiting
        if response.status_code == 429:
            print("⚠️ Rate limit atteint sur match details")
            return None

        response.raise_for_status()
        data = response.json()

        if data.get('status') == 200:
            return data.get('data')
        else:
            print(f"Erreur API match: {data.get('message', 'Erreur inconnue')}")
            return None
    except requests.exceptions.RequestException as e:
        if '429' in str(e):
            print("⚠️ Rate limit atteint")
            return None
        print(f"Erreur lors de la récupération du match: {e}")
        return None

def get_player_stats_from_match(match_data, puuid):
    """Extrait les statistiques d'un joueur spécifique depuis les données du match"""
    if not match_data:
        return None

    players = match_data.get('players', {}).get('all_players', [])
    for player in players:
        if player.get('puuid') == puuid:
            return player

    return None

def get_mmr_history(name, tag, region='eu', size=10):
    """Récupère l'historique MMR pour obtenir les changements de RR et les match IDs (Europe uniquement)"""
    # L'API v1 utilise le format /mmr-history/{region}/{name}/{tag}
    url = f'{API_BASE_URL}/mmr-history/{region}/{name}/{tag}'
    headers = {'Authorization': API_KEY}

    try:
        response = requests.get(url, headers=headers, timeout=10)

        # Gérer le rate limiting
        if response.status_code == 429:
            print("⚠️ Rate limit atteint sur mmr-history")
            return None

        response.raise_for_status()
        data = response.json()

        if data.get('status') == 200:
            mmr_data = data.get('data', [])
            # Limiter au nombre demandé
            return mmr_data[:size] if mmr_data else []
        else:
            print(f"Erreur API MMR history: {data.get('message', 'Erreur inconnue')}")
            return []
    except requests.exceptions.RequestException as e:
        if '429' in str(e):
            print("⚠️ Rate limit atteint")
            return None
        print(f"Erreur lors de la récupération de l'historique MMR: {e}")
        return []

@bot.event
async def on_ready():
    """Événement déclenché quand le bot est prêt"""
    print(f'{bot.user} est connecté!', flush=True)

    # Charger le dernier match ID depuis le fichier
    global duo_puuid, last_match_id
    loaded_match_id = load_last_match_id()
    if loaded_match_id:
        last_match_id = loaded_match_id
        print(f"Dernier match chargé: {last_match_id}", flush=True)

    # Initialiser le PUUID du duo
    if DUO_NAME and DUO_TAG:
        print(f"Récupération des informations pour {DUO_NAME}#{DUO_TAG}...", flush=True)
        account_info = get_account_info(DUO_NAME, DUO_TAG)
        if account_info:
            duo_puuid = account_info.get('puuid')
            print(f"PUUID du duo: {duo_puuid}", flush=True)
        else:
            print("⚠️ Impossible de récupérer le PUUID. Vérifiez le nom et le tag.", flush=True)
    else:
        print("⚠️ DUO_NAME et DUO_TAG ne sont pas configurés dans le .env", flush=True)

    # Démarrer la vérification des matchs
    if duo_puuid and CHANNEL_ID:
        check_matches.start()
        print(f"Bot prêt! Vérification des matchs toutes les {POLL_INTERVAL} secondes.", flush=True)
    else:
        print("⚠️ Bot non configuré correctement. Vérifiez vos variables d'environnement.", flush=True)

@tasks.loop(seconds=POLL_INTERVAL)
async def check_matches():
    """Vérifie périodiquement les nouveaux matchs"""
    global last_match_id, duo_puuid

    if not duo_puuid or not CHANNEL_ID:
        return

    channel = bot.get_channel(CHANNEL_ID)
    if not channel:
        print(f"⚠️ Impossible de trouver le canal avec l'ID {CHANNEL_ID}")
        return

    try:
        # Récupérer l'historique des matchs via MMR history (seul endpoint qui fonctionne)
        match_history = []
        latest_match_id = None
        rr_change = 0
        current_rank = None

        if DUO_NAME and DUO_TAG:
            mmr_history = get_mmr_history(DUO_NAME, DUO_TAG, region='eu', size=1)

            if mmr_history is None:
                # Rate limit, attendre avant de continuer
                print("⏳ Rate limit détecté, passage au prochain cycle...")
                return
            elif mmr_history and len(mmr_history) > 0:
                latest_mmr = mmr_history[0]
                latest_match_id = latest_mmr.get('match_id')
                rr_change = latest_mmr.get('mmr_change_to_last_game', 0)
                current_rank = latest_mmr.get('currenttierpatched', 'Unknown')
                current_rr = latest_mmr.get('ranking_in_tier', 0)  # RR actuel dans le tier
                elo = latest_mmr.get('elo', 0)  # MMR/ELO total

                print(f"✅ Match trouvé via MMR history: {latest_match_id}")
            else:
                print("Aucun match trouvé dans l'historique MMR")
                return

        if not latest_match_id:
            print("Aucun match_id trouvé")
            return

        # Si c'est un nouveau match
        if latest_match_id != last_match_id:
            print(f"Nouveau match détecté: {latest_match_id}")

            # Vérifier si le match n'a pas déjà été posté dans le channel
            already_posted = await check_if_match_already_posted(channel, latest_match_id)
            if already_posted:
                print(f"Match {latest_match_id} déjà posté dans le channel, ignoré")
                last_match_id = latest_match_id  # Marquer comme vu pour ne plus le vérifier
                save_last_match_id(latest_match_id)  # Sauvegarder aussi
                return

            # Récupérer les détails du match
            match_data = get_match_details(latest_match_id)

            if match_data is None:
                # Rate limit, attendre avant de continuer
                print("⏳ Rate limit détecté sur match details, passage au prochain cycle...")
                return

            if match_data:
                # Obtenir les stats du joueur
                player_stats = get_player_stats_from_match(match_data, duo_puuid)

                if player_stats:
                    # Extraire les stats du joueur
                    stats = player_stats.get('stats', {})
                    kills = stats.get('kills', 0)
                    deaths = stats.get('deaths', 0)
                    assists = stats.get('assists', 0)
                    score = stats.get('score', 0)
                    headshots = stats.get('headshots', 0)
                    bodyshots = stats.get('bodyshots', 0)
                    legshots = stats.get('legshots', 0)

                    # Calculer l'ACS (Average Combat Score)
                    rounds_played = match_data.get('metadata', {}).get('rounds_played', 1)
                    acs = score // max(1, rounds_played)

                    # K/D ratio
                    kd_ratio = round(kills / max(1, deaths), 2)

                    # Headshot %
                    total_shots = headshots + bodyshots + legshots
                    hs_percent = round((headshots / max(1, total_shots)) * 100) if total_shots > 0 else 0

                    # Agent joué
                    agent = player_stats.get('character', 'Unknown')

                    # Déterminer si c'est une victoire ou défaite
                    team = player_stats.get('team', '').upper()
                    teams = match_data.get('teams', {})
                    red_rounds_won = teams.get('red', {}).get('rounds_won', 0)
                    blue_rounds_won = teams.get('blue', {}).get('rounds_won', 0)

                    won = False
                    if team == 'RED':
                        won = red_rounds_won > blue_rounds_won
                    elif team == 'BLUE':
                        won = blue_rounds_won > red_rounds_won

                    # Les infos RR et rang sont déjà dans les variables rr_change et current_rank
                    # (récupérées plus tôt depuis mmr_history)

                    # Créer l'embed Discord
                    result_emoji = '✅' if won else '❌'
                    result_text = "VICTOIRE" if won else "DÉFAITE"
                    result_color = discord.Color.green() if won else discord.Color.red()

                    embed = discord.Embed(
                        title=f"{result_emoji} Nouveau match terminé!",
                        description=f"**{DUO_NAME}#{DUO_TAG}** a **{result_text.lower()}**",
                        color=result_color,
                        timestamp=datetime.now(timezone.utc)
                    )

                    # Agent et score du match
                    embed.add_field(
                        name="🎭 Agent",
                        value=agent,
                        inline=True
                    )

                    embed.add_field(
                        name="📊 Score",
                        value=f"{blue_rounds_won} - {red_rounds_won}",
                        inline=True
                    )

                    if rr_change != 0:
                        rr_emoji = "📈" if rr_change > 0 else "📉"
                        embed.add_field(
                            name=f"{rr_emoji} RR",
                            value=f"{'+' if rr_change > 0 else ''}{rr_change} RR",
                            inline=True
                        )

                    # Stats de performance
                    embed.add_field(
                        name="⚔️ K/D/A",
                        value=f"{kills}/{deaths}/{assists}",
                        inline=True
                    )

                    embed.add_field(
                        name="📈 ACS",
                        value=f"{acs}",
                        inline=True
                    )

                    embed.add_field(
                        name="🎯 K/D",
                        value=f"{kd_ratio}",
                        inline=True
                    )

                    if current_rank:
                        # Afficher le rang avec le nombre de RR actuel
                        rank_display = f"{current_rank}"
                        if current_rr > 0:
                            rank_display += f" ({current_rr} RR)"

                        embed.add_field(
                            name="🏆 Rang actuel",
                            value=rank_display,
                            inline=True
                        )

                    # Ajouter l'ELO si disponible
                    if elo > 0:
                        embed.add_field(
                            name="📊 ELO",
                            value=f"{elo}",
                            inline=True
                        )

                    # Ajouter des infos supplémentaires
                    map_name = match_data.get('metadata', {}).get('map', 'Unknown')
                    game_mode = match_data.get('metadata', {}).get('mode', 'Unknown')

                    embed.add_field(
                        name="🗺️ Map",
                        value=map_name,
                        inline=False
                    )

                    embed.add_field(
                        name="🎮 Mode",
                        value=game_mode,
                        inline=True
                    )

                    # Footer avec le match ID pour permettre la détection de doublons
                    embed.set_footer(text=f"Match ID: {latest_match_id}")

                    await channel.send(embed=embed)
                    print(f"Notification envoyée pour le match {latest_match_id}")
                else:
                    print(f"Joueur non trouvé dans le match {latest_match_id}")

            # Mettre à jour et sauvegarder le dernier match ID
            last_match_id = latest_match_id
            save_last_match_id(latest_match_id)

    except Exception as e:
        print(f"Erreur lors de la vérification des matchs: {e}")
        import traceback
        traceback.print_exc()

@check_matches.before_loop
async def before_check_matches():
    """Attend que le bot soit prêt avant de commencer les vérifications"""
    await bot.wait_until_ready()

@bot.command(name='test')
async def test_command(ctx):
    """Commande de test pour vérifier que le bot fonctionne"""
    await ctx.send("Bot actif! ✅")

@bot.command(name='status')
async def status_command(ctx):
    """Affiche le statut du bot"""
    global duo_puuid, last_match_id

    embed = discord.Embed(
        title="Status du bot",
        color=discord.Color.blue()
    )

    embed.add_field(name="Bot", value="🟢 Actif", inline=True)
    embed.add_field(name="Duo", value=f"{DUO_NAME}#{DUO_TAG}" if DUO_NAME and DUO_TAG else "Non configuré", inline=True)
    embed.add_field(name="PUUID", value=duo_puuid[:8] + "..." if duo_puuid else "Non trouvé", inline=True)
    embed.add_field(name="Dernier match", value=last_match_id if last_match_id else "Aucun", inline=False)
    embed.add_field(name="Intervalle", value=f"{POLL_INTERVAL} secondes", inline=True)

    await ctx.send(embed=embed)

@bot.command(name='forcecheck')
async def force_check_command(ctx):
    """Force une vérification immédiate des matchs"""
    global check_matches
    await ctx.send("Vérification en cours...")
    await check_matches()
    await ctx.send("Vérification terminée!")

@bot.command(name='testapi')
async def test_api_command(ctx):
    """Teste directement l'API pour voir ce qu'elle retourne"""
    if not DUO_NAME or not DUO_TAG:
        await ctx.send("❌ DUO_NAME et DUO_TAG doivent être configurés")
        return

    await ctx.send(f"🔍 Test de l'API pour {DUO_NAME}#{DUO_TAG}...")

    # Tester l'endpoint account
    account_info = get_account_info(DUO_NAME, DUO_TAG)
    if account_info:
        puuid = account_info.get('puuid')
        await ctx.send(f"✅ Compte trouvé - PUUID: `{puuid[:8]}...`")

        # Tester l'endpoint MMR history (le seul qui fonctionne)
        mmr_history = get_mmr_history(DUO_NAME, DUO_TAG, region='eu', size=3)

        if mmr_history is None:
            await ctx.send("⚠️ Rate limit atteint")
        elif mmr_history:
            result = f"✅ MMR History: {len(mmr_history)} matchs trouvés\n\n"
            result += "Derniers matchs:\n"
            for i, mmr in enumerate(mmr_history[:3], 1):
                match_id = mmr.get('match_id', 'N/A')
                rank = mmr.get('currenttierpatched', 'N/A')
                rr = mmr.get('mmr_change_to_last_game', 0)
                map_name = mmr.get('map', {}).get('name', 'N/A')
                result += f"{i}. {rank} | {'+' if rr > 0 else ''}{rr} RR | {map_name}\n"
                result += f"   Match ID: {match_id[:8]}...\n"

            await ctx.send(f"```\n{result}\n```")
        else:
            await ctx.send("❌ Aucun match trouvé dans l'historique MMR")
    else:
        await ctx.send("❌ Impossible de récupérer les informations du compte")

# Lancer le bot
if __name__ == '__main__':
    if not DISCORD_TOKEN:
        print("⚠️ ERREUR: DISCORD_TOKEN n'est pas défini dans le .env")
        print("Créez un fichier .env avec vos tokens. Voir .env.example")
    else:
        bot.run(DISCORD_TOKEN)


import discord
from discord import app_commands
from discord.ext import tasks, commands
import requests
import asyncio
import os
import json
from dotenv import load_dotenv
from datetime import datetime, timezone
import io
import lol_tracker  # Module pour League of Legends
try:
    import matplotlib
    matplotlib.use('Agg')  # Backend sans interface graphique
    import matplotlib.pyplot as plt
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    print("⚠️ matplotlib non disponible. Les graphiques de rang ne seront pas disponibles.")

# Import PostgreSQL
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    POSTGRES_AVAILABLE = True
except ImportError:
    POSTGRES_AVAILABLE = False
    print("⚠️ psycopg2 non disponible. Utilisation du stockage JSON en fallback.")

# Charger les variables d'environnement
load_dotenv()

# Configuration
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
API_KEY = os.getenv('VALORANT_API_KEY', 'HDEV-c797c6bf-6699-49b0-9bc8-a369c13e5cac')
RIOT_API_KEY = os.getenv('RIOT_API_KEY')  # Clé API Riot pour LoL
DUO_NAME = os.getenv('DUO_NAME')  # Nom du joueur (ex: "Loopy")
DUO_TAG = os.getenv('DUO_TAG')    # Tag du joueur (ex: "EUW")
CHANNEL_ID = int(os.getenv('DISCORD_CHANNEL_ID', '0'))
LOL_CHANNEL_ID = int(os.getenv('LOL_CHANNEL_ID', '0'))  # Channel pour les notifications LoL (optionnel, sinon même que Valorant)
# ID de l'utilisateur à mentionner dans les notifications (optionnel)
NOTIFY_USER_ID = os.getenv('NOTIFY_USER_ID', '265556280033148929')
# Intervalle par défaut: 90 secondes pour respecter le rate limit (90 req/min pour Advanced key)
# Cela fait environ 40 requêtes/heure, ce qui est sûr
POLL_INTERVAL = int(os.getenv('POLL_INTERVAL', '90'))  # Secondes entre les vérifications

# Configuration PostgreSQL (Railway injecte automatiquement DATABASE_URL)
DATABASE_URL = os.getenv('DATABASE_URL')
db_connection = None

# Régions LoL disponibles
LOL_REGIONS = {
    'euw': 'europe',
    'eun': 'europe',
    'na': 'americas',
    'br': 'americas',
    'lan': 'americas',
    'las': 'americas',
    'oce': 'sea',
    'kr': 'asia',
    'jp': 'asia',
}

# Configuration Discord
intents = discord.Intents.default()
# Plus besoin de message_content pour les slash commands !
bot = commands.Bot(command_prefix='!', intents=intents)

# Base URL de l'API Valorant
API_BASE_URL = 'https://api.henrikdev.xyz/valorant/v1'

# Base URLs de l'API Riot (LoL)
RIOT_API_BASE = {
    'europe': 'https://europe.api.riotgames.com',
    'americas': 'https://americas.api.riotgames.com',
    'asia': 'https://asia.api.riotgames.com',
    'sea': 'https://sea.api.riotgames.com',
}

# Stockage des joueurs trackés et derniers matchs
TRACKED_PLAYERS_FILE = 'tracked_players.json'
LAST_MATCH_FILE = 'last_match.json'
tracked_players = {}  # Format: {puuid: {name, tag, last_match_id}} - Valorant
tracked_players_lol = {}  # Format: {puuid: {name, region, last_match_id}} - LoL

# Variables de compatibilité (gardées pour le premier joueur par défaut)
duo_puuid = None

# ==================== GESTION BASE DE DONNÉES ====================

def ensure_db_connection():
    """Vérifie et rétablit la connexion DB si nécessaire"""
    global db_connection

    if not POSTGRES_AVAILABLE or not DATABASE_URL:
        return False

    try:
        # Tester si la connexion est active
        if db_connection and not db_connection.closed:
            cursor = db_connection.cursor()
            cursor.execute("SELECT 1")
            cursor.close()
            return True
    except Exception:
        pass

    # Reconnexion nécessaire
    try:
        print("🔄 Reconnexion à PostgreSQL...", flush=True)
        db_connection = psycopg2.connect(DATABASE_URL)
        print("✅ Reconnecté à PostgreSQL", flush=True)
        return True
    except Exception as e:
        print(f"⚠️ Erreur de reconnexion à la DB: {e}")
        db_connection = None
        return False

def init_database():
    """Initialize la connexion à la base de données et crée les tables"""
    global db_connection

    if not POSTGRES_AVAILABLE or not DATABASE_URL:
        print("📁 Mode JSON: Pas de base de données PostgreSQL configurée")
        return False

    try:
        db_connection = psycopg2.connect(DATABASE_URL)
        cursor = db_connection.cursor()

        # Créer la table des joueurs trackés Valorant
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tracked_players (
                puuid VARCHAR(255) PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                tag VARCHAR(255) NOT NULL,
                last_match_id VARCHAR(255),
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Créer la table des joueurs trackés LoL
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tracked_players_lol (
                puuid VARCHAR(255) PRIMARY KEY,
                summoner_name VARCHAR(255) NOT NULL,
                region VARCHAR(50) NOT NULL,
                last_match_id VARCHAR(255),
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        db_connection.commit()
        cursor.close()
        print("✅ Base de données PostgreSQL connectée et initialisée (Valorant + LoL)")
        return True
    except Exception as e:
        print(f"⚠️ Erreur lors de l'initialisation de la DB: {e}")
        print("📁 Fallback vers le mode JSON")
        db_connection = None
        return False

def load_tracked_players_from_db():
    """Charge les joueurs depuis PostgreSQL"""
    if not db_connection:
        return {}

    try:
        cursor = db_connection.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT * FROM tracked_players")
        rows = cursor.fetchall()
        cursor.close()

        players = {}
        for row in rows:
            players[row['puuid']] = {
                'name': row['name'],
                'tag': row['tag'],
                'last_match_id': row['last_match_id']
            }

        return players
    except Exception as e:
        print(f"⚠️ Erreur lors du chargement depuis la DB: {e}")
        return {}

def save_tracked_players_to_db(players):
    """Sauvegarde les joueurs dans PostgreSQL"""
    if not db_connection:
        return False

    try:
        cursor = db_connection.cursor()

        # Clear et re-insert (simple mais efficace)
        cursor.execute("DELETE FROM tracked_players")

        for puuid, info in players.items():
            cursor.execute("""
                INSERT INTO tracked_players (puuid, name, tag, last_match_id)
                VALUES (%s, %s, %s, %s)
            """, (puuid, info['name'], info['tag'], info.get('last_match_id')))

        db_connection.commit()
        cursor.close()
        return True
    except Exception as e:
        print(f"⚠️ Erreur lors de la sauvegarde dans la DB: {e}")
        db_connection.rollback()
        return False

def load_tracked_players():
    """Charge la liste des joueurs trackés (DB prioritaire, fallback JSON)"""
    # Essayer de charger depuis la DB d'abord
    if db_connection:
        players = load_tracked_players_from_db()
        if players:
            return players

    # Fallback: charger depuis JSON
    try:
        if os.path.exists(TRACKED_PLAYERS_FILE):
            with open(TRACKED_PLAYERS_FILE, 'r') as f:
                return json.load(f)
    except Exception as e:
        print(f"Erreur lors du chargement des joueurs depuis JSON: {e}")
    return {}

def save_tracked_players(players):
    """Sauvegarde la liste des joueurs trackés (DB prioritaire, backup JSON)"""
    # Essayer de sauvegarder dans la DB d'abord
    if db_connection:
        if save_tracked_players_to_db(players):
            print("💾 Joueurs sauvegardés dans PostgreSQL")
            return

    # Fallback: sauvegarder dans JSON
    try:
        with open(TRACKED_PLAYERS_FILE, 'w') as f:
            json.dump(players, f, indent=2)
        print("💾 Joueurs sauvegardés dans JSON (fallback)")
    except Exception as e:
        print(f"⚠️ Erreur lors de la sauvegarde des joueurs: {e}")

def add_tracked_player(name, tag, puuid):
    """Ajoute un joueur à la liste de tracking"""
    global tracked_players
    tracked_players[puuid] = {
        'name': name,
        'tag': tag,
        'last_match_id': None
    }
    save_tracked_players(tracked_players)

def remove_tracked_player(puuid):
    """Retire un joueur de la liste de tracking"""
    global tracked_players
    if puuid in tracked_players:
        del tracked_players[puuid]
        save_tracked_players(tracked_players)
        return True
    return False

def update_last_match_for_player(puuid, match_id):
    """Met à jour le dernier match ID pour un joueur"""
    global tracked_players
    if puuid in tracked_players:
        tracked_players[puuid]['last_match_id'] = match_id
        save_tracked_players(tracked_players)

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

class MatchDetailsView(discord.ui.View):
    """Boutons interactifs pour les notifications de match"""
    def __init__(self, match_id: str, player_name: str, player_tag: str):
        super().__init__(timeout=3600)  # 1 heure
        self.match_id = match_id
        self.player_name = player_name
        self.player_tag = player_tag

        # Ajouter le bouton tracker.gg
        tracker_url = f"https://tracker.gg/valorant/match/{match_id}"
        self.add_item(discord.ui.Button(
            label="Voir sur Tracker.gg",
            url=tracker_url,
            emoji="📊",
            style=discord.ButtonStyle.link
        ))

    @discord.ui.button(label="Réactions", emoji="👍", style=discord.ButtonStyle.secondary)
    async def reaction_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Bouton pour ajouter une réaction rapide"""
        await interaction.response.send_message(
            "Choisissez votre réaction:",
            view=ReactionView(),
            ephemeral=True
        )

class ReactionView(discord.ui.View):
    """Vue pour les réactions rapides"""
    def __init__(self):
        super().__init__(timeout=60)

    @discord.ui.button(label="GG", emoji="🔥", style=discord.ButtonStyle.success)
    async def gg_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("🔥 GG envoyé !", ephemeral=True)
        await interaction.message.edit(view=None)

    @discord.ui.button(label="RIP", emoji="💀", style=discord.ButtonStyle.secondary)
    async def rip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("💀 RIP envoyé !", ephemeral=True)
        await interaction.message.edit(view=None)

    @discord.ui.button(label="Carry", emoji="👑", style=discord.ButtonStyle.primary)
    async def carry_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("👑 Carry king !", ephemeral=True)
        await interaction.message.edit(view=None)

@bot.event
async def on_ready():
    """Événement déclenché quand le bot est prêt"""
    print(f'{bot.user} est connecté!', flush=True)

    # Initialiser la base de données
    init_database()

    # Synchroniser les slash commands
    try:
        synced = await bot.tree.sync()
        print(f"✅ {len(synced)} slash command(s) synchronisée(s)", flush=True)
    except Exception as e:
        print(f"⚠️ Erreur lors de la synchronisation des commandes: {e}", flush=True)

    # Charger les joueurs trackés Valorant
    global tracked_players, duo_puuid
    tracked_players = load_tracked_players()
    print(f"Joueurs Valorant trackés chargés: {len(tracked_players)}", flush=True)

    # Charger les joueurs trackés LoL
    lol_tracker.tracked_players_lol = lol_tracker.load_lol_players_from_db(db_connection)
    print(f"Joueurs LoL trackés chargés: {len(lol_tracker.tracked_players_lol)}", flush=True)

    # Ajouter le joueur par défaut depuis .env s'il existe et n'est pas déjà tracké
    if DUO_NAME and DUO_TAG:
        print(f"Vérification du joueur par défaut: {DUO_NAME}#{DUO_TAG}...", flush=True)
        account_info = get_account_info(DUO_NAME, DUO_TAG)
        if account_info:
            puuid = account_info.get('puuid')
            duo_puuid = puuid  # Compatibilité
            if puuid not in tracked_players:
                print(f"Ajout du joueur par défaut: {DUO_NAME}#{DUO_TAG}", flush=True)
                add_tracked_player(DUO_NAME, DUO_TAG, puuid)
            else:
                print(f"Joueur déjà tracké: {DUO_NAME}#{DUO_TAG}", flush=True)

    # Démarrer la vérification des matchs Valorant
    if CHANNEL_ID:
        check_matches.start()
        print(f"Bot prêt! Vérification des matchs Valorant toutes les {POLL_INTERVAL} secondes.", flush=True)
        print(f"Tracking {len(tracked_players)} joueur(s) Valorant", flush=True)
    else:
        print("⚠️ CHANNEL_ID non configuré.", flush=True)

    # Démarrer la vérification des matchs LoL
    lol_channel = LOL_CHANNEL_ID if LOL_CHANNEL_ID else CHANNEL_ID
    if lol_channel and lol_tracker.tracked_players_lol:
        check_lol_matches.start()
        print(f"✅ Vérification des matchs LoL activée toutes les {POLL_INTERVAL} secondes.", flush=True)
        print(f"Tracking {len(lol_tracker.tracked_players_lol)} joueur(s) LoL", flush=True)
    elif lol_tracker.tracked_players_lol:
        print("⚠️ Joueurs LoL trackés mais aucun channel configuré (LOL_CHANNEL_ID ou CHANNEL_ID)", flush=True)

@tasks.loop(seconds=POLL_INTERVAL)
async def check_matches():
    """Vérifie périodiquement les nouveaux matchs pour tous les joueurs trackés"""
    global tracked_players

    if not CHANNEL_ID or not tracked_players:
        return

    # Vérifier et rétablir la connexion DB si nécessaire
    ensure_db_connection()

    channel = bot.get_channel(CHANNEL_ID)
    if not channel:
        print(f"⚠️ Impossible de trouver le canal avec l'ID {CHANNEL_ID}")
        return

    # Vérifier chaque joueur tracké
    for puuid, player_info in list(tracked_players.items()):
        await check_player_match(channel, puuid, player_info)

async def check_player_match(channel, puuid, player_info):
    """Vérifie les matchs pour un joueur spécifique"""
    try:
        name = player_info['name']
        tag = player_info['tag']
        last_match_id = player_info.get('last_match_id')

        # Récupérer l'historique MMR pour ce joueur (5 matchs pour détecter les streaks)
        mmr_history = get_mmr_history(name, tag, region='eu', size=5)

        if mmr_history is None:
            # Rate limit, attendre avant de continuer
            return
        elif not mmr_history or len(mmr_history) == 0:
            return

        latest_mmr = mmr_history[0]
        latest_match_id = latest_mmr.get('match_id')
        rr_change = latest_mmr.get('mmr_change_to_last_game', 0)
        current_rank = latest_mmr.get('currenttierpatched', 'Unknown')
        current_rr = latest_mmr.get('ranking_in_tier', 0)
        elo = latest_mmr.get('elo', 0)

        # Détecter les streaks
        current_streak = 0
        streak_type = None  # 'win' ou 'loss'
        for i, match in enumerate(mmr_history):
            match_rr = match.get('mmr_change_to_last_game', 0)
            is_win = match_rr > 0

            if i == 0:
                streak_type = 'win' if is_win else 'loss'
                current_streak = 1
            elif (streak_type == 'win' and is_win) or (streak_type == 'loss' and not is_win):
                current_streak += 1
            else:
                break

        if not latest_match_id:
            return

        # Si c'est un nouveau match pour ce joueur
        if latest_match_id != last_match_id:
            print(f"[{name}#{tag}] Nouveau match détecté: {latest_match_id}")

            # Vérifier si le match n'a pas déjà été posté dans le channel
            already_posted = await check_if_match_already_posted(channel, latest_match_id)
            if already_posted:
                print(f"[{name}#{tag}] Match déjà posté, ignoré")
                update_last_match_for_player(puuid, latest_match_id)
                return

            # Récupérer les détails du match
            match_data = get_match_details(latest_match_id)

            if match_data is None:
                # Rate limit
                return

            if match_data:
                # Obtenir les stats du joueur
                player_stats = get_player_stats_from_match(match_data, puuid)

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

                    # Déterminer les badges de performance
                    badges = []
                    if acs >= 300:
                        badges.append("🔥 DOMINATION")
                    elif acs >= 250:
                        badges.append("💪 EXCELLENT")
                    elif acs >= 200:
                        badges.append("👍 SOLIDE")

                    if kd_ratio >= 2.0:
                        badges.append("💀 KILLER")
                    elif kd_ratio >= 1.5:
                        badges.append("⚔️ EFFICACE")

                    if hs_percent >= 40:
                        badges.append("🎯 HEADSHOT MACHINE")

                    # Vérifier si c'est le meilleur de son équipe (MVP)
                    team_players = [p for p in match_data.get('players', {}).get('all_players', []) if p.get('team') == team]
                    if team_players:
                        best_acs = max(p.get('stats', {}).get('score', 0) // max(1, rounds_played) for p in team_players)
                        if acs == best_acs:
                            badges.insert(0, "👑 MVP")

                    badges_text = " ".join(badges) if badges else ""

                    # Ajouter le streak si significatif (3+)
                    streak_text = ""
                    if current_streak >= 3:
                        streak_emoji = "🔥" if streak_type == 'win' else "❄️"
                        streak_word = "victoires" if streak_type == 'win' else "défaites"
                        streak_text = f"\n{streak_emoji} **{current_streak} {streak_word} d'affilée !**"

                    embed = discord.Embed(
                        title=f"{result_emoji} Nouveau match terminé!",
                        description=f"**{name}#{tag}** a **{result_text.lower()}**\n{badges_text}{streak_text}",
                        color=result_color,
                        timestamp=datetime.now(timezone.utc)
                    )

                    # Ajouter l'image de l'agent (thumbnail)
                    # Les URLs des images d'agents sont disponibles dans l'API
                    agent_img = player_stats.get('assets', {}).get('agent', {}).get('small')
                    if agent_img:
                        embed.set_thumbnail(url=agent_img)

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

                    embed.add_field(
                        name="🎯 HS%",
                        value=f"{hs_percent}%",
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

                    # Créer la vue avec les boutons interactifs
                    view = MatchDetailsView(latest_match_id, name, tag)

                    # Mentionner l'utilisateur si l'ID est configuré
                    mention = f"<@{NOTIFY_USER_ID}>" if NOTIFY_USER_ID else ""
                    message_content = mention if mention else None

                    await channel.send(content=message_content, embed=embed, view=view)
                    print(f"[{name}#{tag}] Notification envoyée pour le match {latest_match_id}")
                else:
                    print(f"[{name}#{tag}] Joueur non trouvé dans le match {latest_match_id}")

            # Mettre à jour et sauvegarder le dernier match ID pour ce joueur
            update_last_match_for_player(puuid, latest_match_id)

    except Exception as e:
        print(f"Erreur lors de la vérification des matchs: {e}")
        import traceback
        traceback.print_exc()

@check_matches.before_loop
async def before_check_matches():
    """Attend que le bot soit prêt avant de commencer les vérifications"""
    await bot.wait_until_ready()

# ==================== TASK LOOP LEAGUE OF LEGENDS ====================

@tasks.loop(seconds=POLL_INTERVAL)
async def check_lol_matches():
    """Vérifie périodiquement les nouveaux matchs LoL pour tous les joueurs trackés"""
    if not lol_tracker.tracked_players_lol:
        return

    # Vérifier et rétablir la connexion DB si nécessaire
    ensure_db_connection()

    # Utiliser LOL_CHANNEL_ID si défini, sinon CHANNEL_ID
    channel_id = LOL_CHANNEL_ID if LOL_CHANNEL_ID else CHANNEL_ID
    if not channel_id:
        return

    channel = bot.get_channel(channel_id)
    if not channel:
        print(f"⚠️ Impossible de trouver le canal LoL avec l'ID {channel_id}")
        return

    # Vérifier chaque joueur LoL tracké
    for puuid, player_info in list(lol_tracker.tracked_players_lol.items()):
        match_info = await lol_tracker.check_lol_player_match(db_connection, puuid, player_info)

        if match_info:
            # Créer l'embed
            embed = lol_tracker.create_lol_match_embed(match_info, discord)

            # Mentionner l'utilisateur si configuré
            mention = f"<@{NOTIFY_USER_ID}>" if NOTIFY_USER_ID else ""
            message_content = mention if mention else None

            await channel.send(content=message_content, embed=embed)
            print(f"[LoL - {match_info['summoner_name']}] Notification envoyée pour le match {match_info['match_id']}")

@check_lol_matches.before_loop
async def before_check_lol_matches():
    """Attend que le bot soit prêt avant de commencer les vérifications LoL"""
    await bot.wait_until_ready()

@bot.tree.command(name='test', description='Vérifie que le bot fonctionne')
async def test_command(interaction: discord.Interaction):
    """Commande de test pour vérifier que le bot fonctionne"""
    await interaction.response.send_message("Bot actif! ✅")

@bot.tree.command(name='status', description='Affiche le statut du bot')
async def status_command(interaction: discord.Interaction):
    """Affiche le statut du bot"""
    global tracked_players

    embed = discord.Embed(
        title="Status du bot",
        color=discord.Color.blue()
    )

    embed.add_field(name="Bot", value="🟢 Actif", inline=True)
    embed.add_field(name="Joueurs trackés", value=f"{len(tracked_players)}", inline=True)
    embed.add_field(name="Intervalle", value=f"{POLL_INTERVAL}s", inline=True)

    if tracked_players:
        players_list = "\n".join([f"• {p['name']}#{p['tag']}" for p in tracked_players.values()])
        embed.add_field(name="Liste des joueurs", value=players_list, inline=False)

    await interaction.response.send_message(embed=embed)

@bot.tree.command(name='forcecheck', description='Force une vérification immédiate des matchs')
async def force_check_command(interaction: discord.Interaction):
    """Force une vérification immédiate des matchs"""
    global check_matches
    await interaction.response.send_message("Vérification en cours...")
    await check_matches()
    await interaction.followup.send("Vérification terminée!")

@bot.tree.command(name='addplayer', description='Ajoute un joueur à tracker')
@app_commands.describe(name='Nom du joueur (ex: Loopy)', tag='Tag du joueur (ex: EUW)')
async def add_player_command(interaction: discord.Interaction, name: str, tag: str):
    """Ajoute un joueur à tracker"""
    global tracked_players

    await interaction.response.send_message(f"🔍 Recherche de {name}#{tag}...")

    # Récupérer les infos du compte
    account_info = get_account_info(name, tag)
    if not account_info:
        await interaction.followup.send(f"❌ Joueur {name}#{tag} introuvable. Vérifiez le nom et le tag.")
        return

    puuid = account_info.get('puuid')
    real_name = account_info.get('name')
    real_tag = account_info.get('tag')
    level = account_info.get('account_level')
    region = account_info.get('region')

    # Vérifier si déjà tracké
    if puuid in tracked_players:
        await interaction.followup.send(f"⚠️ {real_name}#{real_tag} est déjà dans la liste de tracking !")
        return

    # Ajouter le joueur
    add_tracked_player(real_name, real_tag, puuid)

    embed = discord.Embed(
        title="✅ Joueur ajouté !",
        description=f"**{real_name}#{real_tag}** est maintenant tracké",
        color=discord.Color.green()
    )
    embed.add_field(name="Région", value=region.upper(), inline=True)
    embed.add_field(name="Niveau", value=level, inline=True)
    embed.add_field(name="Total trackés", value=len(tracked_players), inline=True)

    await interaction.followup.send(embed=embed)

@bot.tree.command(name='removeplayer', description='Retire un joueur du tracking')
@app_commands.describe(name='Nom du joueur', tag='Tag du joueur')
async def remove_player_command(interaction: discord.Interaction, name: str, tag: str):
    """Retire un joueur du tracking"""
    global tracked_players

    # Trouver le joueur dans la liste
    puuid_to_remove = None
    for puuid, player_info in tracked_players.items():
        if player_info['name'].lower() == name.lower() and player_info['tag'].lower() == tag.lower():
            puuid_to_remove = puuid
            break

    if not puuid_to_remove:
        await interaction.response.send_message(f"❌ {name}#{tag} n'est pas dans la liste de tracking")
        return

    # Retirer le joueur
    remove_tracked_player(puuid_to_remove)
    await interaction.response.send_message(f"✅ {name}#{tag} retiré du tracking")

@bot.tree.command(name='listplayers', description='Liste tous les joueurs trackés')
async def list_players_command(interaction: discord.Interaction):
    """Liste tous les joueurs trackés"""
    global tracked_players

    if not tracked_players:
        await interaction.response.send_message("📋 Aucun joueur tracké pour le moment.\nUtilisez `/addplayer nom tag` pour en ajouter.")
        return

    embed = discord.Embed(
        title="📋 Joueurs trackés",
        description=f"{len(tracked_players)} joueur(s) surveillé(s)",
        color=discord.Color.blue()
    )

    for player_info in tracked_players.values():
        name = player_info['name']
        tag = player_info['tag']
        last_match = player_info.get('last_match_id', 'Aucun')
        last_match_short = last_match[:8] + "..." if last_match and last_match != 'Aucun' else 'Aucun'

        embed.add_field(
            name=f"{name}#{tag}",
            value=f"Dernier match: `{last_match_short}`",
            inline=False
        )

    await interaction.response.send_message(embed=embed)

@bot.tree.command(name='stats', description='Affiche les statistiques détaillées d\'un joueur')
@app_commands.describe(name='Nom du joueur (optionnel)', tag='Tag du joueur (optionnel)')
async def stats_command(interaction: discord.Interaction, name: str = None, tag: str = None):
    """Affiche les statistiques détaillées d'un joueur"""
    global tracked_players

    # Si pas de joueur spécifié, utiliser le premier joueur tracké ou le joueur par défaut
    if not name or not tag:
        if tracked_players:
            first_player = list(tracked_players.values())[0]
            name = first_player['name']
            tag = first_player['tag']
        elif DUO_NAME and DUO_TAG:
            name, tag = DUO_NAME, DUO_TAG
        else:
            await interaction.response.send_message("❌ Spécifiez un joueur: /stats nom:xxx tag:xxx")
            return

    await interaction.response.send_message(f"📊 Récupération des statistiques de {name}#{tag}...")

    # Récupérer l'historique MMR (50 derniers matchs)
    mmr_history = get_mmr_history(name, tag, region='eu', size=50)

    if mmr_history is None:
        await interaction.followup.send("⚠️ Rate limit atteint, réessayez dans quelques secondes")
        return
    elif not mmr_history:
        await interaction.followup.send(f"❌ Aucun match trouvé pour {name}#{tag}")
        return

    # Calculer les statistiques
    total_matches = len(mmr_history)
    wins = sum(1 for m in mmr_history if m.get('mmr_change_to_last_game', 0) > 0)
    losses = total_matches - wins
    winrate = round((wins / total_matches) * 100, 1) if total_matches > 0 else 0

    # Calculer le RR total gagné/perdu
    total_rr_change = sum(m.get('mmr_change_to_last_game', 0) for m in mmr_history)
    avg_rr_change = round(total_rr_change / total_matches, 1) if total_matches > 0 else 0

    # Rang actuel
    current_rank = mmr_history[0].get('currenttierpatched', 'Unknown')
    current_rr = mmr_history[0].get('ranking_in_tier', 0)
    current_elo = mmr_history[0].get('elo', 0)

    # Détecter les streaks
    current_streak = 0
    last_result = None
    for match in mmr_history:
        rr = match.get('mmr_change_to_last_game', 0)
        won = rr > 0
        if last_result is None:
            last_result = won
            current_streak = 1
        elif last_result == won:
            current_streak += 1
        else:
            break

    streak_emoji = "🔥" if last_result and current_streak >= 3 else "❄️" if not last_result and current_streak >= 3 else ""
    streak_text = f"{'Victoire' if last_result else 'Défaite'}s" if current_streak > 1 else ""

    # Créer l'embed
    embed_color = discord.Color.green() if winrate >= 50 else discord.Color.red()
    embed = discord.Embed(
        title=f"📊 Statistiques de {name}#{tag}",
        description=f"Basées sur les {total_matches} derniers matchs compétitifs",
        color=embed_color,
        timestamp=datetime.now(timezone.utc)
    )

    # Rang actuel
    embed.add_field(
        name="🏆 Rang actuel",
        value=f"**{current_rank}**\n{current_rr} RR",
        inline=True
    )

    # ELO
    if current_elo > 0:
        embed.add_field(
            name="📊 ELO",
            value=f"{current_elo}",
            inline=True
        )

    # Winrate
    embed.add_field(
        name="📈 Winrate",
        value=f"**{winrate}%**\n{wins}W - {losses}L",
        inline=True
    )

    # RR moyen
    rr_emoji = "📈" if avg_rr_change > 0 else "📉"
    embed.add_field(
        name=f"{rr_emoji} RR Moyen",
        value=f"{'+' if avg_rr_change > 0 else ''}{avg_rr_change} RR/match",
        inline=True
    )

    # RR total
    embed.add_field(
        name="💰 RR Total",
        value=f"{'+' if total_rr_change > 0 else ''}{total_rr_change} RR",
        inline=True
    )

    # Streak actuelle
    if current_streak > 1:
        embed.add_field(
            name=f"{streak_emoji} Série actuelle",
            value=f"**{current_streak}** {streak_text}",
            inline=True
        )

    # Top 3 des maps jouées
    map_counts = {}
    for match in mmr_history:
        map_name = match.get('map', {}).get('name', 'Unknown')
        map_counts[map_name] = map_counts.get(map_name, 0) + 1

    top_maps = sorted(map_counts.items(), key=lambda x: x[1], reverse=True)[:3]
    if top_maps:
        maps_text = "\n".join([f"{i+1}. {map_name} ({count} matchs)" for i, (map_name, count) in enumerate(top_maps)])
        embed.add_field(
            name="🗺️ Maps les plus jouées",
            value=maps_text,
            inline=False
        )

    embed.set_footer(text=f"Historique des {total_matches} derniers matchs compétitifs")

    await interaction.followup.send(embed=embed)

@bot.tree.command(name='rankhistory', description='Affiche l\'historique de rang avec graphique')
@app_commands.describe(name='Nom du joueur (optionnel)', tag='Tag du joueur (optionnel)')
async def rank_history_command(interaction: discord.Interaction, name: str = None, tag: str = None):
    """Affiche l'historique de rang avec un graphique de progression"""
    global tracked_players

    if not MATPLOTLIB_AVAILABLE:
        await interaction.response.send_message("❌ Cette fonctionnalité nécessite matplotlib. Installez-le avec `pip install matplotlib`")
        return

    # Si pas de joueur spécifié, utiliser le premier joueur tracké ou le joueur par défaut
    if not name or not tag:
        if tracked_players:
            first_player = list(tracked_players.values())[0]
            name = first_player['name']
            tag = first_player['tag']
        elif DUO_NAME and DUO_TAG:
            name, tag = DUO_NAME, DUO_TAG
        else:
            await interaction.response.send_message("❌ Spécifiez un joueur: /rankhistory nom:xxx tag:xxx")
            return

    await interaction.response.send_message(f"📈 Génération de l'historique de rang pour {name}#{tag}...")

    # Récupérer l'historique MMR (50 derniers matchs)
    mmr_history = get_mmr_history(name, tag, region='eu', size=50)

    if mmr_history is None:
        await interaction.followup.send("⚠️ Rate limit atteint, réessayez dans quelques secondes")
        return
    elif not mmr_history or len(mmr_history) < 2:
        await interaction.followup.send(f"❌ Pas assez de matchs pour générer un historique")
        return

    # Inverser pour avoir l'ordre chronologique
    mmr_history = list(reversed(mmr_history))

    # Extraire les données pour le graphique
    match_numbers = list(range(1, len(mmr_history) + 1))
    elos = [m.get('elo', 0) for m in mmr_history]
    rr_changes = [m.get('mmr_change_to_last_game', 0) for m in mmr_history]

    # Calculer le RR cumulatif
    cumulative_rr = []
    total = 0
    for rr in rr_changes:
        total += rr
        cumulative_rr.append(total)

    # Créer le graphique
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8))
    fig.suptitle(f'Historique de rang - {name}#{tag}', fontsize=16, fontweight='bold')

    # Graphique 1: ELO au fil du temps
    ax1.plot(match_numbers, elos, marker='o', linewidth=2, markersize=4, color='#FF4655')
    ax1.set_xlabel('Numéro de match', fontsize=11)
    ax1.set_ylabel('ELO', fontsize=11)
    ax1.set_title('Évolution de l\'ELO', fontsize=13)
    ax1.grid(True, alpha=0.3)
    ax1.axhline(y=elos[-1], color='gray', linestyle='--', alpha=0.5, label=f'ELO actuel: {elos[-1]}')
    ax1.legend()

    # Graphique 2: Changement RR cumulatif
    colors = ['green' if rr > 0 else 'red' for rr in cumulative_rr]
    ax2.bar(match_numbers, cumulative_rr, color=colors, alpha=0.6)
    ax2.plot(match_numbers, cumulative_rr, color='blue', linewidth=2, marker='o', markersize=3, label='RR Cumulatif')
    ax2.set_xlabel('Numéro de match', fontsize=11)
    ax2.set_ylabel('RR Cumulatif', fontsize=11)
    ax2.set_title('Gain/Perte de RR cumulatif', fontsize=13)
    ax2.grid(True, alpha=0.3)
    ax2.axhline(y=0, color='black', linestyle='-', alpha=0.3)
    ax2.legend()

    # Ajuster l'espacement
    plt.tight_layout()

    # Sauvegarder le graphique en mémoire
    buffer = io.BytesIO()
    plt.savefig(buffer, format='png', dpi=150, bbox_inches='tight')
    buffer.seek(0)
    plt.close()

    # Créer l'embed avec les stats
    current_rank = mmr_history[-1].get('currenttierpatched', 'Unknown')
    current_rr = mmr_history[-1].get('ranking_in_tier', 0)
    current_elo = mmr_history[-1].get('elo', 0)

    # Calculer les stats
    total_rr_change = cumulative_rr[-1]
    highest_elo = max(elos)
    lowest_elo = min(elos)

    embed = discord.Embed(
        title=f"📈 Historique de rang - {name}#{tag}",
        description=f"Analyse des {len(mmr_history)} derniers matchs compétitifs",
        color=discord.Color.blue(),
        timestamp=datetime.now(timezone.utc)
    )

    embed.add_field(
        name="🏆 Rang actuel",
        value=f"**{current_rank}**\n{current_rr} RR | {current_elo} ELO",
        inline=True
    )

    embed.add_field(
        name="📊 Progression",
        value=f"{'+' if total_rr_change > 0 else ''}{total_rr_change} RR",
        inline=True
    )

    embed.add_field(
        name="📈 ELO Max/Min",
        value=f"Max: {highest_elo}\nMin: {lowest_elo}",
        inline=True
    )

    # Créer le fichier Discord
    file = discord.File(buffer, filename='rank_history.png')
    embed.set_image(url='attachment://rank_history.png')

    await interaction.followup.send(embed=embed, file=file)

@bot.tree.command(name='testapi', description='Teste l\'API Valorant pour un joueur')
@app_commands.describe(name='Nom du joueur (optionnel)', tag='Tag du joueur (optionnel)')
async def test_api_command(interaction: discord.Interaction, name: str = None, tag: str = None):
    """Teste directement l'API pour un joueur"""
    # Utiliser le joueur par défaut si non spécifié
    if not name or not tag:
        if DUO_NAME and DUO_TAG:
            name, tag = DUO_NAME, DUO_TAG
        else:
            await interaction.response.send_message("❌ Spécifiez un joueur: /testapi nom:xxx tag:xxx")
            return

    await interaction.response.send_message(f"🔍 Test de l'API pour {name}#{tag}...")

    # Tester l'endpoint account
    account_info = get_account_info(name, tag)
    if account_info:
        puuid = account_info.get('puuid')
        await interaction.followup.send(f"✅ Compte trouvé - PUUID: `{puuid[:8]}...`")

        # Tester l'endpoint MMR history (le seul qui fonctionne)
        mmr_history = get_mmr_history(name, tag, region='eu', size=3)

        if mmr_history is None:
            await interaction.followup.send("⚠️ Rate limit atteint")
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

            await interaction.followup.send(f"```\n{result}\n```")
        else:
            await interaction.followup.send("❌ Aucun match trouvé dans l'historique MMR")
    else:
        await interaction.followup.send("❌ Impossible de récupérer les informations du compte")

# ==================== COMMANDES LEAGUE OF LEGENDS ====================

@bot.tree.command(name='addplayer-lol', description='Ajoute un invocateur LoL à tracker (EUW only)')
@app_commands.describe(riot_id='Riot ID complet (ex: ThroatGoat#Glucc)')
async def add_lol_player_command(interaction: discord.Interaction, riot_id: str):
    """Ajoute un invocateur LoL à tracker"""

    # Force EUW region
    region = 'euw1'

    # Parser le Riot ID (nom#tag)
    if '#' not in riot_id:
        await interaction.response.send_message(f"❌ Format invalide ! Utilisez le format **Nom#Tag** (ex: ThroatGoat#Glucc)")
        return

    game_name, tag_line = riot_id.split('#', 1)

    await interaction.response.send_message(f"🔍 Recherche de l'invocateur **{riot_id}** sur **{region.upper()}**...")

    # Déterminer la routing region
    routing_region = lol_tracker.REGION_TO_ROUTING.get(region, 'europe')

    # Récupérer le compte Riot (pour avoir le PUUID)
    account_info = lol_tracker.get_account_by_riot_id(game_name, tag_line, routing_region)
    if not account_info:
        await interaction.followup.send(f"❌ Compte Riot **{riot_id}** introuvable. Vérifiez le nom et le tag.")
        return

    puuid = account_info.get('puuid')

    # Récupérer les infos du summoner via PUUID
    summoner_info = lol_tracker.get_summoner_by_puuid(puuid, region)
    if not summoner_info:
        await interaction.followup.send(f"❌ Impossible de récupérer les informations du summoner sur **{region.upper()}**.\nVérifiez que votre clé API Riot est valide et que le joueur existe sur cette région.")
        return

    summoner_name_real = account_info.get('gameName')
    summoner_tag = account_info.get('tagLine')
    summoner_level = summoner_info.get('summonerLevel', 0)
    summoner_id = summoner_info.get('id')

    if not summoner_id:
        await interaction.followup.send(f"❌ Erreur : Impossible de récupérer l'ID du summoner.\nVotre clé API Riot est peut-être expirée. Régénérez-la sur developer.riotgames.com")
        return

    # Vérifier si déjà tracké
    if puuid in lol_tracker.tracked_players_lol:
        await interaction.followup.send(f"⚠️ **{summoner_name_real}#{summoner_tag}** est déjà dans la liste de tracking LoL !")
        return

    # Récupérer les stats ranked (optionnel, ne bloque pas si ça échoue)
    ranked_stats = None
    try:
        ranked_stats = lol_tracker.get_summoner_ranked_stats(summoner_id, region)
    except Exception as e:
        print(f"⚠️ Impossible de récupérer les stats ranked: {e}")

    # Ajouter le joueur (on stocke le Riot ID complet)
    lol_tracker.add_lol_player(db_connection, f"{summoner_name_real}#{summoner_tag}", region, puuid)

    embed = discord.Embed(
        title="✅ Invocateur ajouté !",
        description=f"**{summoner_name_real}#{summoner_tag}** (Niveau {summoner_level}) est maintenant tracké",
        color=discord.Color.blue()
    )
    embed.add_field(name="Région", value=region.upper(), inline=True)
    embed.add_field(name="Niveau", value=summoner_level, inline=True)

    # Ajouter les stats ranked si disponibles
    if ranked_stats:
        for queue in ranked_stats:
            if queue['queueType'] == 'RANKED_SOLO_5x5':
                tier = queue['tier']
                rank = queue['rank']
                lp = queue['leaguePoints']
                wins = queue['wins']
                losses = queue['losses']

                tier_emoji = lol_tracker.get_tier_emoji(tier)
                rank_display = lol_tracker.get_rank_display(tier, rank, lp)

                embed.add_field(
                    name=f"{tier_emoji} Ranked Solo/Duo",
                    value=f"{rank_display}\n{wins}W - {losses}L",
                    inline=False
                )
                break

    embed.add_field(name="Total trackés (LoL)", value=len(lol_tracker.tracked_players_lol), inline=True)

    await interaction.followup.send(embed=embed)

@bot.tree.command(name='listplayers-lol', description='Liste tous les invocateurs LoL trackés')
async def list_lol_players_command(interaction: discord.Interaction):
    """Liste tous les invocateurs LoL trackés"""
    if not lol_tracker.tracked_players_lol:
        await interaction.response.send_message("📋 Aucun invocateur LoL tracké pour le moment.\nUtilisez `/addplayer-lol` pour en ajouter.")
        return

    embed = discord.Embed(
        title="📋 Invocateurs LoL trackés",
        description=f"{len(lol_tracker.tracked_players_lol)} invocateur(s) surveillé(s)",
        color=discord.Color.blue()
    )

    for player_info in lol_tracker.tracked_players_lol.values():
        summoner_name = player_info['summoner_name']
        region = player_info['region']
        last_match = player_info.get('last_match_id', 'Aucun')
        last_match_short = last_match[:8] + "..." if last_match and last_match != 'Aucun' else 'Aucun'

        embed.add_field(
            name=f"{summoner_name} ({region.upper()})",
            value=f"Dernier match: `{last_match_short}`",
            inline=False
        )

    await interaction.response.send_message(embed=embed)

@bot.tree.command(name='rank-lol', description='Affiche le rang actuel d\'un invocateur LoL (EUW)')
@app_commands.describe(riot_id='Riot ID complet (ex: ThroatGoat#Glucc)')
async def rank_lol_command(interaction: discord.Interaction, riot_id: str):
    """Affiche le rang actuel d'un invocateur LoL"""

    # Parser le Riot ID (nom#tag)
    if '#' not in riot_id:
        await interaction.response.send_message(f"❌ Format invalide ! Utilisez le format **Nom#Tag** (ex: ThroatGoat#Glucc)")
        return

    game_name, tag_line = riot_id.split('#', 1)

    await interaction.response.send_message(f"🔍 Recherche du rang de **{riot_id}**...")

    # Force EUW
    region = 'euw1'
    routing_region = 'europe'

    # Récupérer le compte Riot
    account_info = lol_tracker.get_account_by_riot_id(game_name, tag_line, routing_region)
    if not account_info:
        await interaction.followup.send(f"❌ Compte Riot **{riot_id}** introuvable.")
        return

    puuid = account_info.get('puuid')

    # Récupérer les infos du summoner
    summoner_info = lol_tracker.get_summoner_by_puuid(puuid, region)
    if not summoner_info:
        await interaction.followup.send(f"❌ Impossible de récupérer les informations du summoner.")
        return

    summoner_name = account_info.get('gameName')
    summoner_tag = account_info.get('tagLine')
    summoner_level = summoner_info.get('summonerLevel', 0)

    print(f"[Rank-LoL] Fetching rank (Riot API + OP.GG fallback)...")

    # Utiliser la méthode comprehensive (API Riot + OP.GG fallback)
    ranked_stats = lol_tracker.get_rank_comprehensive(puuid, summoner_name, summoner_tag, region)

    # Récupérer les stats du jour
    daily_stats = lol_tracker.get_daily_stats(puuid, region)

    # Couleur basée sur le tier
    tier_colors = {
        'IRON': 0x5C5C5C,
        'BRONZE': 0xCD7F32,
        'SILVER': 0xC0C0C0,
        'GOLD': 0xFFD700,
        'PLATINUM': 0x00CED1,
        'EMERALD': 0x50C878,
        'DIAMOND': 0xB9F2FF,
        'MASTER': 0x9932CC,
        'GRANDMASTER': 0xDC143C,
        'CHALLENGER': 0xF0E68C
    }

    tier = ranked_stats.get('tier', 'GOLD').upper() if ranked_stats else 'GOLD'
    embed_color = tier_colors.get(tier, 0x5865F2)

    # Créer la description principale avec le rank bien mis en avant
    if ranked_stats:
        rank = ranked_stats.get('rank', '')
        lp = ranked_stats.get('lp', 0)
        tier_emoji = lol_tracker.get_tier_emoji(tier)

        # Grande description avec le rank
        description = f"## {tier_emoji} {tier.title()} {rank}\n"
        description += f"**{lp} LP** • Level {summoner_level}\n"
    else:
        description = f"## ❌ Unranked\n"
        description += f"Level {summoner_level}\n"

    embed = discord.Embed(
        title=f"{summoner_name}#{summoner_tag}",
        description=description,
        color=embed_color,
        timestamp=datetime.now(timezone.utc)
    )

    # Stats du jour - field séparé et aéré
    if daily_stats and daily_stats['games'] > 0:
        daily_wins = daily_stats['wins']
        daily_losses = daily_stats['losses']
        daily_games = daily_stats['games']
        daily_wr = round((daily_wins / daily_games) * 100) if daily_games > 0 else 0

        # Emoji basé sur la performance
        if daily_wins > daily_losses:
            wr_emoji = "🟢"
        elif daily_losses > daily_wins:
            wr_emoji = "🔴"
        else:
            wr_emoji = "🟡"

        embed.add_field(
            name="📅 Today",
            value=f"{wr_emoji} **{daily_wins}W - {daily_losses}L** ({daily_wr}%)\n{daily_games} games played",
            inline=False
        )
    else:
        embed.add_field(
            name="📅 Today",
            value="No ranked games yet",
            inline=False
        )

    # ═══════════════════════════════════════════
    # 🎯 PLAT CHALLENGE - Style aéré
    # ═══════════════════════════════════════════
    if ranked_stats:
        challenge = lol_tracker.get_plat_challenge_status(
            ranked_stats.get('tier', ''),
            ranked_stats.get('rank', ''),
            ranked_stats.get('lp', 0)
        )

        # Séparateur visuel
        embed.add_field(name="\u200b", value="───────────────────", inline=False)

        if challenge['completed']:
            embed.add_field(
                name="👑 PLAT CHALLENGE",
                value="🎉 **CHALLENGE COMPLETED!**\nWelcome to Platinum!",
                inline=False
            )
        else:
            # Emoji urgence
            days = challenge['days_remaining']
            hours = challenge['hours_remaining']

            if days <= 1:
                urgency_emoji = "🚨"
            elif days <= 2:
                urgency_emoji = "⚠️"
            else:
                urgency_emoji = "🎯"

            # Progress bar style original (plus lisible)
            progress = challenge['progress_percent']
            filled = int(progress / 5)  # 20 segments
            empty = 20 - filled
            bar = "▓" * filled + "░" * empty
            
            # Couleur basée sur l'urgence pour le temps
            if days <= 1:
                time_box = f"```diff\n- {days}j {hours}h remaining -\n```"
            elif days <= 2:
                time_box = f"```fix\n{days}j {hours}h remaining\n```"
            else:
                time_box = f"```\n{days}j {hours}h remaining\n```"
            
            # Box pour les LP
            lp_box = f"```\n📍 {challenge['lp_needed']} LP to go\n```"
            
            challenge_text = f"**Goal:** PLATINUM IV\n"
            challenge_text += f"`{bar}` **{progress}%**\n"
            challenge_text += lp_box
            challenge_text += time_box
            challenge_text += f"*{challenge['message']}*"

            embed.add_field(
                name=f"{urgency_emoji} PLAT CHALLENGE",
                value=challenge_text,
                inline=False
            )

    embed.set_footer(text="OP.GG • Riot Games API")

    await interaction.followup.send(embed=embed)

# Lancer le bot
if __name__ == '__main__':
    if not DISCORD_TOKEN:
        print("⚠️ ERREUR: DISCORD_TOKEN n'est pas défini dans le .env")
        print("Créez un fichier .env avec vos tokens. Voir .env.example")
    else:
        bot.run(DISCORD_TOKEN)


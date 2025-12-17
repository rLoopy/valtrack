"""
League of Legends Tracker Module
Fonctions et utilitaires pour tracker les matchs LoL
"""

import requests
import os
from datetime import datetime, timezone

# Configuration
RIOT_API_KEY = os.getenv('RIOT_API_KEY')

# Base URLs de l'API Riot (LoL)
RIOT_API_BASE = {
    'europe': 'https://europe.api.riotgames.com',
    'americas': 'https://americas.api.riotgames.com',
    'asia': 'https://asia.api.riotgames.com',
    'sea': 'https://sea.api.riotgames.com',
}

# Mapping régions vers régions routing
REGION_TO_ROUTING = {
    'euw1': 'europe',
    'eun1': 'europe',
    'na1': 'americas',
    'br1': 'americas',
    'la1': 'americas',
    'la2': 'americas',
    'oc1': 'sea',
    'kr': 'asia',
    'jp1': 'asia',
}

# Stockage en mémoire des joueurs LoL trackés
tracked_players_lol = {}  # Format: {puuid: {name, region, last_match_id}}

# ==================== FONCTIONS DATABASE LOL ====================

def load_lol_players_from_db(db_connection):
    """Charge les joueurs LoL depuis PostgreSQL"""
    if not db_connection:
        return {}

    try:
        from psycopg2.extras import RealDictCursor
        cursor = db_connection.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT * FROM tracked_players_lol")
        rows = cursor.fetchall()
        cursor.close()

        players = {}
        for row in rows:
            players[row['puuid']] = {
                'summoner_name': row['summoner_name'],
                'region': row['region'],
                'last_match_id': row['last_match_id']
            }

        return players
    except Exception as e:
        print(f"⚠️ Erreur lors du chargement des joueurs LoL depuis la DB: {e}")
        return {}

def save_lol_players_to_db(db_connection, players):
    """Sauvegarde les joueurs LoL dans PostgreSQL"""
    if not db_connection:
        return False

    try:
        cursor = db_connection.cursor()

        # Clear et re-insert
        cursor.execute("DELETE FROM tracked_players_lol")

        for puuid, info in players.items():
            cursor.execute("""
                INSERT INTO tracked_players_lol (puuid, summoner_name, region, last_match_id)
                VALUES (%s, %s, %s, %s)
            """, (puuid, info['summoner_name'], info['region'], info.get('last_match_id')))

        db_connection.commit()
        cursor.close()
        print("💾 Joueurs LoL sauvegardés dans PostgreSQL")
        return True
    except Exception as e:
        print(f"⚠️ Erreur lors de la sauvegarde des joueurs LoL dans la DB: {e}")
        if db_connection:
            db_connection.rollback()
        return False

def add_lol_player(db_connection, summoner_name, region, puuid):
    """Ajoute un joueur LoL à la liste de tracking"""
    global tracked_players_lol
    tracked_players_lol[puuid] = {
        'summoner_name': summoner_name,
        'region': region,
        'last_match_id': None
    }
    save_lol_players_to_db(db_connection, tracked_players_lol)

def remove_lol_player(db_connection, puuid):
    """Retire un joueur LoL de la liste de tracking"""
    global tracked_players_lol
    if puuid in tracked_players_lol:
        del tracked_players_lol[puuid]
        save_lol_players_to_db(db_connection, tracked_players_lol)
        return True
    return False

def update_last_match_for_lol_player(db_connection, puuid, match_id):
    """Met à jour le dernier match ID pour un joueur LoL"""
    global tracked_players_lol
    if puuid in tracked_players_lol:
        tracked_players_lol[puuid]['last_match_id'] = match_id
        save_lol_players_to_db(db_connection, tracked_players_lol)

# ==================== FONCTIONS API RIOT ====================

def get_summoner_by_name(summoner_name, region='euw1'):
    """Récupère les informations d'un invocateur LoL par son nom"""
    if not RIOT_API_KEY:
        print("⚠️ RIOT_API_KEY non configurée")
        return None

    # Encoder le nom pour l'URL
    summoner_name_encoded = requests.utils.quote(summoner_name)
    url = f'https://{region}.api.riotgames.com/lol/summoner/v4/summoners/by-name/{summoner_name_encoded}'
    headers = {'X-Riot-Token': RIOT_API_KEY}

    try:
        response = requests.get(url, headers=headers, timeout=10)

        if response.status_code == 429:
            print("⚠️ Rate limit atteint sur l'API Riot")
            return None
        elif response.status_code == 404:
            print(f"❌ Invocateur {summoner_name} introuvable sur {region}")
            return None

        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Erreur lors de la récupération de l'invocateur: {e}")
        return None

def get_summoner_ranked_stats(summoner_id, region='euw1'):
    """Récupère les stats ranked d'un invocateur"""
    if not RIOT_API_KEY:
        return None

    url = f'https://{region}.api.riotgames.com/lol/league/v4/entries/by-summoner/{summoner_id}'
    headers = {'X-Riot-Token': RIOT_API_KEY}

    try:
        response = requests.get(url, headers=headers, timeout=10)

        if response.status_code == 429:
            print("⚠️ Rate limit atteint")
            return None

        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Erreur lors de la récupération des stats ranked: {e}")
        return None

def get_recent_matches(puuid, routing_region='europe', count=20):
    """Récupère l'historique des matchs d'un joueur"""
    if not RIOT_API_KEY:
        return []

    regional_endpoint = RIOT_API_BASE.get(routing_region, RIOT_API_BASE['europe'])
    url = f'{regional_endpoint}/lol/match/v5/matches/by-puuid/{puuid}/ids?start=0&count={count}&type=ranked'
    headers = {'X-Riot-Token': RIOT_API_KEY}

    try:
        response = requests.get(url, headers=headers, timeout=10)

        if response.status_code == 429:
            print("⚠️ Rate limit atteint")
            return None

        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Erreur lors de la récupération des matchs: {e}")
        return []

def get_match_details(match_id, routing_region='europe'):
    """Récupère les détails d'un match LoL"""
    if not RIOT_API_KEY:
        return None

    regional_endpoint = RIOT_API_BASE.get(routing_region, RIOT_API_BASE['europe'])
    url = f'{regional_endpoint}/lol/match/v5/matches/{match_id}'
    headers = {'X-Riot-Token': RIOT_API_KEY}

    try:
        response = requests.get(url, headers=headers, timeout=10)

        if response.status_code == 429:
            print("⚠️ Rate limit atteint")
            return None

        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Erreur lors de la récupération du match LoL: {e}")
        return None

def get_player_stats_from_match(match_data, puuid):
    """Extrait les stats d'un joueur depuis un match LoL"""
    if not match_data or 'info' not in match_data:
        return None

    participants = match_data['info'].get('participants', [])
    for participant in participants:
        if participant.get('puuid') == puuid:
            return participant

    return None

# ==================== UTILITAIRES ====================

def get_rank_display(tier, rank, lp):
    """Formate l'affichage du rang"""
    if tier in ['MASTER', 'GRANDMASTER', 'CHALLENGER']:
        return f"{tier.title()} {lp} LP"
    return f"{tier.title()} {rank} - {lp} LP"

def get_kda_ratio(kills, deaths, assists):
    """Calcule le ratio KDA"""
    if deaths == 0:
        return (kills + assists)
    return round((kills + assists) / deaths, 2)

def get_tier_emoji(tier):
    """Retourne un emoji pour chaque tier"""
    emoji_map = {
        'IRON': '⚫',
        'BRONZE': '🟤',
        'SILVER': '⚪',
        'GOLD': '🟡',
        'PLATINUM': '🔷',
        'EMERALD': '💚',
        'DIAMOND': '💎',
        'MASTER': '🔮',
        'GRANDMASTER': '⭐',
        'CHALLENGER': '👑'
    }
    return emoji_map.get(tier, '🎮')

def format_game_duration(duration_seconds):
    """Formate la durée du match"""
    minutes = duration_seconds // 60
    seconds = duration_seconds % 60
    return f"{minutes}m {seconds}s"


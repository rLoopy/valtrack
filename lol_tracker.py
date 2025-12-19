"""
League of Legends Tracker Module
Fonctions et utilitaires pour tracker les matchs LoL
"""

import requests
import os
import re
import time
from datetime import datetime, timezone

# Cloudscraper for bypassing Cloudflare
try:
    import cloudscraper
    CLOUDSCRAPER_AVAILABLE = True
except ImportError:
    CLOUDSCRAPER_AVAILABLE = False
    print("⚠️ cloudscraper not installed - OP.GG scraping will be limited")

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

    # Vérifier que la connexion est toujours active
    try:
        if db_connection.closed:
            print("⚠️ Connexion DB fermée, impossible de sauvegarder")
            return False
    except Exception:
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

def get_account_by_riot_id(game_name, tag_line, routing_region='europe'):
    """Récupère le compte Riot par Riot ID (game_name#tag_line)"""
    if not RIOT_API_KEY:
        print("⚠️ RIOT_API_KEY non configurée")
        return None

    regional_endpoint = RIOT_API_BASE.get(routing_region, RIOT_API_BASE['europe'])
    url = f'{regional_endpoint}/riot/account/v1/accounts/by-riot-id/{game_name}/{tag_line}'
    headers = {'X-Riot-Token': RIOT_API_KEY}

    print(f"[DEBUG] get_account_by_riot_id URL: {url}")

    try:
        response = requests.get(url, headers=headers, timeout=10)
        print(f"[DEBUG] Account API status code: {response.status_code}")

        if response.status_code == 429:
            print("⚠️ Rate limit atteint sur l'API Riot")
            return None
        elif response.status_code == 404:
            print(f"❌ Compte Riot {game_name}#{tag_line} introuvable (404)")
            print(f"[DEBUG] Response body: {response.text}")
            return None
        elif response.status_code == 403:
            print(f"❌ Accès refusé (403) - Vérifiez votre clé API Riot")
            print(f"[DEBUG] Response body: {response.text}")
            return None
        elif response.status_code != 200:
            print(f"❌ Erreur API: {response.status_code}")
            print(f"[DEBUG] Response body: {response.text}")
            return None

        response.raise_for_status()
        data = response.json()
        print(f"[DEBUG] Account data: {data}")
        return data
    except requests.exceptions.RequestException as e:
        print(f"Erreur lors de la récupération du compte Riot: {e}")
        return None

def get_summoner_by_puuid(puuid, region='euw1'):
    """Récupère les informations d'un invocateur LoL par son PUUID"""
    if not RIOT_API_KEY:
        print("⚠️ RIOT_API_KEY non configurée")
        return None

    url = f'https://{region}.api.riotgames.com/lol/summoner/v4/summoners/by-puuid/{puuid}'
    headers = {'X-Riot-Token': RIOT_API_KEY}

    try:
        response = requests.get(url, headers=headers, timeout=10)
        print(f"[DEBUG] Status code: {response.status_code}")

        if response.status_code == 429:
            print("⚠️ Rate limit atteint sur l'API Riot")
            return None
        elif response.status_code == 404:
            print(f"❌ Invocateur introuvable")
            return None
        elif response.status_code != 200:
            print(f"❌ Erreur API: {response.status_code} - {response.text}")
            return None

        response.raise_for_status()
        data = response.json()
        print(f"[DEBUG] Summoner data FULL: {data}")
        print(f"[DEBUG] Summoner data KEYS: {list(data.keys())}")
        print(f"[DEBUG] Checking for 'id': {'id' in data}")
        print(f"[DEBUG] Checking for 'accountId': {'accountId' in data}")
        return data
    except requests.exceptions.RequestException as e:
        print(f"Erreur lors de la récupération de l'invocateur: {e}")
        return None

def get_summoner_ranked_stats(summoner_id, region='euw1'):
    """Récupère les stats ranked d'un invocateur (DEPRECATED - utiliser get_ranked_stats_by_puuid)"""
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

def get_ranked_stats_by_puuid(puuid, region='euw1'):
    """Récupère les stats ranked d'un invocateur par son PUUID (méthode moderne)"""
    if not RIOT_API_KEY:
        print("⚠️ RIOT_API_KEY non configurée")
        return None

    # L'API Riot ne fournit pas d'endpoint direct /by-puuid/ pour les ranked stats
    # On doit d'abord récupérer le summoner ID via le summoner endpoint
    # Mais comme le summoner endpoint ne retourne plus l'ID, on utilise une approche alternative

    # SOLUTION: Utiliser l'endpoint match-v5 qui accepte le PUUID
    # OU chercher le joueur via la liste des challengers/grandmasters/masters

    # Pour l'instant, essayons l'endpoint league-v4 avec PUUID directement
    url = f'https://{region}.api.riotgames.com/lol/league/v4/entries/by-puuid/{puuid}'
    headers = {'X-Riot-Token': RIOT_API_KEY}

    print(f"[DEBUG] Trying ranked stats by PUUID: {url}")

    try:
        response = requests.get(url, headers=headers, timeout=10)
        print(f"[DEBUG] Ranked stats status code: {response.status_code}")

        if response.status_code == 429:
            print("⚠️ Rate limit atteint")
            return None
        elif response.status_code == 404:
            print("⚠️ Endpoint /by-puuid/ n'existe pas pour les ranked stats")
            return None

        response.raise_for_status()
        data = response.json()
        print(f"[DEBUG] Ranked stats data: {data}")
        return data
    except requests.exceptions.RequestException as e:
        print(f"Erreur lors de la récupération des stats ranked par PUUID: {e}")
        return None

def trigger_opgg_update(game_name, tag_line, region='euw'):
    """
    Trigger une mise à jour du profil sur OP.GG pour avoir les données fraîches.
    Équivalent à cliquer sur le bouton "Update" sur le site.
    """
    if not CLOUDSCRAPER_AVAILABLE:
        return False

    try:
        scraper = cloudscraper.create_scraper(
            browser={
                'browser': 'chrome',
                'platform': 'windows',
                'mobile': False
            }
        )

        # Format: ThroatGoat-Glucc (sans URL encoding pour le tiret)
        formatted_name = f"{game_name}-{tag_line}"
        
        # Headers comme si on venait du site
        headers = {
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Content-Type': 'application/json',
            'Origin': 'https://www.op.gg',
            'Referer': f'https://www.op.gg/summoners/{region}/{formatted_name}',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        
        # Essayer plusieurs formats d'URL (OP.GG change parfois leur API)
        urls_to_try = [
            f"https://www.op.gg/api/v1.0/internal/bypass/summoners/{region}/{formatted_name}/renewal",
            f"https://www.op.gg/api/v1.0/internal/bypass/summoners/{region}/{formatted_name.replace('-', '%23')}/renewal",
            f"https://op.gg/api/v1.0/internal/bypass/summoners/{region}/{formatted_name}/renewal",
        ]
        
        for update_url in urls_to_try:
            print(f"[OP.GG] Trying update URL: {update_url}")
            
            try:
                response = scraper.post(update_url, headers=headers, timeout=10, json={})
                print(f"[OP.GG] Response status: {response.status_code}")
                
                if response.status_code in [200, 201, 202, 204]:
                    print(f"[OP.GG] Profile update triggered successfully!")
                    # Attendre pour que l'update se propage
                    time.sleep(4)
                    return True
                elif response.status_code == 429:
                    print(f"[OP.GG] Rate limited - update on cooldown")
                    # Si on est rate limited, les données sont peut-être déjà à jour
                    return False
                    
            except Exception as url_error:
                print(f"[OP.GG] URL failed: {url_error}")
                continue
        
        print(f"[OP.GG] All update URLs failed")
        return False

    except Exception as e:
        print(f"[OP.GG] Update trigger error: {e}")
        return False


def scrape_opgg_rank(game_name, tag_line, region='euw', force_update=False):
    """
    Scrape le rank depuis OP.GG en utilisant cloudscraper pour bypass Cloudflare.
    Si force_update=True, trigger d'abord une mise à jour du profil.
    """
    if not CLOUDSCRAPER_AVAILABLE:
        print("[OP.GG] cloudscraper not available")
        return None

    # Trigger update si demandé
    if force_update:
        trigger_opgg_update(game_name, tag_line, region)

    try:
        # Créer un scraper qui peut bypass Cloudflare
        scraper = cloudscraper.create_scraper(
            browser={
                'browser': 'chrome',
                'platform': 'windows',
                'mobile': False
            }
        )

        # Formater le nom pour l'URL OP.GG (espaces -> %20, # -> -)
        formatted_name = f"{game_name}-{tag_line}".replace(' ', '%20')
        url = f"https://www.op.gg/summoners/{region}/{formatted_name}"

        print(f"[OP.GG] Scraping rank from: {url}")

        # Ajouter un petit délai pour éviter le rate limit
        time.sleep(1)

        response = scraper.get(url, timeout=15)

        if response.status_code != 200:
            print(f"[OP.GG] HTTP error {response.status_code}")
            return None

        html = response.text

        # Debug: Log HTML length and check for common elements
        print(f"[OP.GG] HTML length: {len(html)} chars")

        # Parser le HTML pour extraire les infos de rank
        rank_data = {}

        # OP.GG utilise Next.js - chercher les données dans __NEXT_DATA__
        next_data_match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
        if next_data_match:
            try:
                import json
                next_data = json.loads(next_data_match.group(1))
                print(f"[OP.GG] Found __NEXT_DATA__ JSON")

                # Naviguer dans la structure JSON pour trouver les données de rank
                # La structure peut varier, chercher récursivement
                def find_ranked_data(obj, path=""):
                    if isinstance(obj, dict):
                        # Chercher les infos de ranked solo
                        if obj.get('queueType') == 'RANKED_SOLO_5x5':
                            print(f"[OP.GG] Found RANKED_SOLO_5x5 at {path}")
                            return obj
                        # Chercher par tier directement
                        if 'tier' in obj and 'lp' in obj:
                            tier = obj.get('tier', '')
                            if tier and tier.upper() in ['IRON', 'BRONZE', 'SILVER', 'GOLD', 'PLATINUM', 'EMERALD', 'DIAMOND', 'MASTER', 'GRANDMASTER', 'CHALLENGER']:
                                print(f"[OP.GG] Found tier data at {path}: {obj}")
                                return obj
                        for key, value in obj.items():
                            result = find_ranked_data(value, f"{path}.{key}")
                            if result:
                                return result
                    elif isinstance(obj, list):
                        for i, item in enumerate(obj):
                            result = find_ranked_data(item, f"{path}[{i}]")
                            if result:
                                return result
                    return None

                ranked_obj = find_ranked_data(next_data)
                if ranked_obj:
                    rank_data['tier'] = ranked_obj.get('tier', '').upper()
                    rank_data['rank'] = ranked_obj.get('division', ranked_obj.get('rank', ''))
                    rank_data['lp'] = ranked_obj.get('lp', ranked_obj.get('leaguePoints', 0))
                    rank_data['wins'] = ranked_obj.get('wins', 0)
                    rank_data['losses'] = ranked_obj.get('losses', 0)
                    rank_data['tier_full'] = f"{rank_data['tier']} {rank_data['rank']}"
                    print(f"[OP.GG] Extracted from JSON: {rank_data}")
                    return rank_data
            except json.JSONDecodeError as e:
                print(f"[OP.GG] Failed to parse __NEXT_DATA__: {e}")
        else:
            print("[OP.GG] No __NEXT_DATA__ found, falling back to regex")

        # Fallback: regex patterns pour le HTML rendu
        # Chercher le tier avec des patterns plus spécifiques à OP.GG
        tier_patterns = [
            # Pattern pour "Gold IV" ou "Emerald II" etc dans un conteneur de rank
            r'(?:tier|rank)[^>]*>[\s\n]*([A-Za-z]+)[\s\n]*(?:</[^>]+>[\s\n]*<[^>]+>[\s\n]*)?([IV]+|[1-4])?',
            # Pattern JSON inline
            r'"tier"\s*:\s*"([A-Z]+)"[^}]*"(?:rank|division)"\s*:\s*"([IV]+)"',
            # Pattern simple pour tier suivi de division
            r'\b(Iron|Bronze|Silver|Gold|Platinum|Emerald|Diamond|Master|Grandmaster|Challenger)\s*([IV1-4]*)\b',
        ]

        for pattern in tier_patterns:
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                tier = match.group(1).strip().upper()
                rank = match.group(2).strip() if match.lastindex >= 2 and match.group(2) else ''
                if tier in ['IRON', 'BRONZE', 'SILVER', 'GOLD', 'PLATINUM', 'EMERALD', 'DIAMOND', 'MASTER', 'GRANDMASTER', 'CHALLENGER']:
                    rank_data['tier'] = tier
                    rank_data['rank'] = rank
                    rank_data['tier_full'] = f"{tier} {rank}".strip()
                    print(f"[OP.GG] Tier found via regex: {tier} {rank}")
                    break

        # Chercher LP
        lp_patterns = [
            r'(\d+)\s*LP',
            r'"lp"\s*:\s*(\d+)',
            r'"leaguePoints"\s*:\s*(\d+)',
        ]

        for pattern in lp_patterns:
            match = re.search(pattern, html)
            if match:
                lp_val = int(match.group(1))
                # Éviter les faux positifs (LP trop élevés sont probablement pas des LP)
                if lp_val <= 100 or 'tier' in rank_data:
                    rank_data['lp'] = lp_val
                    print(f"[OP.GG] LP found: {rank_data['lp']}")
                    break

        # Chercher wins/losses
        wl_patterns = [
            r'(\d+)W\s*(\d+)L',
            r'"wins"\s*:\s*(\d+)[^}]*"losses"\s*:\s*(\d+)',
        ]

        for pattern in wl_patterns:
            match = re.search(pattern, html, re.DOTALL)
            if match:
                rank_data['wins'] = int(match.group(1))
                rank_data['losses'] = int(match.group(2))
                print(f"[OP.GG] W/L found: {rank_data['wins']}W {rank_data['losses']}L")
                break

        if rank_data and ('tier_full' in rank_data or 'tier' in rank_data):
            print(f"[OP.GG] Rank data scraped successfully: {rank_data}")
            return rank_data
        else:
            # Debug: montrer un extrait du HTML pour comprendre la structure
            print("[OP.GG] No rank data found in page")
            # Chercher des indices de ce qui est dans la page
            if 'Unranked' in html or 'unranked' in html:
                print("[OP.GG] Page contains 'Unranked' - player might be unranked")
            if 'Gold' in html or 'Emerald' in html or 'Platinum' in html:
                print("[OP.GG] Page contains rank keywords but couldn't parse them")
            return None

    except Exception as e:
        print(f"[OP.GG] Error scraping: {e}")
        import traceback
        traceback.print_exc()
        return None


def get_rank_from_riot_api(puuid, region='euw1'):
    """
    Essaie de récupérer le rank via l'API Riot.
    Méthode 1: Direct /by-summoner/ si on a le summoner ID
    """
    if not RIOT_API_KEY:
        return None

    # D'abord récupérer les infos du summoner pour avoir le summoner ID
    summoner_info = get_summoner_by_puuid(puuid, region)

    if summoner_info and 'id' in summoner_info:
        summoner_id = summoner_info['id']
        print(f"[Rank] Got summoner ID: {summoner_id[:10]}...")

        # Utiliser l'endpoint /by-summoner/
        try:
            url = f'https://{region}.api.riotgames.com/lol/league/v4/entries/by-summoner/{summoner_id}'
            headers = {'X-Riot-Token': RIOT_API_KEY}
            response = requests.get(url, headers=headers, timeout=10)

            if response.status_code == 200:
                data = response.json()
                for entry in data:
                    if entry.get('queueType') == 'RANKED_SOLO_5x5':
                        return {
                            'tier': entry.get('tier', 'Unranked'),
                            'rank': entry.get('rank', ''),
                            'lp': entry.get('leaguePoints', 0),
                            'wins': entry.get('wins', 0),
                            'losses': entry.get('losses', 0)
                        }
                print("[Rank] No Solo/Duo stats found")
            else:
                print(f"[Rank] API error: {response.status_code}")
        except Exception as e:
            print(f"[Rank] Error: {e}")
    else:
        print("[Rank] No summoner ID available from Riot API")

    return None


def get_rank_comprehensive(puuid, game_name, tag_line, region='euw1'):
    """
    Récupère le rank en essayant plusieurs méthodes:
    1. API Riot (si summoner ID disponible)
    2. Scraping OP.GG (avec cloudscraper pour bypass Cloudflare)
    """

    # Méthode 1: Essayer l'API Riot d'abord
    print(f"[Rank] Trying Riot API...")
    rank_data = get_rank_from_riot_api(puuid, region)

    if rank_data:
        print(f"[Rank] Got rank from Riot API: {rank_data['tier']} {rank_data['rank']}")
        return rank_data

    # Méthode 2: Scraper OP.GG si l'API Riot n'a pas fonctionné
    # force_update=True pour trigger l'actualisation du profil avant de scraper
    print(f"[Rank] Riot API failed, trying OP.GG scraping (with update)...")
    opgg_region = 'euw' if region == 'euw1' else region.replace('1', '')
    opgg_data = scrape_opgg_rank(game_name, tag_line, opgg_region, force_update=True)

    if opgg_data:
        # Convertir le format OP.GG vers le format standard
        tier_full = opgg_data.get('tier_full', '')
        tier = opgg_data.get('tier', '')
        rank = opgg_data.get('rank', '')

        # Si on a tier_full mais pas tier/rank séparés, parser
        if tier_full and not tier:
            parts = tier_full.split()
            if len(parts) >= 2:
                tier = parts[0].upper()
                rank = parts[1] if len(parts) > 1 else ''
            else:
                tier = tier_full.upper()
                rank = ''

        return {
            'tier': tier,
            'rank': rank,
            'lp': opgg_data.get('lp', 0),
            'wins': opgg_data.get('wins', 0),
            'losses': opgg_data.get('losses', 0)
        }

    print("[Rank] All methods failed - player might be unranked")
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


def get_daily_stats(puuid, region='euw1'):
    """
    Récupère les stats de la journée (depuis minuit heure Paris) pour un joueur.
    Retourne: {'wins': X, 'losses': Y, 'games': Z, 'champions': [...]}
    """
    try:
        from zoneinfo import ZoneInfo
        paris_tz = ZoneInfo('Europe/Paris')
    except ImportError:
        # Fallback pour Python < 3.9
        import pytz
        paris_tz = pytz.timezone('Europe/Paris')

    if not RIOT_API_KEY:
        return None

    routing_region = REGION_TO_ROUTING.get(region, 'europe')

    # Timestamp de minuit aujourd'hui (heure Paris)
    now_paris = datetime.now(paris_tz)
    midnight_paris = now_paris.replace(hour=0, minute=0, second=0, microsecond=0)
    midnight_timestamp = int(midnight_paris.timestamp())

    print(f"[DailyStats] Fetching matches since midnight UTC...")

    # Récupérer les 20 derniers matchs ranked
    match_ids = get_recent_matches(puuid, routing_region, count=20)

    if not match_ids:
        print("[DailyStats] No matches found")
        return {'wins': 0, 'losses': 0, 'games': 0, 'champions': []}

    daily_stats = {
        'wins': 0,
        'losses': 0,
        'games': 0,
        'champions': [],
        'total_kills': 0,
        'total_deaths': 0,
        'total_assists': 0
    }

    for match_id in match_ids:
        # Récupérer les détails du match
        match_data = get_match_details(match_id, routing_region)

        if not match_data:
            continue

        # Vérifier si le match est dans les dernières 24h
        game_end_timestamp = match_data.get('info', {}).get('gameEndTimestamp', 0) // 1000  # ms -> s

        if game_end_timestamp < midnight_timestamp:
            # Match d'avant minuit, arrêter (les matchs sont triés du plus récent au plus ancien)
            print(f"[DailyStats] Match {match_id[:10]}... is from before midnight, stopping")
            break

        # Trouver les stats du joueur dans ce match
        player_stats = get_player_stats_from_match(match_data, puuid)

        if player_stats:
            daily_stats['games'] += 1

            if player_stats['win']:
                daily_stats['wins'] += 1
            else:
                daily_stats['losses'] += 1

            daily_stats['champions'].append(player_stats['championName'])
            daily_stats['total_kills'] += player_stats['kills']
            daily_stats['total_deaths'] += player_stats['deaths']
            daily_stats['total_assists'] += player_stats['assists']

    # Calculer le KDA moyen
    if daily_stats['games'] > 0:
        daily_stats['avg_kills'] = round(daily_stats['total_kills'] / daily_stats['games'], 1)
        daily_stats['avg_deaths'] = round(daily_stats['total_deaths'] / daily_stats['games'], 1)
        daily_stats['avg_assists'] = round(daily_stats['total_assists'] / daily_stats['games'], 1)

    print(f"[DailyStats] Today: {daily_stats['wins']}W {daily_stats['losses']}L ({daily_stats['games']} games)")

    return daily_stats


def get_plat_challenge_status(current_tier, current_rank, current_lp):
    """
    Calcule le progrès vers le challenge Platinum.
    Point de départ: Silver 2 50 LP
    Objectif: Platinum IV 0 LP
    """
    try:
        from zoneinfo import ZoneInfo
        paris_tz = ZoneInfo('Europe/Paris')
    except ImportError:
        import pytz
        paris_tz = pytz.timezone('Europe/Paris')

    from datetime import timedelta

    # Hiérarchie des ranks (du plus bas au plus haut)
    tier_order = ['IRON', 'BRONZE', 'SILVER', 'GOLD', 'PLATINUM', 'EMERALD', 'DIAMOND', 'MASTER', 'GRANDMASTER', 'CHALLENGER']
    rank_order = ['IV', 'III', 'II', 'I']  # IV est le plus bas

    # Aussi accepter les chiffres
    rank_map = {'4': 'IV', '3': 'III', '2': 'II', '1': 'I', 'IV': 'IV', 'III': 'III', 'II': 'II', 'I': 'I'}

    current_tier = current_tier.upper() if current_tier else 'UNRANKED'
    current_rank = rank_map.get(str(current_rank).upper(), 'IV') if current_rank else 'IV'
    current_lp = current_lp or 0

    # ═══════════════════════════════════════════
    # CHALLENGE CONFIG
    # ═══════════════════════════════════════════
    # Point de départ: Silver 2 50 LP
    start_tier = 'SILVER'
    start_rank = 'II'
    start_lp = 50

    # Objectif: Platinum IV 0 LP
    target_tier = 'PLATINUM'
    target_rank = 'IV'
    target_lp = 0

    # Calculer le deadline (lundi prochain à minuit Paris)
    now_paris = datetime.now(paris_tz)
    days_until_monday = (7 - now_paris.weekday()) % 7
    if days_until_monday == 0 and now_paris.hour >= 0:
        days_until_monday = 7  # Si on est lundi, c'est le lundi d'après

    next_monday = now_paris + timedelta(days=days_until_monday)
    next_monday = next_monday.replace(hour=0, minute=0, second=0, microsecond=0)

    time_remaining = next_monday - now_paris
    hours_remaining = int(time_remaining.total_seconds() // 3600)
    days_remaining = hours_remaining // 24
    hours_mod = hours_remaining % 24

    # Fonction pour calculer les LP absolus
    def calculate_total_lp(tier, rank, lp):
        if tier not in tier_order:
            return 0
        tier_index = tier_order.index(tier)
        rank_index = rank_order.index(rank) if rank in rank_order else 0
        # Chaque tier = 4 divisions, chaque division = 100 LP
        return (tier_index * 4 + rank_index) * 100 + lp

    # Calculer les LP
    start_total_lp = calculate_total_lp(start_tier, start_rank, start_lp)    # Silver 2 50 LP
    current_total_lp = calculate_total_lp(current_tier, current_rank, current_lp)
    target_total_lp = calculate_total_lp(target_tier, target_rank, target_lp)  # Plat 4 0 LP

    # LP nécessaires depuis le départ jusqu'à l'objectif
    total_lp_journey = target_total_lp - start_total_lp  # LP total du challenge
    lp_climbed = current_total_lp - start_total_lp       # LP déjà grimpés
    lp_needed = target_total_lp - current_total_lp       # LP restants

    # Vérifier si déjà Plat ou plus
    if current_tier in tier_order:
        current_tier_index = tier_order.index(current_tier)
        target_tier_index = tier_order.index(target_tier)

        if current_tier_index >= target_tier_index:
            return {
                'completed': True,
                'current_tier': current_tier,
                'current_rank': current_rank,
                'current_lp': current_lp,
                'target_tier': target_tier,
                'days_remaining': days_remaining,
                'hours_remaining': hours_mod,
                'message': "🎉 CHALLENGE COMPLETED!",
                'progress_percent': 100
            }

    # Calculer le pourcentage basé sur le point de départ
    if total_lp_journey > 0:
        progress_percent = min(100, max(0, int((lp_climbed / total_lp_journey) * 100)))
    else:
        progress_percent = 100

    # Calculer les divisions restantes
    divisions_remaining = max(0, lp_needed // 100)

    # Messages fun basés sur le progrès
    if lp_needed <= 0:
        message = "🎉 CHALLENGE COMPLETED!"
    elif lp_needed <= 100:
        message = "🔥 SO CLOSE! One more division!"
    elif progress_percent >= 75:
        message = "💪 Almost there! Keep pushing!"
    elif progress_percent >= 50:
        message = "😤 Halfway there! Don't give up!"
    elif progress_percent >= 25:
        message = "🎮 Good progress! Keep grinding!"
    elif days_remaining <= 1:
        message = "⏰ LAST DAY! IT'S NOW OR NEVER!"
    elif days_remaining <= 2:
        message = "😰 Time is running out..."
    else:
        message = "🎮 The grind continues..."

    return {
        'completed': False,
        'current_tier': current_tier,
        'current_rank': current_rank,
        'current_lp': current_lp,
        'target_tier': target_tier,
        'start_tier': start_tier,
        'start_rank': start_rank,
        'lp_needed': lp_needed,
        'lp_climbed': lp_climbed,
        'total_lp_journey': total_lp_journey,
        'divisions_remaining': divisions_remaining,
        'days_remaining': days_remaining,
        'hours_remaining': hours_mod,
        'progress_percent': progress_percent,
        'message': message,
        'deadline': next_monday.strftime('%A %d %B %H:%M')
    }

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

# ==================== TRACKING AUTOMATIQUE ====================

async def check_lol_player_match(db_connection, puuid, player_info):
    """Vérifie si un joueur LoL a terminé un nouveau match"""
    try:
        summoner_name = player_info['summoner_name']
        region = player_info['region']
        last_match_id = player_info.get('last_match_id')

        # Déterminer la routing region
        routing_region = REGION_TO_ROUTING.get(region, 'europe')

        # Récupérer les derniers matchs (juste le premier)
        match_ids = get_recent_matches(puuid, routing_region, count=1)

        if match_ids is None:
            # Rate limit
            return None

        if not match_ids or len(match_ids) == 0:
            return None

        latest_match_id = match_ids[0]

        # Si c'est un nouveau match
        if latest_match_id != last_match_id:
            print(f"[LoL - {summoner_name}] Nouveau match détecté: {latest_match_id}")

            # Récupérer les détails du match
            match_data = get_match_details(latest_match_id, routing_region)

            if match_data is None:
                # Rate limit
                return None

            if match_data:
                # Obtenir les stats du joueur
                player_stats = get_player_stats_from_match(match_data, puuid)

                if player_stats:
                    # Essayer de récupérer le rang actuel (API Riot + OP.GG fallback)
                    ranked_info = None
                    try:
                        # Récupérer le Riot ID pour OP.GG
                        routing_region_api = REGION_TO_ROUTING.get(region, 'europe')
                        game_name = None
                        tag_line = None

                        try:
                            account_response = requests.get(
                                f'{RIOT_API_BASE[routing_region_api]}/riot/account/v1/accounts/by-puuid/{puuid}',
                                headers={'X-Riot-Token': RIOT_API_KEY},
                                timeout=10
                            )
                            if account_response.status_code == 200:
                                account_data = account_response.json()
                                game_name = account_data.get('gameName')
                                tag_line = account_data.get('tagLine')
                        except Exception as e:
                            print(f"[LoL - {summoner_name}] Error fetching Riot ID: {e}")

                        print(f"[LoL - {summoner_name}] Fetching rank (Riot API + OP.GG fallback)...")
                        ranked_info = get_rank_comprehensive(puuid, game_name, tag_line, region)

                        if ranked_info:
                            print(f"[LoL - {summoner_name}] Rank found: {ranked_info['tier']} {ranked_info['rank']} - {ranked_info['lp']} LP")
                        else:
                            print(f"[LoL - {summoner_name}] Rank not available (unranked)")
                    except Exception as e:
                        print(f"[LoL - {summoner_name}] Error fetching rank: {e}")

                    # Mettre à jour le dernier match ID
                    update_last_match_for_lol_player(db_connection, puuid, latest_match_id)

                    # Retourner les données pour créer l'embed
                    return {
                        'match_id': latest_match_id,
                        'match_data': match_data,
                        'player_stats': player_stats,
                        'summoner_name': summoner_name,
                        'region': region,
                        'ranked_info': ranked_info
                    }
                else:
                    print(f"[LoL - {summoner_name}] Joueur non trouvé dans le match {latest_match_id}")

            # Mettre à jour quand même pour éviter de re-checker
            update_last_match_for_lol_player(db_connection, puuid, latest_match_id)

    except Exception as e:
        print(f"Erreur lors de la vérification des matchs LoL: {e}")
        import traceback
        traceback.print_exc()

    return None

def create_lol_match_embed(match_info, discord_module, daily_stats=None):
    """Crée l'embed Discord pour une notification de match LoL"""
    match_data = match_info['match_data']
    player_stats = match_info['player_stats']
    summoner_name = match_info['summoner_name']
    match_id = match_info['match_id']
    ranked_info = match_info.get('ranked_info')

    # Infos du match
    info = match_data['info']
    game_duration = info['gameDuration']
    game_mode = info['gameMode']

    # Stats du joueur
    champion = player_stats['championName']
    kills = player_stats['kills']
    deaths = player_stats['deaths']
    assists = player_stats['assists']
    total_damage = player_stats['totalDamageDealtToChampions']
    cs = player_stats['totalMinionsKilled'] + player_stats.get('neutralMinionsKilled', 0)
    vision_score = player_stats['visionScore']
    gold = player_stats['goldEarned']
    level = player_stats['champLevel']

    # Victoire ou défaite
    won = player_stats['win']

    # Calculer KDA
    kda = get_kda_ratio(kills, deaths, assists)

    # Multi-kills
    double_kills = player_stats.get('doubleKills', 0)
    triple_kills = player_stats.get('tripleKills', 0)
    quadra_kills = player_stats.get('quadraKills', 0)
    penta_kills = player_stats.get('pentaKills', 0)

    # Badges de performance
    badges = []
    if penta_kills > 0:
        badges.append("👑 PENTAKILL!")
    elif quadra_kills > 0:
        badges.append("💥 QUADRAKILL!")
    elif triple_kills > 0:
        badges.append("🔥 TRIPLE KILL!")

    if kda >= 5.0:
        badges.append("⭐ PERFECT KDA")
    elif kda >= 3.0:
        badges.append("💪 EXCELLENT KDA")

    # Kill participation
    team_kills = sum(p['kills'] for p in info['participants'] if p['teamId'] == player_stats['teamId'])
    kill_participation = round((kills + assists) / max(1, team_kills) * 100)

    if kill_participation >= 70:
        badges.append("👑 CARRY")
    elif kill_participation >= 50:
        badges.append("🎯 HIGH IMPACT")

    # MVP de l'équipe ?
    team_players = [p for p in info['participants'] if p['teamId'] == player_stats['teamId']]
    best_damage = max(p['totalDamageDealtToChampions'] for p in team_players)
    if total_damage == best_damage and won:
        badges.insert(0, "🏆 MVP")

    badges_text = " ".join(badges) if badges else ""

    # Calculate CS/min (needed for toxic messages)
    cs_per_min = round(cs / (game_duration / 60), 1)

    # Detect if jungler (role)
    role = player_stats.get('teamPosition', '').upper()
    is_jungler = role == 'JUNGLE' or player_stats.get('individualPosition', '').upper() == 'JUNGLE'

    # Toxic messages for losses 😈
    toxic_messages = []
    if not won:
        # JUNGLE DIFF obligatoire pour les junglers
        if is_jungler:
            toxic_messages.append("🌳 JUNGLE DIFF - Outjungled and embarrassed")

        # Messages selon le nombre de morts
        if deaths >= 10:
            toxic_messages.append(f"💀 INTING SIMULATOR: {deaths} deaths (is this a speedrun?)")
        elif deaths >= 7:
            toxic_messages.append(f"🪦 Cemetery resident ({deaths} deaths)")

        # Messages selon le KDA
        if kda < 1.0:
            toxic_messages.append("🤡 KDA < 1.0 - Iron IV gameplay unlocked")

        # Messages selon la kill participation
        if kill_participation < 30:
            toxic_messages.append(f"🎪 {kill_participation}% KP - Were you even playing?")

        # Messages selon le CS (si pas jungler)
        if not is_jungler and cs_per_min < 4:
            toxic_messages.append(f"🌾 {cs_per_min} CS/min - The minions farm themselves now?")

        # Message par défaut si aucun trigger spécial
        if not toxic_messages and not is_jungler:
            default_toxic = [
                "💀 RIP BOZO",
                "🤡 Massive diff gap",
                "😴 Unranked energy",
                "🎪 Entertainment value +100",
                "💩 Hardstuck confirmed",
                "🗿 Built different (negatively)"
            ]
            import random
            toxic_messages.append(random.choice(default_toxic))

    # ═══════════════════════════════════════════════════════════════
    # STYLE RECON / VALORANT NEON
    # Palette: Deep Purple #7B2FBE, Magenta #E100FF, Cyan #00D4FF
    # ═══════════════════════════════════════════════════════════════

    # Couleur principale - Deep Purple (comme les skins Recon)
    result_color = discord_module.Color.from_rgb(123, 47, 190)  # Deep purple #7B2FBE

    # URL de l'image du champion (Data Dragon)
    champion_image_url = f"https://ddragon.leagueoflegends.com/cdn/14.24.1/img/champion/{champion}.png"

    # ══════════════════════════════════════════════════════════════
    # TITRE - Style épuré
    # ══════════════════════════════════════════════════════════════
    if won:
        title = "▸ VICTORY"
    else:
        title = "▸ DEFEAT"

    # ══════════════════════════════════════════════════════════════
    # DESCRIPTION - Style Recon épuré
    # ══════════════════════════════════════════════════════════════

    champion_display = champion.upper()

    # Header avec champion et KDA
    description = f"# {champion_display}\n"
    description += f"### {kills} / {deaths} / {assists}\n\n"

    # Ligne de statut
    if won:
        description += f"**{summoner_name}** ─ ✦ Victory\n"
    else:
        description += f"**{summoner_name}** ─ ✧ Defeat\n"

    # Badges compacts
    if badges_text:
        description += f"\n{badges_text}\n"

    # Message toxique pour défaites
    if not won and toxic_messages:
        description += f"\n> *{toxic_messages[0]}*"

    # Créer l'embed
    embed = discord_module.Embed(
        title=title,
        description=description,
        color=result_color,
        timestamp=discord_module.utils.utcnow()
    )

    # Thumbnail avec l'image du champion
    embed.set_thumbnail(url=champion_image_url)

    # ══════════════════════════════════════════════════════════════
    # STATS - Style minimaliste
    # ══════════════════════════════════════════════════════════════

    kda_arrow = "▲" if kda >= 3.0 else ("▼" if kda < 2.0 and not won else "")

    stats_value = f"```\n"
    stats_value += f"  KDA ─────── {kda:.2f} {kda_arrow}\n"
    stats_value += f"  CS  ─────── {cs} ({cs_per_min}/m)\n"
    stats_value += f"  KP  ─────── {kill_participation}%\n"
    stats_value += f"```"

    embed.add_field(
        name="◈ PERFORMANCE",
        value=stats_value,
        inline=False
    )

    # ══════════════════════════════════════════════════════════════
    # RESOURCES - Compact
    # ══════════════════════════════════════════════════════════════

    resources_value = f"```\n"
    resources_value += f"  DMG ── {total_damage:,}\n"
    resources_value += f"  GOLD ─ {gold:,}\n"
    resources_value += f"  VIS ── {vision_score}\n"
    resources_value += f"  TIME ─ {format_game_duration(game_duration)}\n"
    resources_value += f"```"

    embed.add_field(
        name="◈ STATS",
        value=resources_value,
        inline=True
    )

    # ══════════════════════════════════════════════════════════════
    # RANK - Style progress bar neon
    # ══════════════════════════════════════════════════════════════

    if ranked_info:
        tier = ranked_info['tier']
        rank = ranked_info['rank']
        lp = ranked_info['lp']

        # Barre LP style neon
        filled = int(lp / 10)
        empty = 10 - filled
        lp_bar = "▮" * filled + "▯" * empty

        rank_value = f"```\n"
        rank_value += f"  {tier.upper()} {rank}\n"
        rank_value += f"  {lp_bar}\n"
        rank_value += f"  {lp} LP\n"
        rank_value += f"```"

        embed.add_field(
            name="◈ RANK",
            value=rank_value,
            inline=True
        )

    # ══════════════════════════════════════════════════════════════
    # MULTI-KILLS
    # ══════════════════════════════════════════════════════════════

    if penta_kills > 0 or quadra_kills > 0 or triple_kills > 0:
        multikills = []
        if penta_kills > 0:
            multikills.append(f"PENTAKILL ×{penta_kills}")
        if quadra_kills > 0:
            multikills.append(f"QUADRA ×{quadra_kills}")
        if triple_kills > 0:
            multikills.append(f"TRIPLE ×{triple_kills}")

        embed.add_field(
            name="◈ MULTI-KILLS",
            value="```\n  " + "\n  ".join(multikills) + "\n```",
            inline=False
        )

    # ══════════════════════════════════════════════════════════════
    # DAILY STATS - Style épuré
    # ══════════════════════════════════════════════════════════════

    if daily_stats:
        daily_wins = daily_stats.get('wins', 0)
        daily_losses = daily_stats.get('losses', 0)
        daily_games = daily_wins + daily_losses
        daily_winrate = round((daily_wins / daily_games) * 100) if daily_games > 0 else 0

        # Barre progress style Recon
        wr_filled = int(daily_winrate / 10)
        wr_empty = 10 - wr_filled
        wr_bar = "▮" * wr_filled + "▯" * wr_empty

        # Status icon
        if daily_winrate >= 60:
            status_icon = "▲"
        elif daily_winrate >= 50:
            status_icon = "►"
        else:
            status_icon = "▼"

        daily_value = f"```\n"
        daily_value += f"  TODAY\n"
        daily_value += f"  {daily_wins}W · {daily_losses}L\n"
        daily_value += f"  {wr_bar} {daily_winrate}%\n"
        daily_value += f"```"
        daily_value += f"{status_icon} **{'On Fire' if daily_winrate >= 60 else 'Climbing' if daily_winrate >= 50 else 'Tilted'}**"

        embed.add_field(
            name="▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬",
            value=daily_value,
            inline=False
        )

    # ══════════════════════════════════════════════════════════════
    # FOOTER - Clean
    # ══════════════════════════════════════════════════════════════

    if won:
        footer_text = "GG WP"
    else:
        if is_jungler:
            toxic_footers = [
                "jungle diff",
                "outjungled",
                "skill issue",
                "jungle gap"
            ]
        else:
            toxic_footers = [
                "uninstall.exe",
                "skill issue",
                "elo hell?",
                "certified L",
                "hardstuck"
            ]
        import random
        footer_text = random.choice(toxic_footers)

    embed.set_footer(text=f"◈ {footer_text}")

    return embed


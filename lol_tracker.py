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

    try:
        response = requests.get(url, headers=headers, timeout=10)

        if response.status_code == 429:
            print("⚠️ Rate limit atteint sur l'API Riot")
            return None
        elif response.status_code == 404:
            print(f"❌ Compte Riot {game_name}#{tag_line} introuvable")
            return None

        response.raise_for_status()
        return response.json()
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
    
    print(f"[DEBUG] get_summoner_by_puuid URL: {url}")

    try:
        response = requests.get(url, headers=headers, timeout=10)
        print(f"[DEBUG] Status code: {response.status_code}")

        if response.status_code == 429:
            print("⚠️ Rate limit atteint sur l'API Riot")
            return None
        elif response.status_code == 404:
            print(f"❌ Invocateur introuvable (404)")
            return None
        elif response.status_code != 200:
            print(f"❌ Erreur API: {response.status_code} - {response.text}")
            return None

        response.raise_for_status()
        data = response.json()
        print(f"[DEBUG] Summoner data: {data}")
        return data
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
                    # Récupérer le summoner info pour avoir le summonerId
                    summoner_info = get_summoner_by_puuid(puuid, region)

                    # Récupérer le rang actuel
                    ranked_info = None
                    if summoner_info:
                        summoner_id = summoner_info.get('id')
                        if summoner_id:
                            ranked_stats = get_summoner_ranked_stats(summoner_id, region)
                            if ranked_stats:
                                # Trouver les stats Ranked Solo/Duo
                                for queue in ranked_stats:
                                    if queue.get('queueType') == 'RANKED_SOLO_5x5':
                                        ranked_info = {
                                            'tier': queue.get('tier'),
                                            'rank': queue.get('rank'),
                                            'lp': queue.get('leaguePoints'),
                                            'wins': queue.get('wins'),
                                            'losses': queue.get('losses')
                                        }
                                        break

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

def create_lol_match_embed(match_info, discord_module):
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

    # Color based on win/loss
    result_emoji = '✅' if won else '💀'
    result_color = discord_module.Color.green() if won else discord_module.Color.dark_red()

    # Description différente selon win/loss
    if won:
        description = f"**{summoner_name}** has **won** (nice)\n{badges_text}"
    else:
        toxic_text = "\n".join(toxic_messages)
        description = f"**{summoner_name}** has **lost** (lmao)\n{badges_text}\n\n{toxic_text}"

    # Créer l'embed
    title = f"{result_emoji} LoL Match Complete!" if won else f"{result_emoji} L BOZO - Match Lost!"
    embed = discord_module.Embed(
        title=title,
        description=description,
        color=result_color,
        timestamp=discord_module.utils.utcnow()
    )

    # Champion played
    embed.add_field(
        name="🎭 Champion",
        value=f"{champion} (Level {level})",
        inline=True
    )

    # KDA avec message toxique si mauvais
    kda_label = "⚔️ K/D/A"
    if not won and deaths > kills:
        kda_label = "💀 K/D/A (yikes)"

    embed.add_field(
        name=kda_label,
        value=f"{kills}/{deaths}/{assists}",
        inline=True
    )

    # KDA Ratio avec commentaire
    kda_display = f"{kda:.2f}"
    if not won:
        if kda < 1.0:
            kda_display += " 🤡"
        elif kda < 2.0:
            kda_display += " 📉"

    embed.add_field(
        name="📊 KDA Ratio",
        value=kda_display,
        inline=True
    )

    # Rank actuel (si disponible)
    if ranked_info:
        tier = ranked_info['tier']
        rank = ranked_info['rank']
        lp = ranked_info['lp']
        wins = ranked_info['wins']
        losses = ranked_info['losses']

        tier_emoji = get_tier_emoji(tier)
        rank_display = get_rank_display(tier, rank, lp)
        winrate = round((wins / (wins + losses)) * 100) if (wins + losses) > 0 else 0

        embed.add_field(
            name=f"{tier_emoji} Current Rank",
            value=f"{rank_display}\n{wins}W {losses}L ({winrate}%)",
            inline=True
        )

    # CS (Creep Score)
    embed.add_field(
        name="🗡️ CS",
        value=f"{cs} ({cs_per_min}/min)",
        inline=True
    )

    # Damage
    embed.add_field(
        name="💥 Damage",
        value=f"{total_damage:,}",
        inline=True
    )

    # Kill Participation
    embed.add_field(
        name="🎯 KP%",
        value=f"{kill_participation}%",
        inline=True
    )

    # Vision Score
    embed.add_field(
        name="👁️ Vision",
        value=f"{vision_score}",
        inline=True
    )

    # Gold
    embed.add_field(
        name="💰 Gold",
        value=f"{gold:,}",
        inline=True
    )

    # Game duration
    embed.add_field(
        name="⏱️ Duration",
        value=format_game_duration(game_duration),
        inline=True
    )

    # Game mode
    embed.add_field(
        name="🎮 Mode",
        value=game_mode,
        inline=False
    )

    # Multi-kills if present
    if penta_kills > 0 or quadra_kills > 0 or triple_kills > 0:
        multikills = []
        if penta_kills > 0:
            multikills.append(f"👑 {penta_kills}x Pentakill")
        if quadra_kills > 0:
            multikills.append(f"💥 {quadra_kills}x Quadra")
        if triple_kills > 0:
            multikills.append(f"🔥 {triple_kills}x Triple")

        embed.add_field(
            name="🎊 Multi-kills",
            value="\n".join(multikills),
            inline=False
        )

    # Footer avec match ID + message toxique
    if won:
        footer_text = f"Match ID: {match_id[:8]}... | GG WP"
    else:
        if is_jungler:
            toxic_footers = [
                f"Match ID: {match_id[:8]}... | Jungle diff simply too large",
                f"Match ID: {match_id[:8]}... | Enemy jungler owns you",
                f"Match ID: {match_id[:8]}... | Maybe try normals first?",
                f"Match ID: {match_id[:8]}... | Perma-camped by enemy jungler",
                f"Match ID: {match_id[:8]}... | Griefing the lanes speedrun",
                f"Match ID: {match_id[:8]}... | Jungle gap insurmountable"
            ]
        else:
            toxic_footers = [
                f"Match ID: {match_id[:8]}... | Uninstall recommended",
                f"Match ID: {match_id[:8]}... | Better luck next time (you'll need it)",
                f"Match ID: {match_id[:8]}... | Elo hell or skill issue?",
                f"Match ID: {match_id[:8]}... | Certified L moment",
                f"Match ID: {match_id[:8]}... | Built different (negatively)",
                f"Match ID: {match_id[:8]}... | Hardstuck speedrun any%"
            ]
        import random
        footer_text = random.choice(toxic_footers)

    embed.set_footer(text=footer_text)

    return embed


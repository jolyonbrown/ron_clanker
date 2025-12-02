#!/usr/bin/env python3
"""
Import Historical FPL Season Data

Imports gameweek-by-gameweek player performance data from previous seasons
using the vaastav/Fantasy-Premier-League GitHub archive.

Data source: https://github.com/vaastav/Fantasy-Premier-League

Usage:
    python import_historical_seasons.py                    # Import all available seasons
    python import_historical_seasons.py --seasons 2023-24  # Import specific season
    python import_historical_seasons.py --seasons 2022-23 2023-24 2024-25
    python import_historical_seasons.py --dry-run          # Preview without importing

Key design decisions:
    1. Uses player 'code' as stable identifier across seasons (not 'id')
    2. Downloads CSVs directly from GitHub (no local caching needed)
    3. Handles missing columns gracefully (older seasons have fewer metrics)
    4. Skips current season (handled by regular data collection)
"""

import sys
import argparse
import logging
import sqlite3
import csv
from io import StringIO
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any
import requests
from dataclasses import dataclass

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('historical_import')

# GitHub raw content base URL
GITHUB_BASE = "https://raw.githubusercontent.com/vaastav/Fantasy-Premier-League/master/data"

# Available seasons (oldest to newest)
AVAILABLE_SEASONS = [
    '2016-17', '2017-18', '2018-19', '2019-20',
    '2020-21', '2021-22', '2022-23', '2023-24', '2024-25'
]

# Current season (skip this - we have live data)
CURRENT_SEASON = '2025-26'


@dataclass
class SeasonStats:
    """Track import statistics for a season."""
    season_id: str
    players_imported: int = 0
    gameweeks_imported: int = 0
    teams_imported: int = 0
    errors: int = 0
    duration_seconds: float = 0


def fetch_csv(url: str) -> Optional[List[Dict]]:
    """Fetch and parse a CSV file from GitHub."""
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        reader = csv.DictReader(StringIO(response.text))
        return list(reader)
    except Exception as e:
        logger.warning(f"Failed to fetch {url}: {e}")
        return None


def safe_int(value: Any, default: int = 0) -> int:
    """Safely convert to int."""
    if value is None or value == '' or value == 'None':
        return default
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return default


def safe_float(value: Any, default: float = None) -> Optional[float]:
    """Safely convert to float."""
    if value is None or value == '' or value == 'None':
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def import_season(conn: sqlite3.Connection, season_id: str, dry_run: bool = False) -> SeasonStats:
    """
    Import all data for a single season.

    Args:
        conn: SQLite database connection
        season_id: Season identifier (e.g., '2023-24')
        dry_run: If True, don't actually insert data

    Returns:
        SeasonStats with import statistics
    """
    stats = SeasonStats(season_id=season_id)
    start_time = datetime.now()
    cursor = conn.cursor()

    logger.info(f"Importing season {season_id}...")

    # Parse season years
    years = season_id.split('-')
    start_year = 2000 + int(years[0]) if len(years[0]) == 2 else int(years[0])
    end_year = 2000 + int(years[1]) if len(years[1]) == 2 else int(years[1])

    # =========================================================================
    # 1. Register the season
    # =========================================================================
    if not dry_run:
        cursor.execute("""
            INSERT OR REPLACE INTO seasons (id, name, start_year, end_year, data_source)
            VALUES (?, ?, ?, ?, 'vaastav_github')
        """, (season_id, f"{start_year}/{end_year % 100:02d}", start_year, end_year))

    # =========================================================================
    # 2. Import teams
    # =========================================================================
    teams_url = f"{GITHUB_BASE}/{season_id}/teams.csv"
    teams_data = fetch_csv(teams_url)

    if teams_data:
        for team in teams_data:
            if not dry_run:
                try:
                    cursor.execute("""
                        INSERT OR REPLACE INTO historical_teams
                        (season_id, team_code, season_team_id, name, short_name, strength,
                         strength_attack_home, strength_attack_away,
                         strength_defence_home, strength_defence_away)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        season_id,
                        safe_int(team.get('code', team.get('id'))),
                        safe_int(team.get('id')),
                        team.get('name', ''),
                        team.get('short_name', ''),
                        safe_int(team.get('strength')),
                        safe_int(team.get('strength_attack_home')),
                        safe_int(team.get('strength_attack_away')),
                        safe_int(team.get('strength_defence_home')),
                        safe_int(team.get('strength_defence_away'))
                    ))
                    stats.teams_imported += 1
                except Exception as e:
                    logger.warning(f"Failed to import team {team.get('name')}: {e}")
                    stats.errors += 1
        logger.info(f"  Imported {stats.teams_imported} teams")

    # =========================================================================
    # 3. Import players
    # =========================================================================
    players_url = f"{GITHUB_BASE}/{season_id}/players_raw.csv"
    players_data = fetch_csv(players_url)

    player_code_to_element = {}  # Map code -> element_id for this season

    if players_data:
        for player in players_data:
            player_code = safe_int(player.get('code'))
            element_id = safe_int(player.get('id'))

            if player_code == 0 or element_id == 0:
                continue

            player_code_to_element[player_code] = element_id

            if not dry_run:
                try:
                    cursor.execute("""
                        INSERT OR REPLACE INTO historical_players
                        (season_id, player_code, season_element_id, first_name, second_name,
                         web_name, team_code, element_type, total_points, total_minutes,
                         goals_scored, assists, clean_sheets, saves, bonus, points_per_game,
                         start_cost, end_cost)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        season_id,
                        player_code,
                        element_id,
                        player.get('first_name', ''),
                        player.get('second_name', ''),
                        player.get('web_name', ''),
                        safe_int(player.get('team_code', player.get('team'))),
                        safe_int(player.get('element_type')),
                        safe_int(player.get('total_points')),
                        safe_int(player.get('minutes')),
                        safe_int(player.get('goals_scored')),
                        safe_int(player.get('assists')),
                        safe_int(player.get('clean_sheets')),
                        safe_int(player.get('saves')),
                        safe_int(player.get('bonus')),
                        safe_float(player.get('points_per_game')),
                        safe_int(player.get('now_cost')),  # End of season cost
                        safe_int(player.get('now_cost'))
                    ))
                    stats.players_imported += 1
                except Exception as e:
                    logger.warning(f"Failed to import player {player.get('web_name')}: {e}")
                    stats.errors += 1
        logger.info(f"  Imported {stats.players_imported} players")

    # =========================================================================
    # 4. Import gameweek data
    # =========================================================================
    # Build reverse mapping: element_id -> player_code
    element_to_code = {v: k for k, v in player_code_to_element.items()}

    for gw in range(1, 39):
        gw_url = f"{GITHUB_BASE}/{season_id}/gws/gw{gw}.csv"
        gw_data = fetch_csv(gw_url)

        if not gw_data:
            continue

        gw_count = 0
        for row in gw_data:
            # Get player code from element ID
            element_id = safe_int(row.get('element'))
            player_code = element_to_code.get(element_id)

            if not player_code:
                continue

            if not dry_run:
                try:
                    cursor.execute("""
                        INSERT OR REPLACE INTO historical_gameweek_data
                        (season_id, player_code, gameweek, minutes, goals_scored, assists,
                         clean_sheets, goals_conceded, own_goals, penalties_saved,
                         penalties_missed, yellow_cards, red_cards, saves, bonus, bps,
                         influence, creativity, threat, ict_index,
                         expected_goals, expected_assists, expected_goal_involvements,
                         expected_goals_conceded, total_points, opponent_team_code,
                         was_home, value, selected, transfers_in, transfers_out,
                         fixture_id, kickoff_time)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        season_id,
                        player_code,
                        gw,
                        safe_int(row.get('minutes')),
                        safe_int(row.get('goals_scored')),
                        safe_int(row.get('assists')),
                        safe_int(row.get('clean_sheets')),
                        safe_int(row.get('goals_conceded')),
                        safe_int(row.get('own_goals')),
                        safe_int(row.get('penalties_saved')),
                        safe_int(row.get('penalties_missed')),
                        safe_int(row.get('yellow_cards')),
                        safe_int(row.get('red_cards')),
                        safe_int(row.get('saves')),
                        safe_int(row.get('bonus')),
                        safe_int(row.get('bps')),
                        safe_float(row.get('influence')),
                        safe_float(row.get('creativity')),
                        safe_float(row.get('threat')),
                        safe_float(row.get('ict_index')),
                        safe_float(row.get('expected_goals')),
                        safe_float(row.get('expected_assists')),
                        safe_float(row.get('expected_goal_involvements')),
                        safe_float(row.get('expected_goals_conceded')),
                        safe_int(row.get('total_points')),
                        safe_int(row.get('opponent_team')),
                        row.get('was_home', '').lower() == 'true',
                        safe_int(row.get('value')),
                        safe_int(row.get('selected')),
                        safe_int(row.get('transfers_in')),
                        safe_int(row.get('transfers_out')),
                        safe_int(row.get('fixture')),
                        row.get('kickoff_time')
                    ))
                    gw_count += 1
                except Exception as e:
                    # Don't log every error - too verbose
                    stats.errors += 1

        stats.gameweeks_imported += gw_count
        if gw % 10 == 0:
            logger.info(f"  GW{gw}: {gw_count} player performances")

    logger.info(f"  Total gameweek records: {stats.gameweeks_imported}")

    # =========================================================================
    # 5. Mark season as imported
    # =========================================================================
    if not dry_run:
        cursor.execute("""
            UPDATE seasons SET import_completed_at = CURRENT_TIMESTAMP WHERE id = ?
        """, (season_id,))
        conn.commit()

    stats.duration_seconds = (datetime.now() - start_time).total_seconds()
    return stats


def update_player_code_mapping(conn: sqlite3.Connection):
    """
    Update the player_code_mapping table to link historical codes to current players.
    """
    logger.info("Updating player code mapping...")
    cursor = conn.cursor()

    # Get current season players
    cursor.execute("""
        SELECT id, code, first_name || ' ' || second_name as name
        FROM players
    """)
    current_players = {row[1]: (row[0], row[2]) for row in cursor.fetchall()}

    # Get all unique player codes from historical data
    cursor.execute("""
        SELECT DISTINCT player_code FROM historical_players
    """)
    historical_codes = [row[0] for row in cursor.fetchall()]

    # Get career stats for each player
    cursor.execute("""
        SELECT
            player_code,
            MIN(season_id) as first_season,
            MAX(season_id) as last_season,
            COUNT(DISTINCT season_id) as seasons_played,
            SUM(total_points) as total_points
        FROM historical_gameweek_data
        GROUP BY player_code
    """)
    career_stats = {row[0]: row[1:] for row in cursor.fetchall()}

    # Insert/update mappings
    for code in historical_codes:
        current_id, current_name = current_players.get(code, (None, None))
        stats = career_stats.get(code, (None, None, 0, 0))

        # Get name from historical data if not current
        if not current_name:
            cursor.execute("""
                SELECT web_name FROM historical_players
                WHERE player_code = ?
                ORDER BY season_id DESC LIMIT 1
            """, (code,))
            result = cursor.fetchone()
            current_name = result[0] if result else 'Unknown'

        cursor.execute("""
            INSERT OR REPLACE INTO player_code_mapping
            (player_code, current_player_id, current_player_name,
             first_seen_season, last_seen_season, seasons_played, total_historical_points)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (code, current_id, current_name, stats[0], stats[1], stats[2], stats[3]))

    conn.commit()
    logger.info(f"Updated mapping for {len(historical_codes)} players")


def main():
    parser = argparse.ArgumentParser(description='Import historical FPL season data')
    parser.add_argument('--seasons', nargs='+',
                        help='Specific seasons to import (e.g., 2023-24 2024-25)')
    parser.add_argument('--all', action='store_true',
                        help='Import all available seasons')
    parser.add_argument('--recent', type=int, default=3,
                        help='Import N most recent seasons (default: 3)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Preview without importing')
    parser.add_argument('--db', default='data/ron_clanker.db',
                        help='Database path')

    args = parser.parse_args()

    # Determine which seasons to import
    if args.seasons:
        seasons_to_import = args.seasons
    elif args.all:
        seasons_to_import = [s for s in AVAILABLE_SEASONS if s != CURRENT_SEASON]
    else:
        # Default: most recent N seasons (excluding current)
        available = [s for s in AVAILABLE_SEASONS if s != CURRENT_SEASON]
        seasons_to_import = available[-args.recent:]

    print("\n" + "=" * 70)
    print("HISTORICAL FPL DATA IMPORT")
    print("=" * 70)
    print(f"Seasons to import: {', '.join(seasons_to_import)}")
    print(f"Database: {args.db}")
    print(f"Dry run: {args.dry_run}")
    print("=" * 70)

    # Connect to database
    conn = sqlite3.connect(args.db)

    all_stats = []

    for season in seasons_to_import:
        if season == CURRENT_SEASON:
            logger.info(f"Skipping current season {CURRENT_SEASON}")
            continue

        if season not in AVAILABLE_SEASONS:
            logger.warning(f"Season {season} not available, skipping")
            continue

        stats = import_season(conn, season, dry_run=args.dry_run)
        all_stats.append(stats)

        print(f"\n{season}: {stats.players_imported} players, "
              f"{stats.gameweeks_imported} GW records, "
              f"{stats.errors} errors, "
              f"{stats.duration_seconds:.1f}s")

    # Update player code mapping
    if not args.dry_run and all_stats:
        update_player_code_mapping(conn)

    conn.close()

    # Summary
    print("\n" + "=" * 70)
    print("IMPORT COMPLETE")
    print("=" * 70)
    total_players = sum(s.players_imported for s in all_stats)
    total_gw = sum(s.gameweeks_imported for s in all_stats)
    total_errors = sum(s.errors for s in all_stats)
    total_time = sum(s.duration_seconds for s in all_stats)

    print(f"Total seasons: {len(all_stats)}")
    print(f"Total players: {total_players}")
    print(f"Total gameweek records: {total_gw}")
    print(f"Total errors: {total_errors}")
    print(f"Total time: {total_time:.1f}s")

    if not args.dry_run:
        print("\nData is now available for ML training!")
        print("Use the v_all_seasons_player_history view for unified access.")


if __name__ == '__main__':
    main()

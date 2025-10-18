#!/usr/bin/env python3
"""
Backfill Player Gameweek History

Fetches historical gameweek-by-gameweek performance data for all players.
This is needed for building prediction models and analyzing past performance.

Usage:
    python backfill_gameweek_history.py           # Fetch all missing GWs
    python backfill_gameweek_history.py --gw 1-7  # Fetch specific range
    python backfill_gameweek_history.py --limit 50 # Test with first 50 players
"""

import sys
import asyncio
import logging
from pathlib import Path
from datetime import datetime
import requests
import time
import argparse

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from data.database import Database

logger = logging.getLogger('ron_clanker.backfill_history')

FPL_API_BASE = "https://fantasy.premierleague.com/api"


def fetch_player_history(element_id: int) -> dict:
    """
    Fetch historical gameweek data for a single player.

    Returns dict with:
        - history: List of past gameweek performances
        - fixtures: Upcoming fixtures
    """
    try:
        url = f"{FPL_API_BASE}/element-summary/{element_id}/"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.warning(f"Failed to fetch history for player {element_id}: {e}")
        return None


def store_gameweek_data(db: Database, player_id: int, gw_data: list):
    """
    Store gameweek performance data for a player.

    gw_data contains fields like:
        - element: player ID
        - fixture: fixture ID
        - round: gameweek number
        - total_points: points scored
        - minutes: minutes played
        - goals_scored, assists, clean_sheets, etc.
    """
    stored = 0

    for gw in gw_data:
        try:
            db.execute_update("""
                INSERT OR REPLACE INTO player_gameweek_history (
                    player_id, gameweek, fixture_id, total_points,
                    minutes, goals_scored, assists, clean_sheets, goals_conceded,
                    own_goals, penalties_saved, penalties_missed, yellow_cards,
                    red_cards, saves, bonus, bps, influence, creativity,
                    threat, ict_index, value, selected, transfers_in,
                    transfers_out
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
            """, (
                player_id,
                gw['round'],
                gw.get('fixture'),
                gw.get('total_points', 0),
                gw.get('minutes', 0),
                gw.get('goals_scored', 0),
                gw.get('assists', 0),
                gw.get('clean_sheets', 0),
                gw.get('goals_conceded', 0),
                gw.get('own_goals', 0),
                gw.get('penalties_saved', 0),
                gw.get('penalties_missed', 0),
                gw.get('yellow_cards', 0),
                gw.get('red_cards', 0),
                gw.get('saves', 0),
                gw.get('bonus', 0),
                gw.get('bps', 0),
                gw.get('influence'),
                gw.get('creativity'),
                gw.get('threat'),
                gw.get('ict_index'),
                gw.get('value'),
                gw.get('selected'),
                gw.get('transfers_in'),
                gw.get('transfers_out')
            ))
            stored += 1

        except Exception as e:
            logger.error(f"Failed to store GW{gw.get('round')} for player {player_id}: {e}")
            continue

    return stored


def main():
    parser = argparse.ArgumentParser(description='Backfill player gameweek history data')
    parser.add_argument('--gw-start', type=int, default=1, help='Start gameweek (default: 1)')
    parser.add_argument('--gw-end', type=int, default=7, help='End gameweek (default: 7)')
    parser.add_argument('--limit', type=int, help='Limit to first N players (for testing)')
    parser.add_argument('--delay', type=float, default=0.3, help='Delay between requests in seconds (default: 0.3)')

    args = parser.parse_args()

    start_time = datetime.now()

    print("\n" + "=" * 80)
    print("PLAYER GAMEWEEK HISTORY BACKFILL")
    print("=" * 80)
    print(f"Gameweek range: GW{args.gw_start}-{args.gw_end}")
    print(f"Started: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")

    logger.info(f"HistoryBackfill: Starting backfill for GW{args.gw_start}-{args.gw_end}")

    # Initialize database
    db = Database()

    # Get all players
    players = db.execute_query("SELECT id, web_name FROM players ORDER BY id")

    if not players:
        print("\n❌ No players found in database. Run collect_fpl_data.py first.")
        logger.error("HistoryBackfill: No players in database")
        return 1

    total_players = len(players)
    if args.limit:
        players = players[:args.limit]
        print(f"⚠️  Limited to first {args.limit} players for testing")

    print(f"\nProcessing {len(players)} players...")
    logger.info(f"HistoryBackfill: Processing {len(players)} of {total_players} total players")

    # Track stats
    stats = {
        'players_processed': 0,
        'players_failed': 0,
        'gameweeks_stored': 0,
        'api_calls': 0
    }

    # Process each player
    for i, player in enumerate(players, 1):
        player_id = player['id']
        player_name = player['web_name']

        # Progress indicator
        if i % 50 == 0 or i == 1:
            elapsed = (datetime.now() - start_time).total_seconds()
            rate = i / elapsed if elapsed > 0 else 0
            remaining = (len(players) - i) / rate if rate > 0 else 0
            print(f"  [{i}/{len(players)}] {player_name} (ETA: {remaining:.0f}s)")

        # Fetch player history
        logger.debug(f"HistoryBackfill: Fetching history for {player_name} ({player_id})")

        try:
            history_data = fetch_player_history(player_id)
            stats['api_calls'] += 1

            if not history_data:
                stats['players_failed'] += 1
                logger.warning(f"HistoryBackfill: No data returned for {player_name}")
                continue

            # Filter for requested gameweek range
            gw_history = history_data.get('history', [])
            filtered_history = [
                gw for gw in gw_history
                if args.gw_start <= gw.get('round', 0) <= args.gw_end
            ]

            if filtered_history:
                stored = store_gameweek_data(db, player_id, filtered_history)
                stats['gameweeks_stored'] += stored
                logger.debug(f"HistoryBackfill: Stored {stored} gameweeks for {player_name}")

            stats['players_processed'] += 1

            # Rate limiting
            time.sleep(args.delay)

        except Exception as e:
            stats['players_failed'] += 1
            logger.error(f"HistoryBackfill: Error processing {player_name}: {e}")
            continue

    duration = (datetime.now() - start_time).total_seconds()

    # Summary
    print("\n" + "=" * 80)
    print("BACKFILL COMPLETE")
    print("=" * 80)
    print(f"Duration: {duration:.1f}s")
    print(f"Players processed: {stats['players_processed']}/{len(players)}")
    print(f"Players failed: {stats['players_failed']}")
    print(f"Gameweeks stored: {stats['gameweeks_stored']}")
    print(f"API calls made: {stats['api_calls']}")
    print(f"Rate: {stats['players_processed']/duration:.1f} players/sec")

    logger.info(
        f"HistoryBackfill: Complete - "
        f"Duration: {duration:.1f}s, "
        f"Players: {stats['players_processed']}/{len(players)}, "
        f"Failed: {stats['players_failed']}, "
        f"Gameweeks: {stats['gameweeks_stored']}, "
        f"API calls: {stats['api_calls']}"
    )

    # Verify data
    verification = db.execute_query("""
        SELECT gameweek, COUNT(*) as count
        FROM player_gameweek_history
        GROUP BY gameweek
        ORDER BY gameweek
    """)

    if verification:
        print("\nData verification:")
        for row in verification:
            print(f"  GW{row['gameweek']}: {row['count']} player records")

    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\nBackfill cancelled.")
        sys.exit(1)
    except Exception as e:
        logger.error(f"HistoryBackfill: Fatal error: {e}", exc_info=True)
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

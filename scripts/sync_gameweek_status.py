#!/usr/bin/env python3
"""
Sync Gameweek Status from FPL API

Fetches current gameweek status from FPL API and updates database.
This is the single source of truth for gameweek tracking.

Updates:
- is_current flag (which GW is live)
- is_next flag (which GW is upcoming)
- finished flag (which GWs are complete)

Run regularly (e.g., every hour via cron) to keep GW status accurate.

Usage:
    python scripts/sync_gameweek_status.py
    python scripts/sync_gameweek_status.py --verbose
"""

import sys
from pathlib import Path
import requests
import logging
import argparse
from datetime import datetime

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from data.database import Database

logger = logging.getLogger('ron_clanker.sync_gameweek')

FPL_API = "https://fantasy.premierleague.com/api/bootstrap-static/"


def fetch_gameweek_status():
    """Fetch current gameweek status from FPL API."""
    try:
        response = requests.get(FPL_API, timeout=10)
        response.raise_for_status()
        data = response.json()

        events = data['events']

        # Extract current, next, and previous GW
        current_gw = next((e for e in events if e['is_current']), None)
        next_gw = next((e for e in events if e['is_next']), None)

        logger.info(f"GameweekSync: FPL API current GW: {current_gw['id'] if current_gw else 'None'}")
        logger.info(f"GameweekSync: FPL API next GW: {next_gw['id'] if next_gw else 'None'}")

        return events

    except requests.RequestException as e:
        logger.error(f"GameweekSync: Failed to fetch from FPL API: {e}")
        raise


def update_database_gameweeks(db, events):
    """Update gameweek status in database."""

    updated_count = 0

    for event in events:
        gw_id = event['id']
        is_current = 1 if event['is_current'] else 0
        is_next = 1 if event['is_next'] else 0
        finished = 1 if event['finished'] else 0

        try:
            db.execute_update("""
                UPDATE gameweeks
                SET is_current = ?,
                    is_next = ?,
                    finished = ?
                WHERE id = ?
            """, (is_current, is_next, finished, gw_id))

            updated_count += 1

            logger.debug(f"GameweekSync: Updated GW{gw_id}: current={is_current}, next={is_next}, finished={finished}")

        except Exception as e:
            logger.error(f"GameweekSync: Failed to update GW{gw_id}: {e}")
            raise

    logger.info(f"GameweekSync: Updated {updated_count} gameweeks in database")
    return updated_count


def verify_sync(db):
    """Verify database matches FPL API."""

    # Get current GW from database
    db_current = db.execute_query("""
        SELECT id, name, is_current, is_next, finished
        FROM gameweeks
        WHERE is_current = 1
        LIMIT 1
    """)

    # Get next GW from database
    db_next = db.execute_query("""
        SELECT id, name, is_current, is_next, finished
        FROM gameweeks
        WHERE is_next = 1
        LIMIT 1
    """)

    if db_current:
        current_gw = db_current[0]
        logger.info(f"GameweekSync: Database current GW: {current_gw['id']} - {current_gw['name']}")
    else:
        logger.warning("GameweekSync: No current gameweek found in database!")
        current_gw = None

    if db_next:
        next_gw = db_next[0]
        logger.info(f"GameweekSync: Database next GW: {next_gw['id']} - {next_gw['name']}")
    else:
        logger.warning("GameweekSync: No next gameweek found in database!")
        next_gw = None

    return current_gw, next_gw


def main():
    parser = argparse.ArgumentParser(description="Sync gameweek status from FPL API")
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Verbose output')
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    print("=" * 80)
    print("GAMEWEEK STATUS SYNC")
    print("=" * 80)
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    try:
        # Initialize database
        db = Database()

        # Fetch from FPL API
        print("\n📥 Fetching gameweek status from FPL API...")
        events = fetch_gameweek_status()

        # Find current/next GW from API
        current_gw = next((e for e in events if e['is_current']), None)
        next_gw = next((e for e in events if e['is_next']), None)

        print(f"\n✅ FPL API Status:")
        if current_gw:
            status = "LIVE" if not current_gw['finished'] else "FINISHING"
            print(f"   Current: GW{current_gw['id']} ({status})")
            print(f"   Deadline was: {current_gw['deadline_time']}")

        if next_gw:
            print(f"   Next: GW{next_gw['id']}")
            print(f"   Deadline: {next_gw['deadline_time']}")

        # Update database
        print(f"\n💾 Updating database...")
        updated = update_database_gameweeks(db, events)
        print(f"   Updated {updated} gameweeks")

        # Verify
        print(f"\n🔍 Verifying sync...")
        db_current, db_next = verify_sync(db)

        # Check if they match
        api_current_id = current_gw['id'] if current_gw else None
        db_current_id = db_current['id'] if db_current else None

        if api_current_id == db_current_id:
            print(f"   ✅ Database matches FPL API (GW{api_current_id} is current)")
        else:
            print(f"   ❌ MISMATCH: API says GW{api_current_id}, DB says GW{db_current_id}")
            return 1

        print("\n" + "=" * 80)
        print("✅ SYNC COMPLETE")
        print("=" * 80)

        return 0

    except Exception as e:
        logger.error(f"GameweekSync: Fatal error: {e}", exc_info=True)
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())

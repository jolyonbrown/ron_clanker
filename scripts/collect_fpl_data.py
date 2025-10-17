#!/usr/bin/env python3
"""
Collect FPL Data

Fetches latest data from FPL API and stores in database.
Runs daily before Scout intelligence gathering.

This is a wrapper around sync_fpl_data.py for cron job use.
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from agents.data_collector import DataCollector
from data.database import Database
import logging

logger = logging.getLogger('ron_clanker.data_collection')


async def collect_data():
    """Collect latest FPL data."""

    start_time = datetime.now()

    print("\n" + "=" * 80)
    print("FPL DATA COLLECTION")
    print("=" * 80)
    print(f"Timestamp: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")

    collector = DataCollector()
    db = Database()

    try:
        # Fetch FPL data
        print("\n📡 Fetching latest FPL data...")
        fpl_data = await collector.update_all_data()

        if not fpl_data:
            print("❌ Failed to fetch FPL data")
            return 1

        # Sync players
        print(f"\n💾 Syncing {len(fpl_data['players'])} players...")
        for player in fpl_data['players']:
            db.upsert_player(player)
        print("✅ Players synced")

        # Sync teams
        print(f"\n💾 Syncing {len(fpl_data['teams'])} teams...")
        for team in fpl_data['teams']:
            team_data = {
                'id': team['id'],
                'code': team['code'],
                'name': team['name'],
                'short_name': team['short_name'],
                'strength': team.get('strength'),
                'strength_overall_home': team.get('strength_overall_home'),
                'strength_overall_away': team.get('strength_overall_away'),
            }
            db.upsert_team(team_data)
        print("✅ Teams synced")

        # Get current gameweek
        current_gw = None
        for event in fpl_data.get('events', []):
            if event.get('is_current'):
                current_gw = event['id']
                print(f"\n📅 Current Gameweek: {current_gw}")
                break

        # Show stats
        print("\n" + "-" * 80)
        print("DATABASE STATISTICS")
        print("-" * 80)

        player_count = db.execute_query("SELECT COUNT(*) as c FROM players")
        team_count = db.execute_query("SELECT COUNT(*) as c FROM teams")

        if player_count:
            print(f"Players in database: {player_count[0]['c']}")
        if team_count:
            print(f"Teams in database: {team_count[0]['c']}")

        duration = (datetime.now() - start_time).total_seconds()

        print("\n" + "=" * 80)
        print("DATA COLLECTION COMPLETE")
        print("=" * 80)
        print(f"Duration: {duration:.1f} seconds")
        print(f"Status: SUCCESS")

        return 0

    except Exception as e:
        logger.error(f"DataCollection: Error: {e}", exc_info=True)
        print(f"\n❌ Error: {e}")
        return 1

    finally:
        await collector.close()


if __name__ == '__main__':
    try:
        exit_code = asyncio.run(collect_data())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\nData collection cancelled.")
        sys.exit(1)
    except Exception as e:
        logger.error(f"DataCollection: Fatal error: {e}", exc_info=True)
        print(f"\n❌ Fatal error: {e}")
        sys.exit(1)

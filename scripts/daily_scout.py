#!/usr/bin/env python3
"""
Daily Scout Intelligence Gathering

Runs autonomously via cron to collect intelligence from all sources.
Should be scheduled for 3 AM daily (after price changes at ~2 AM).
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from agents.scout import ScoutAgent
from data.database import Database
import logging

logger = logging.getLogger('ron_clanker.daily_scout')


async def main():
    """Run daily Scout intelligence gathering."""

    start_time = datetime.now()

    print("\n" + "=" * 80)
    print("DAILY SCOUT INTELLIGENCE GATHERING")
    print("=" * 80)
    print(f"Timestamp: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"ScoutDaily: Starting daily intelligence gathering at {start_time}")

    db = Database()
    scout = ScoutAgent(database=db)

    # Check current gameweek
    bootstrap = db.execute_query("""
        SELECT data FROM bootstrap_data
        ORDER BY fetched_at DESC LIMIT 1
    """)

    if bootstrap:
        import json
        data = json.loads(bootstrap[0]['data'])
        current_gw = data['current_gameweek']['id']
        print(f"Current Gameweek: {current_gw}")
    else:
        print("⚠️  No bootstrap data available - run data collection first")
        current_gw = None

    # Gather intelligence
    print("\n" + "-" * 80)
    print("GATHERING INTELLIGENCE")
    print("-" * 80)

    try:
        logger.info("ScoutDaily: Initiating intelligence gathering from all sources")
        intelligence = await scout.gather_intelligence()

        logger.info(f"ScoutDaily: Gathered {len(intelligence)} intelligence items")
        print(f"\n✓ Intelligence gathering complete")
        print(f"  Total items: {len(intelligence)}")

        # Breakdown by type
        by_type = {}
        for item in intelligence:
            item_type = item['type']
            by_type[item_type] = by_type.get(item_type, 0) + 1

        logger.info(f"ScoutDaily: Intelligence breakdown - {dict(by_type)}")
        print("\n  Breakdown by type:")
        for item_type, count in sorted(by_type.items()):
            print(f"    {item_type}: {count}")

        # Show sample intelligence
        if intelligence:
            print("\n  Sample intelligence (first 5):")
            for item in intelligence[:5]:
                print(f"    • [{item['type']}] {item['player_name']}")
                details_preview = item['details'][:60]
                if len(item['details']) > 60:
                    details_preview += "..."
                print(f"      {details_preview}")

    except Exception as e:
        logger.error(f"ScoutDaily: Error gathering intelligence: {e}", exc_info=True)
        print(f"\n❌ Error: {e}")
        return 1

    # Database statistics
    print("\n" + "-" * 80)
    print("DATABASE STATISTICS")
    print("-" * 80)

    # Intelligence count
    intel_count = db.execute_query("""
        SELECT COUNT(*) as count FROM intelligence_cache
    """)
    print(f"\nTotal intelligence in cache: {intel_count[0]['count']}")

    # Recent intelligence (last 24 hours)
    recent = db.execute_query("""
        SELECT COUNT(*) as count FROM intelligence_cache
        WHERE timestamp > datetime('now', '-1 day')
    """)
    print(f"Intelligence gathered in last 24h: {recent[0]['count']}")

    # YouTube cache statistics
    youtube_stats = db.execute_query("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN expires_at > CURRENT_TIMESTAMP THEN 1 ELSE 0 END) as valid
        FROM youtube_transcripts
    """)
    if youtube_stats and youtube_stats[0]['total']:
        print(f"\nYouTube transcripts cached: {youtube_stats[0]['total']}")
        print(f"  Valid (not expired): {youtube_stats[0]['valid']}")

    duration = (datetime.now() - start_time).total_seconds()

    logger.info(f"ScoutDaily: Complete - Duration: {duration:.1f}s, Intelligence items: {len(intelligence)}, GW: {current_gw}")

    print("\n" + "=" * 80)
    print("DAILY SCOUT RUN COMPLETE")
    print("=" * 80)
    print(f"Duration: {duration:.1f} seconds")
    print(f"Status: SUCCESS")

    return 0


if __name__ == '__main__':
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\nDaily scout run cancelled by user.")
        sys.exit(1)
    except Exception as e:
        logger.error(f"ScoutDaily: Fatal error: {e}", exc_info=True)
        print(f"\n❌ Fatal error: {e}")
        sys.exit(1)

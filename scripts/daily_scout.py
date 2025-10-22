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
from utils.config import get_telegram_token, get_telegram_chat_id
from telegram_bot.notifications import send_scout_report, send_cron_failure
import logging
import os

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

    # Load player cache for name matching (critical for performance)
    print("\n" + "-" * 80)
    print("LOADING PLAYER CACHE")
    print("-" * 80)
    await scout.load_player_cache()
    print("✓ Player cache loaded")

    # Check current gameweek
    gameweek_data = db.execute_query("""
        SELECT id, name FROM gameweeks
        WHERE is_current = 1
        LIMIT 1
    """)

    if gameweek_data:
        current_gw = gameweek_data[0]['id']
        print(f"Current Gameweek: {current_gw} ({gameweek_data[0]['name']})")
    else:
        print("⚠️  No current gameweek found in database")
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

        # Send failure notification
        if os.getenv('TELEGRAM_NOTIFICATIONS_ENABLED', 'true').lower() == 'true':
            bot_token = get_telegram_token()
            chat_id = get_telegram_chat_id()
            if bot_token and chat_id:
                try:
                    send_cron_failure(
                        bot_token=bot_token,
                        chat_id=chat_id,
                        job_name="Daily Scout",
                        error=str(e)
                    )
                except:
                    pass  # Don't fail on notification failure

        return 1

    # Database statistics
    print("\n" + "-" * 80)
    print("DATABASE STATISTICS")
    print("-" * 80)

    # Check if intelligence_cache table exists
    tables = db.execute_query("""
        SELECT name FROM sqlite_master WHERE type='table' AND name='intelligence_cache'
    """)

    if tables:
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
    else:
        print("\n⚠️  Intelligence cache table not yet created")

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

    # Send Telegram notification (if configured and enabled)
    if os.getenv('TELEGRAM_NOTIFICATIONS_ENABLED', 'true').lower() == 'true':
        bot_token = get_telegram_token()
        chat_id = get_telegram_chat_id()

        if bot_token and chat_id:
            try:
                print("\n📱 Sending Telegram notification...")
                send_scout_report(
                    bot_token=bot_token,
                    chat_id=chat_id,
                    intel_count=len(intelligence),
                    breakdown=by_type,
                    top_items=intelligence[:3] if intelligence else None
                )
                print("   ✓ Notification sent")
            except Exception as e:
                logger.warning(f"Failed to send Telegram notification: {e}")
                print(f"   ⚠️  Failed to send notification: {e}")

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

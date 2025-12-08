#!/usr/bin/env python3
"""
Pre-Deadline Team Selection

Runs 6 hours before each gameweek deadline to make autonomous team selection.
Should be scheduled via cron or triggered by deadline monitoring.
"""

import asyncio
import sys
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from agents.manager_agent_v2 import RonManager
from data.database import Database
from infrastructure.event_bus import EventBus, get_event_bus
from utils.config import load_config
import logging

logger = logging.getLogger('ron_clanker.pre_deadline')


def sync_current_team(db: Database) -> bool:
    """
    Sync current_team table with actual FPL team before selection.

    This prevents using stale team data when transfers were made manually
    on the FPL website.
    """
    from scripts.track_ron_team import sync_current_team_from_fpl, get_team_id

    config = load_config()
    team_id = config.get('team_id')

    if not team_id:
        logger.warning("PreDeadline: No team_id configured, skipping sync")
        return False

    try:
        print("\n🔄 Syncing current_team with FPL API...")
        success = sync_current_team_from_fpl(team_id, verbose=True)
        if success:
            logger.info("PreDeadline: current_team synced successfully")
            return True
        else:
            logger.error("PreDeadline: Failed to sync current_team")
            return False
    except Exception as e:
        logger.error(f"PreDeadline: Error syncing current_team: {e}")
        return False


def get_next_deadline(db: Database) -> Optional[dict]:
    """Get the next gameweek deadline from FPL data."""
    # Get next unfinished gameweek
    next_gw = db.execute_query("""
        SELECT id, name, deadline_time, finished
        FROM gameweeks
        WHERE finished = 0
        ORDER BY id ASC
        LIMIT 1
    """)

    if not next_gw:
        return None

    return {
        'gameweek': next_gw[0]['id'],
        'deadline': next_gw[0]['deadline_time'],
        'name': next_gw[0]['name']
    }


async def main():
    """Run pre-deadline team selection."""

    start_time = datetime.now(timezone.utc)

    print("\n" + "=" * 80)
    print("PRE-DEADLINE TEAM SELECTION")
    print("=" * 80)
    print(f"Timestamp: {start_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")

    db = Database()

    # Initialize event bus for event-driven architecture
    # Note: EventBus uses connect() not start() - but for simple runs, we don't need it
    # event_bus = get_event_bus()
    # await event_bus.connect()

    # Check deadline info
    deadline_info = get_next_deadline(db)

    if not deadline_info:
        print("\n❌ ERROR: Cannot determine next deadline")
        print("Run: venv/bin/python scripts/collect_fpl_data.py")
        return 1

    gameweek = deadline_info['gameweek']
    deadline = deadline_info['deadline']
    name = deadline_info['name']

    print(f"\nNext Deadline: {name}")
    print(f"  Gameweek: {gameweek}")
    print(f"  Deadline: {deadline}")

    # Parse deadline time
    from dateutil.parser import parse as parse_datetime
    deadline_dt = parse_datetime(deadline)
    time_until = (deadline_dt - start_time).total_seconds() / 3600

    print(f"  Time until deadline: {time_until:.1f} hours")

    if time_until < 0:
        print("\n⚠️  WARNING: Deadline has passed!")
    elif time_until > 8:
        print("\n⚠️  WARNING: More than 8 hours until deadline")
        print("  This script should run 6 hours before deadline")

    # CRITICAL: Sync current_team with actual FPL team before selection
    # This prevents using stale team data when transfers were made manually
    print("\n" + "-" * 80)
    print("SYNCING CURRENT TEAM FROM FPL API")
    print("-" * 80)

    if not sync_current_team(db):
        print("⚠️  Could not sync current_team - proceeding with existing data")
        print("  Run: venv/bin/python scripts/track_ron_team.py --sync")

    # Initialize manager (EVENT-DRIVEN)
    print("\n" + "-" * 80)
    print("INITIALIZING RON CLANKER (Event-Driven Manager)")
    print("-" * 80)

    ron = RonManager(database=db)
    await ron.start()  # Start BaseAgent event subscriptions

    # Make team selection
    print("\n" + "-" * 80)
    print(f"SELECTING TEAM FOR GAMEWEEK {gameweek}")
    print("-" * 80)

    try:
        # Make weekly decision (transfers, captain, chip usage)
        # Returns dict with keys: squad, transfers, chip_used, announcement
        result = await ron.make_weekly_decision(gameweek)

        transfers = result['transfers']
        chip_used = result['chip_used']
        announcement = result['announcement']
        squad = result['squad']

        print(f"\n✓ Team selection complete!")
        print(f"   Players: {len(squad)}")
        print(f"   Transfers: {len(transfers)}")
        print(f"   Chip used: {chip_used or 'None'}")

        # Show announcement
        print("\n" + "=" * 80)
        print("RON'S TEAM ANNOUNCEMENT")
        print("=" * 80)
        print(announcement)
        print("=" * 80)

    except Exception as e:
        logger.error(f"PreDeadline: Error during team selection: {e}", exc_info=True)
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

    # Store decision record
    print("\n" + "-" * 80)
    print("STORING DECISION RECORD")
    print("-" * 80)

    try:
        # Get Ron's latest decisions from database
        transfers_logged = db.execute_query("""
            SELECT * FROM transfers
            WHERE gameweek = ?
            ORDER BY executed_at DESC
        """, (gameweek,))

        # Check draft_team (new architecture)
        draft_team = db.get_draft_team(gameweek)

        if transfers_logged:
            print(f"✓ Transfers logged: {len(transfers_logged)} transfer(s)")
        if draft_team and len(draft_team) > 0:
            print(f"✓ Draft team stored: {len(draft_team)} players")
        if not transfers_logged and not draft_team:
            print("⚠️  No decision records found in database")

    except Exception as e:
        logger.warning(f"PreDeadline: Could not verify decision storage: {e}")
        print(f"⚠️  Could not verify decision storage: {e}")

    # Send notification (if configured)
    print("\n" + "-" * 80)
    print("NOTIFICATIONS")
    print("-" * 80)

    webhook_url = None  # TODO: Load from config/environment

    if webhook_url:
        try:
            import requests
            message = {
                "text": f"🤖 Ron Clanker has selected team for GW{gameweek}",
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*Team Selection Complete*\nGameweek {gameweek}\nDeadline: {deadline}"
                        }
                    }
                ]
            }
            response = requests.post(webhook_url, json=message, timeout=10)
            if response.status_code == 200:
                print("✓ Notification sent successfully")
            else:
                print(f"⚠️  Notification failed: HTTP {response.status_code}")
        except Exception as e:
            logger.warning(f"PreDeadline: Notification error: {e}")
            print(f"⚠️  Notification error: {e}")
    else:
        print("⚠️  No webhook configured - set WEBHOOK_URL environment variable")
        print("   to receive notifications (Discord/Slack/etc)")

    # Cleanup event-driven components
    try:
        await ron.stop()
        await event_bus.stop()
    except Exception as e:
        logger.warning(f"PreDeadline: Error during cleanup: {e}")

    duration = (datetime.now(timezone.utc) - start_time).total_seconds()

    print("\n" + "=" * 80)
    print("PRE-DEADLINE SELECTION COMPLETE")
    print("=" * 80)
    print(f"Duration: {duration:.1f} seconds")
    print(f"Status: SUCCESS")
    print(f"\nView team announcement:")
    print(f"  venv/bin/python scripts/show_latest_team.py")
    print(f"\nView draft team:")
    print(f"  SELECT * FROM draft_team WHERE for_gameweek = {gameweek};")

    return 0


if __name__ == '__main__':
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\nPre-deadline selection cancelled by user.")
        sys.exit(1)
    except Exception as e:
        logger.error(f"PreDeadline: Fatal error: {e}", exc_info=True)
        print(f"\n❌ Fatal error: {e}")
        sys.exit(1)

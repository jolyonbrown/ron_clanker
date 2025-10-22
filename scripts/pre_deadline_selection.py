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

from agents.manager import ManagerAgent
from data.database import Database
from infrastructure.event_bus import EventBus
import logging

logger = logging.getLogger('ron_clanker.pre_deadline')


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
    event_bus = EventBus()

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

    # Initialize manager
    print("\n" + "-" * 80)
    print("INITIALIZING RON CLANKER")
    print("-" * 80)

    ron = ManagerAgent(database=db)

    # Make team selection
    print("\n" + "-" * 80)
    print(f"SELECTING TEAM FOR GAMEWEEK {gameweek}")
    print("-" * 80)

    try:
        # Make weekly decision (transfers, captain, chip usage)
        transfers, chip_used, announcement = await ron.make_weekly_decision(gameweek)

        print(f"\n✓ Team selection complete!")
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

        team_stored = db.execute_query("""
            SELECT COUNT(*) as count FROM my_team
            WHERE gameweek = ?
        """, (gameweek,))

        if transfers_logged:
            print(f"✓ Transfers logged: {len(transfers_logged)} transfer(s)")
        if team_stored and team_stored[0]['count'] > 0:
            print(f"✓ Team stored: {team_stored[0]['count']} players")
        if not transfers_logged and not (team_stored and team_stored[0]['count'] > 0):
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

    duration = (datetime.now(timezone.utc) - start_time).total_seconds()

    print("\n" + "=" * 80)
    print("PRE-DEADLINE SELECTION COMPLETE")
    print("=" * 80)
    print(f"Duration: {duration:.1f} seconds")
    print(f"Status: SUCCESS")
    print(f"\nView team announcement:")
    print(f"  venv/bin/python scripts/show_latest_team.py")

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

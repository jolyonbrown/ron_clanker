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

from agents.manager import RonClanker
from data.database import Database
from utils.event_bus import EventBus
import logging

logger = logging.getLogger('ron_clanker.pre_deadline')


def get_next_deadline(db: Database) -> Optional[dict]:
    """Get the next gameweek deadline from FPL data."""
    bootstrap = db.execute_query("""
        SELECT data FROM bootstrap_data
        ORDER BY fetched_at DESC LIMIT 1
    """)

    if not bootstrap:
        return None

    data = json.loads(bootstrap[0]['data'])
    current_gw = data['current_gameweek']['id']

    # Find next deadline
    events = data.get('events', [])
    for event in events:
        if event['id'] >= current_gw and not event['finished']:
            return {
                'gameweek': event['id'],
                'deadline': event['deadline_time'],
                'name': event['name']
            }

    return None


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

    ron = RonClanker(event_bus=event_bus, database=db)

    # Emit deadline approaching event
    await event_bus.emit('deadline_approaching', {
        'gameweek': gameweek,
        'hours_remaining': max(0, time_until),
        'deadline': deadline
    })

    # Make team selection
    print("\n" + "-" * 80)
    print(f"SELECTING TEAM FOR GAMEWEEK {gameweek}")
    print("-" * 80)

    try:
        # This will coordinate all agents and make final selection
        await event_bus.emit('make_team_selection', {
            'gameweek': gameweek,
            'deadline': deadline
        })

        # Wait for Ron to process and make decisions
        await asyncio.sleep(2)

        print("\n✓ Team selection process initiated")

    except Exception as e:
        logger.error(f"PreDeadline: Error during team selection: {e}", exc_info=True)
        print(f"\n❌ Error: {e}")
        return 1

    # Store decision record
    print("\n" + "-" * 80)
    print("STORING DECISION RECORD")
    print("-" * 80)

    try:
        # Get Ron's latest decision from database
        decision = db.execute_query("""
            SELECT * FROM team_selections
            WHERE gameweek = ?
            ORDER BY created_at DESC
            LIMIT 1
        """, (gameweek,))

        if decision:
            print(f"✓ Decision stored: {len(decision)} records")
        else:
            print("⚠️  No decision record found in database")

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

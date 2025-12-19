#!/usr/bin/env python3
"""
Pre-Deadline Team Selection

Runs 6 hours before each gameweek deadline to make autonomous team selection.
Should be scheduled via cron or triggered by deadline monitoring.

Usage:
    python pre_deadline_selection.py                    # Auto-detect GW and FTs
    python pre_deadline_selection.py --gameweek 16      # Specific gameweek
    python pre_deadline_selection.py --free-transfers 5 # Override FT count
    python pre_deadline_selection.py --gameweek 16 --free-transfers 5
"""

import argparse
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
from services.free_transfer_tracker import FreeTransferTracker
from services.chip_availability import ChipAvailabilityService
from rules.rules_engine import RulesEngine
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


async def main(args):
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

    if not deadline_info and not args.gameweek:
        print("\n❌ ERROR: Cannot determine next deadline")
        print("Run: venv/bin/python scripts/collect_fpl_data.py")
        return 1

    # Use command-line gameweek if provided, otherwise auto-detect
    if args.gameweek:
        gameweek = args.gameweek
        deadline = deadline_info['deadline'] if deadline_info else "Unknown"
        name = f"Gameweek {gameweek}"
        print(f"\n⚙️  Using command-line gameweek: {gameweek}")
    else:
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

    # Fetch available free transfers from FPL API
    print("\n" + "-" * 80)
    print("FETCHING FREE TRANSFER DATA")
    print("-" * 80)

    config = load_config()
    team_id = config.get('team_id')
    ft_tracker = FreeTransferTracker()

    # Use command-line override if provided
    override_ft = args.free_transfers if args.free_transfers else None

    try:
        ft_data = ft_tracker.get_available_free_transfers(
            team_id=team_id,
            target_gw=gameweek,
            override_ft=override_ft
        )
        free_transfers = ft_data['free_transfers']
        bank = ft_data['bank']

        print(f"✓ Free Transfers: {free_transfers}")
        print(f"  Bank: £{bank:.1f}m")
        print(f"  Team Value: £{ft_data['team_value']:.1f}m")
        print(f"  Calculation: {ft_data['calculation']}")

        if ft_data.get('is_override'):
            print(f"  ⚠️  Command-line override applied (--free-transfers {override_ft})")

    except Exception as e:
        logger.error(f"PreDeadline: Error fetching FT data: {e}")
        print(f"⚠️  Could not fetch FT data: {e}")
        if override_ft:
            print(f"  Using command-line override: {override_ft} free transfers")
            free_transfers = override_ft
        else:
            print("  Defaulting to 1 free transfer")
            free_transfers = 1
        bank = 0.0

    # Fetch chip availability from FPL API
    print("\n" + "-" * 80)
    print("CHIP AVAILABILITY")
    print("-" * 80)

    chip_service = ChipAvailabilityService()
    chip_summary = None

    try:
        chip_summary = chip_service.get_chip_summary(team_id, current_gw=gameweek)

        print(f"✓ Chips loaded from API ({chip_summary['total_chips']} defined this season)")

        if chip_summary['available']:
            print(f"\n  Available ({len(chip_summary['available'])}):")
            for chip in chip_summary['available']:
                window = f"GW{chip['start_event']}-{chip['stop_event']}"
                expiry = f" [EXPIRES in {chip['gws_until_expiry']} GWs!]" if chip['expires_soon'] else ""
                print(f"    - {chip['display_name']}: {window}{expiry}")

        if chip_summary['used']:
            print(f"\n  Already Used ({len(chip_summary['used'])}):")
            for chip in chip_summary['used']:
                print(f"    - {chip['display_name']}: used in GW{chip['used_in_gw']}")

        if chip_summary['expiring_soon']:
            print(f"\n  ⚠️  EXPIRING SOON ({len(chip_summary['expiring_soon'])}):")
            for chip in chip_summary['expiring_soon']:
                print(f"    - {chip['display_name']}: {chip['gws_until_expiry']} GWs left!")
            print("     Consider using before window closes!")

        if chip_summary['expired']:
            print(f"\n  Expired/Missed ({len(chip_summary['expired'])}):")
            for chip in chip_summary['expired']:
                print(f"    - {chip['display_name']}: window was GW{chip['start_event']}-{chip['stop_event']}")

    except Exception as e:
        logger.warning(f"PreDeadline: Could not fetch chip data: {e}")
        print(f"⚠️  Could not fetch chip data: {e}")
        print("   Chip strategy will use cached data if available")

    # Initialize manager (EVENT-DRIVEN)
    print("\n" + "-" * 80)
    print("INITIALIZING RON CLANKER (Event-Driven Manager)")
    print("-" * 80)

    ron = RonManager(database=db)
    await ron.start()  # Start BaseAgent event subscriptions

    # Make team selection
    print("\n" + "-" * 80)
    print(f"SELECTING TEAM FOR GAMEWEEK {gameweek}")
    print(f"Free Transfers Available: {free_transfers}")
    print("-" * 80)

    try:
        # Make weekly decision (transfers, captain, chip usage)
        # Returns dict with keys: squad, transfers, chip_used, announcement
        result = await ron.make_weekly_decision(gameweek, free_transfers=free_transfers, bank=bank)

        transfers = result['transfers']
        chip_used = result['chip_used']
        announcement = result['announcement']
        squad = result['squad']

        print(f"\n✓ Team selection complete!")
        print(f"   Players: {len(squad)}")
        print(f"   Transfers: {len(transfers)}")
        print(f"   Chip used: {chip_used or 'None'}")

        # Validate against FPL rules
        print("\n" + "-" * 80)
        print("RULES VALIDATION")
        print("-" * 80)

        rules_engine = RulesEngine()
        validation_passed = True

        # 1. Validate squad composition
        try:
            is_valid, error = rules_engine.validate_team(squad)
            if is_valid:
                print("✓ Squad composition valid (15 players, budget, position limits)")
            else:
                validation_passed = False
                print(f"❌ Squad validation failed: {error}")
        except Exception as e:
            print(f"⚠️  Could not validate squad: {e}")

        # 2. Validate formation (starting XI)
        try:
            is_valid, error = rules_engine.validate_starting_xi(squad)
            if is_valid:
                print("✓ Formation valid")
            else:
                validation_passed = False
                print(f"❌ Formation invalid: {error}")
        except Exception as e:
            print(f"⚠️  Could not validate formation: {e}")

        # 3. Validate transfer count vs free transfers
        transfer_count = len(transfers) if transfers else 0
        if transfer_count <= free_transfers:
            print(f"✓ Transfers valid ({transfer_count} made, {free_transfers} free)")
        elif chip_used in ['wildcard', 'freehit']:
            print(f"✓ Transfers valid (unlimited due to {chip_used})")
        else:
            hits = (transfer_count - free_transfers) * 4
            print(f"⚠️  Taking {transfer_count - free_transfers} hit(s) = -{hits}pts")

        # 4. Check chip availability if used
        if chip_used and chip_summary:
            available_chips = [c['name'] for c in chip_summary.get('available', [])]
            if chip_used in available_chips:
                print(f"✓ Chip '{chip_used}' is available")
            else:
                validation_passed = False
                print(f"❌ Chip '{chip_used}' not available!")

        # 5. Check for special events (AFCON etc.)
        ft_topup = rules_engine.get_ft_topup_for_gw(gameweek)
        if ft_topup:
            print(f"ℹ️  Special event active: {ft_topup['name']}")

        if validation_passed:
            print("\n✓ All rules validation passed")
        else:
            print("\n⚠️  Some rules validation failed - review team before submitting!")

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


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description='Pre-deadline team selection for Ron Clanker',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python pre_deadline_selection.py                     # Auto-detect GW and FTs
  python pre_deadline_selection.py --gameweek 16       # Specific gameweek
  python pre_deadline_selection.py --free-transfers 5  # Override FT count (e.g., AFCON)
  python pre_deadline_selection.py -g 16 -f 5          # Short form
        """
    )
    parser.add_argument(
        '-g', '--gameweek',
        type=int,
        help='Target gameweek (default: auto-detect next GW)'
    )
    parser.add_argument(
        '-f', '--free-transfers',
        type=int,
        help='Override free transfer count (e.g., 5 for AFCON special event)'
    )
    return parser.parse_args()


if __name__ == '__main__':
    args = parse_args()
    try:
        exit_code = asyncio.run(main(args))
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\nPre-deadline selection cancelled by user.")
        sys.exit(1)
    except Exception as e:
        logger.error(f"PreDeadline: Fatal error: {e}", exc_info=True)
        print(f"\n❌ Fatal error: {e}")
        sys.exit(1)

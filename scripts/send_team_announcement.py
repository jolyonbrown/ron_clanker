#!/usr/bin/env python3
"""
Send Team Announcement to Slack

Sends Ron's team announcement AFTER the team has been confirmed on FPL website.
This should be run after Chrome submission to ensure the announcement matches
the actual submitted team.

Usage:
    python scripts/send_team_announcement.py                    # Auto-detect gameweek
    python scripts/send_team_announcement.py --gameweek 20      # Specific gameweek
    python scripts/send_team_announcement.py --dry-run          # Preview without sending
    python scripts/send_team_announcement.py --no-sync          # Skip FPL sync (use cached data)
"""

import sys
from pathlib import Path
import argparse
import logging

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from data.database import Database
from utils.config import load_config
from scripts.track_ron_team import (
    get_team_id,
    fetch_bootstrap_data,
    fetch_team_entry,
    fetch_team_picks,
    build_player_lookup,
    sync_current_team_from_fpl
)
from notifications.slack import SlackNotifier

logger = logging.getLogger('ron_clanker.announcement')

POSITION_MAP = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}


def fetch_team_from_database(gameweek: int) -> dict:
    """
    Fetch team from draft_team table (for pre-deadline announcements).

    Returns dict with same structure as fetch_confirmed_team.
    """
    db = Database()
    bootstrap = fetch_bootstrap_data()
    players, teams = build_player_lookup(bootstrap)

    # Fetch draft team
    draft = db.execute_query("""
        SELECT dt.player_id, dt.position, dt.is_captain, dt.is_vice_captain,
               CASE WHEN dt.position <= 11 THEN 1 ELSE 0 END as multiplier
        FROM draft_team dt
        WHERE dt.for_gameweek = ?
        ORDER BY dt.position
    """, (gameweek,))

    if not draft:
        return {'picks': [], 'players': players, 'teams': teams}

    # Convert to picks format
    picks = []
    for row in draft:
        picks.append({
            'element': row['player_id'],
            'position': row['position'],
            'is_captain': row['is_captain'],
            'is_vice_captain': row['is_vice_captain'],
            'multiplier': row['multiplier']
        })

    return {
        'picks': picks,
        'players': players,
        'teams': teams,
        'active_chip': None,
        'entry_history': {}
    }


def get_current_gameweek():
    """Get current gameweek from FPL API."""
    bootstrap = fetch_bootstrap_data()
    for event in bootstrap['events']:
        if event['is_current']:
            return event['id']
    # If no current GW, find next one
    for event in bootstrap['events']:
        if event['is_next']:
            return event['id']
    return None


def fetch_confirmed_team(team_id: int, gameweek: int) -> dict:
    """
    Fetch the confirmed team from FPL API.

    Returns dict with:
        - picks: List of player picks with captain/VC info
        - players: Player details lookup
        - teams: Team name lookup
    """
    bootstrap = fetch_bootstrap_data()
    players, teams = build_player_lookup(bootstrap)

    picks_data = fetch_team_picks(team_id, gameweek)

    return {
        'picks': picks_data.get('picks', []),
        'players': players,
        'teams': teams,
        'active_chip': picks_data.get('active_chip'),
        'entry_history': picks_data.get('entry_history', {})
    }


def generate_announcement(team_data: dict, gameweek: int, transfers: list = None) -> str:
    """
    Generate Ron's team announcement from confirmed team data.

    Args:
        team_data: Dict from fetch_confirmed_team
        gameweek: Gameweek number
        transfers: Optional list of transfers made

    Returns:
        Announcement text in Ron's voice
    """
    picks = team_data['picks']
    players = team_data['players']
    teams = team_data['teams']
    active_chip = team_data.get('active_chip')

    # Organize squad by position
    starting_xi = [p for p in picks if p['multiplier'] > 0]
    bench = [p for p in picks if p['multiplier'] == 0]

    # Find captain and vice-captain
    captain = next((p for p in picks if p['is_captain']), None)
    vice_captain = next((p for p in picks if p['is_vice_captain']), None)

    # Build position groups for starting XI
    positions = {'GKP': [], 'DEF': [], 'MID': [], 'FWD': []}
    for pick in starting_xi:
        player = players.get(pick['element'], {})
        pos = POSITION_MAP.get(player.get('element_type', 0), 'UNK')
        team = teams.get(player.get('team', 0), 'UNK')
        name = player.get('web_name', f"Player {pick['element']}")

        marker = ''
        if pick['is_captain']:
            marker = ' (C)'
        elif pick['is_vice_captain']:
            marker = ' (VC)'

        positions[pos].append(f"{name}{marker}")

    # Build bench list
    bench_players = []
    bench_sorted = sorted(bench, key=lambda x: x['position'])
    for pick in bench_sorted:
        player = players.get(pick['element'], {})
        name = player.get('web_name', f"Player {pick['element']}")
        bench_players.append(name)

    # Determine formation
    formation = f"{len(positions['DEF'])}-{len(positions['MID'])}-{len(positions['FWD'])}"

    # Build announcement
    lines = []
    lines.append(f"GAMEWEEK {gameweek} - RON'S CONFIRMED TEAM")
    lines.append("")

    if active_chip:
        lines.append(f"CHIP ACTIVE: {active_chip.upper()}")
        lines.append("")

    if transfers:
        lines.append("TRANSFERS:")
        for t in transfers:
            lines.append(f"  OUT: {t['out']} -> IN: {t['in']}")
        lines.append("")

    lines.append(f"FORMATION: {formation}")
    lines.append("")
    lines.append(f"GK: {', '.join(positions['GKP'])}")
    lines.append(f"DEF: {', '.join(positions['DEF'])}")
    lines.append(f"MID: {', '.join(positions['MID'])}")
    lines.append(f"FWD: {', '.join(positions['FWD'])}")
    lines.append("")
    lines.append(f"BENCH: {', '.join(bench_players)}")
    lines.append("")

    # Captain info
    if captain:
        cap_player = players.get(captain['element'], {})
        cap_name = cap_player.get('web_name', 'Unknown')
        cap_team = teams.get(cap_player.get('team', 0), 'UNK')
        lines.append(f"CAPTAIN: {cap_name} ({cap_team})")

    if vice_captain:
        vc_player = players.get(vice_captain['element'], {})
        vc_name = vc_player.get('web_name', 'Unknown')
        lines.append(f"VICE: {vc_name}")

    lines.append("")
    lines.append("Team confirmed on FPL website.")
    lines.append("")
    lines.append("- Ron Clanker")

    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Send Ron's team announcement to Slack after Chrome submission",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python send_team_announcement.py                           # Auto-detect GW, sync and send
  python send_team_announcement.py --gameweek 20            # Specific gameweek
  python send_team_announcement.py --dry-run                # Preview without sending
  python send_team_announcement.py --no-sync                # Skip FPL sync
  python send_team_announcement.py --from-database -g 20    # Pre-deadline: read from DB

Workflow:
  1. Run pre_deadline_selection.py --no-notify    # Generate draft team
  2. Submit team via Chrome                       # Confirm on FPL website
  3. After deadline: send_team_announcement.py    # Sync from FPL API and announce
  OR before deadline: --from-database             # Read from database
        """
    )
    parser.add_argument(
        '-g', '--gameweek',
        type=int,
        help='Target gameweek (default: auto-detect)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview announcement without sending to Slack'
    )
    parser.add_argument(
        '--no-sync',
        action='store_true',
        help='Skip syncing from FPL API (use cached database data)'
    )
    parser.add_argument(
        '--from-database',
        action='store_true',
        help='Read team from draft_team table (for pre-deadline announcements)'
    )

    args = parser.parse_args()

    print("\n" + "=" * 80)
    print("SEND TEAM ANNOUNCEMENT")
    print("=" * 80)

    # Get team ID
    team_id = get_team_id()
    if not team_id:
        print("\n No team ID configured. Set FPL_TEAM_ID in .env file.")
        return 1

    print(f"\nTeam ID: {team_id}")

    # Determine gameweek
    if args.gameweek:
        gameweek = args.gameweek
    else:
        try:
            entry = fetch_team_entry(team_id)
            gameweek = entry['current_event']
        except Exception as e:
            print(f" Could not auto-detect gameweek: {e}")
            return 1

    print(f"Gameweek: {gameweek}")

    # Sync from FPL API (unless --no-sync or --from-database)
    if args.from_database:
        print("\n Using database mode - skipping FPL sync")
    elif not args.no_sync:
        print("\n Syncing team from FPL API...")
        success = sync_current_team_from_fpl(team_id, gameweek, verbose=True)
        if not success:
            print(" Sync failed! Use --no-sync to skip or --from-database for pre-deadline.")
            return 1
    else:
        print("\n Skipping FPL sync (using cached data)")

    # Fetch team data
    if args.from_database:
        print("\n Fetching team from database (draft_team)...")
        try:
            team_data = fetch_team_from_database(gameweek)
        except Exception as e:
            print(f" Failed to fetch from database: {e}")
            return 1
    else:
        print("\n Fetching confirmed team from FPL API...")
        try:
            team_data = fetch_confirmed_team(team_id, gameweek)
        except Exception as e:
            print(f" Failed to fetch team: {e}")
            print("   TIP: If before deadline, use --from-database flag")
            return 1

    if not team_data['picks']:
        print(f" No picks found for GW{gameweek}")
        return 1

    print(f" Found {len(team_data['picks'])} players")

    # Generate announcement
    print("\n Generating announcement...")
    announcement = generate_announcement(team_data, gameweek)

    print("\n" + "-" * 80)
    print("ANNOUNCEMENT PREVIEW")
    print("-" * 80)
    print(announcement)
    print("-" * 80)

    # Send to Slack (unless --dry-run)
    if args.dry_run:
        print("\n DRY RUN - Not sending to Slack")
        print("   Remove --dry-run flag to send")
    else:
        print("\n Sending to Slack...")
        notifier = SlackNotifier()

        if not notifier.enabled:
            print(" Slack not configured. Set SLACK_WEBHOOK_URL environment variable.")
            return 1

        success = notifier.send_team_announcement(announcement, gameweek)

        if success:
            print(" Slack notification sent successfully!")
        else:
            print(" Failed to send Slack notification")
            return 1

    print("\n" + "=" * 80)
    print(" ANNOUNCEMENT COMPLETE")
    print("=" * 80)

    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\nCancelled.")
        sys.exit(1)
    except Exception as e:
        print(f"\n Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

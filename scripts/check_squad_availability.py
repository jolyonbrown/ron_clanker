#!/usr/bin/env python3
"""
Squad Availability Checker

Checks the current squad against FPL API to identify:
- Injured players (status = 'i')
- Suspended players (status = 's')
- Unavailable players (status = 'u' - loans, etc.)
- Doubtful players (status = 'd')
- Chance of playing percentages

Usage:
    python scripts/check_squad_availability.py --squad gw8
    python scripts/check_squad_availability.py --squad gw8 --verbose
"""

import sys
from pathlib import Path
import argparse
import json
import requests
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

FPL_BASE_URL = "https://fantasy.premierleague.com/api"
POSITION_MAP = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}
STATUS_MAP = {
    'a': '✅ Available',
    'd': '⚠️  Doubtful',
    'i': '🚑 Injured',
    's': '🟥 Suspended',
    'u': '❌ Unavailable',
    'n': '❓ Not in squad'
}


def fetch_bootstrap_data():
    """Fetch FPL bootstrap data"""
    response = requests.get(f"{FPL_BASE_URL}/bootstrap-static/")
    response.raise_for_status()
    return response.json()


def load_squad(squad_file):
    """Load squad from JSON file"""
    squad_path = project_root / 'data' / 'squads' / f'{squad_file}_squad.json'
    if not squad_path.exists():
        raise FileNotFoundError(f"Squad file not found: {squad_path}")

    with open(squad_path, 'r') as f:
        return json.load(f)


def find_player_by_id(player_id, bootstrap_data):
    """Find player in bootstrap data by ID"""
    for player in bootstrap_data['elements']:
        if player['id'] == player_id:
            return player
    return None


def check_availability(squad_data, bootstrap_data, verbose=False):
    """Check squad availability against FPL API"""

    teams = {t['id']: t['short_name'] for t in bootstrap_data['teams']}

    print("\n" + "=" * 80)
    print("SQUAD AVAILABILITY CHECK")
    print("=" * 80)
    print(f"Gameweek: {squad_data.get('gameweek', 'Unknown')}")
    print(f"Generated: {squad_data.get('generated', 'Unknown')}")
    print(f"Check time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    issues = []
    all_clear = True

    # Flatten squad structure (GKP, DEF, MID, FWD)
    all_players = []
    squad = squad_data.get('squad', {})
    for position_group in ['goalkeepers', 'defenders', 'midfielders', 'forwards']:
        if position_group in squad:
            for player in squad[position_group]:
                all_players.append(player)

    for player in all_players:
        fpl_player = find_player_by_id(player['id'], bootstrap_data)

        if not fpl_player:
            print(f"\n⚠️  WARNING: Could not find {player['name']} (ID: {player['id']}) in FPL data")
            continue

        # Get team name
        team_name = teams.get(fpl_player['team'], 'UNK')
        position = POSITION_MAP.get(fpl_player['element_type'], 'UNK')

        status = fpl_player['status']
        news = fpl_player.get('news', '')
        chance_this = fpl_player.get('chance_of_playing_this_round')
        chance_next = fpl_player.get('chance_of_playing_next_round')

        # Check for any flags
        is_flagged = (
            status != 'a' or
            news != '' or
            chance_this is not None or
            chance_next is not None
        )

        if is_flagged or verbose:
            print(f"\n{player['name']:20s} ({team_name}) - £{player['price']:.1f}m")
            print(f"  Position: {position}")
            print(f"  Status: {STATUS_MAP.get(status, status)}")

            if news:
                print(f"  News: {news}")

            if chance_this is not None:
                print(f"  Chance this round: {chance_this}%")

            if chance_next is not None:
                print(f"  Chance next round: {chance_next}%")

            if is_flagged:
                all_clear = False
                issues.append({
                    'player': player['name'],
                    'team': team_name,
                    'position': position,
                    'status': status,
                    'news': news,
                    'chance_this_round': chance_this,
                    'chance_next_round': chance_next
                })

    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)

    if all_clear:
        print("\n✅ ALL PLAYERS AVAILABLE - No flags or concerns")
    else:
        print(f"\n⚠️  {len(issues)} PLAYER(S) FLAGGED\n")

        for issue in issues:
            severity = {
                'i': '🚑 INJURED',
                's': '🟥 SUSPENDED',
                'u': '❌ UNAVAILABLE',
                'd': '⚠️  DOUBTFUL',
                'a': '⚠️  FITNESS CONCERN'
            }.get(issue['status'], '❓ UNKNOWN')

            print(f"{severity}: {issue['player']} ({issue['team']}) - {issue['position']}")
            if issue['news']:
                print(f"         {issue['news']}")

        print(f"\n📋 RECOMMENDATION: Review flagged players before finalizing team")

    print("\n" + "=" * 80)

    return issues


def main():
    parser = argparse.ArgumentParser(description='Check squad player availability')
    parser.add_argument('--squad', default='gw8',
                       help='Squad file to check (default: gw8)')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Show all players, not just flagged ones')

    args = parser.parse_args()

    try:
        print("Fetching latest FPL data...")
        bootstrap_data = fetch_bootstrap_data()

        print(f"Loading squad file: {args.squad}...")
        squad_data = load_squad(args.squad)

        issues = check_availability(squad_data, bootstrap_data, args.verbose)

        # Exit code: 0 if all clear, 1 if issues found
        sys.exit(1 if issues else 0)

    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(2)


if __name__ == '__main__':
    main()

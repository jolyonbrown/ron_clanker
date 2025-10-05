#!/usr/bin/env python3
"""
Explore FPL Team API endpoints

Tests what data is available for a given team ID.
This will be used to track Ron's team performance once registered.

Usage:
    python scripts/explore_team_api.py --team-id 9204022
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


def explore_team_entry(team_id):
    """Explore /entry/{team_id}/ endpoint"""
    print("\n" + "=" * 80)
    print(f"TEAM ENTRY ENDPOINT: /entry/{team_id}/")
    print("=" * 80)

    try:
        url = f"{FPL_BASE_URL}/entry/{team_id}/"
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()

        print("\n📋 TEAM INFORMATION:")
        print("-" * 80)

        # Key fields
        interesting_fields = [
            'id', 'player_first_name', 'player_last_name', 'name',
            'started_event', 'summary_overall_points', 'summary_overall_rank',
            'summary_event_points', 'summary_event_rank', 'current_event',
            'total_transfers', 'bank', 'value', 'favourite_team',
            'last_deadline_bank', 'last_deadline_value', 'last_deadline_total_transfers'
        ]

        for field in interesting_fields:
            if field in data:
                print(f"  {field:30s} = {data[field]}")

        # Save full response
        output_file = project_root / 'data' / 'api_exploration' / f'team_{team_id}_entry.json'
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, 'w') as f:
            json.dump(data, f, indent=2)
        print(f"\n💾 Full data saved to: {output_file}")

        return data

    except requests.exceptions.HTTPError as e:
        print(f"\n❌ Error: {e}")
        return None


def explore_team_picks(team_id, gameweek):
    """Explore /entry/{team_id}/event/{gw}/picks/ endpoint"""
    print("\n" + "=" * 80)
    print(f"TEAM PICKS ENDPOINT: /entry/{team_id}/event/{gameweek}/picks/")
    print("=" * 80)

    try:
        url = f"{FPL_BASE_URL}/entry/{team_id}/event/{gameweek}/picks/"
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()

        print("\n📋 GAMEWEEK PICKS:")
        print("-" * 80)

        # Entry history for this GW
        if 'entry_history' in data:
            print("\nGAMEWEEK SUMMARY:")
            history = data['entry_history']
            for key, value in history.items():
                print(f"  {key:30s} = {value}")

        # Active chip
        if 'active_chip' in data:
            print(f"\nActive Chip: {data['active_chip'] or 'None'}")

        # Picks
        if 'picks' in data:
            print(f"\nSQUAD ({len(data['picks'])} players):")
            for pick in data['picks']:
                position = pick['position']
                is_captain = ' (C)' if pick['is_captain'] else ''
                is_vice = ' (VC)' if pick['is_vice_captain'] else ''
                multiplier = f"x{pick['multiplier']}"
                print(f"  Pos {position:2d}: Player {pick['element']:3d}{is_captain}{is_vice} {multiplier}")

        # Automatic subs
        if 'automatic_subs' in data:
            if data['automatic_subs']:
                print("\nAUTOMATIC SUBSTITUTIONS:")
                for sub in data['automatic_subs']:
                    print(f"  OUT: Player {sub['element_out']} -> IN: Player {sub['element_in']}")
            else:
                print("\nNo automatic substitutions")

        # Save full response
        output_file = project_root / 'data' / 'api_exploration' / f'team_{team_id}_gw{gameweek}_picks.json'
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, 'w') as f:
            json.dump(data, f, indent=2)
        print(f"\n💾 Full data saved to: {output_file}")

        return data

    except requests.exceptions.HTTPError as e:
        print(f"\n❌ Error: {e}")
        if e.response.status_code == 404:
            print(f"   Team may not have entered GW{gameweek} yet")
        return None


def explore_team_history(team_id):
    """Explore /entry/{team_id}/history/ endpoint"""
    print("\n" + "=" * 80)
    print(f"TEAM HISTORY ENDPOINT: /entry/{team_id}/history/")
    print("=" * 80)

    try:
        url = f"{FPL_BASE_URL}/entry/{team_id}/history/"
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()

        print("\n📋 SEASON HISTORY:")
        print("-" * 80)

        # Current season gameweeks
        if 'current' in data and data['current']:
            print(f"\nCURRENT SEASON ({len(data['current'])} gameweeks):")
            print(f"{'GW':4s} {'Pts':5s} {'Tot':6s} {'Rank':10s} {'Bank':7s} {'Value':8s} {'Transfers':10s}")
            print("-" * 80)
            for gw in data['current'][:10]:  # Show first 10
                print(f"{gw['event']:4d} "
                      f"{gw['points']:5d} "
                      f"{gw['total_points']:6d} "
                      f"{gw['overall_rank']:10d} "
                      f"£{gw['bank']/10:.1f}m  "
                      f"£{gw['value']/10:.1f}m  "
                      f"{gw['event_transfers']:2d} ({gw['event_transfers_cost']:+d})")

            if len(data['current']) > 10:
                print(f"... and {len(data['current']) - 10} more gameweeks")

        # Chips used
        if 'chips' in data:
            print("\nCHIPS USED:")
            if data['chips']:
                for chip in data['chips']:
                    print(f"  GW{chip['event']:2d}: {chip['name']}")
            else:
                print("  None used yet")

        # Past seasons
        if 'past' in data and data['past']:
            print(f"\nPAST SEASONS ({len(data['past'])} seasons):")
            for season in data['past']:
                print(f"  {season['season_name']}: {season['total_points']} pts, Rank {season['rank']}")

        # Save full response
        output_file = project_root / 'data' / 'api_exploration' / f'team_{team_id}_history.json'
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, 'w') as f:
            json.dump(data, f, indent=2)
        print(f"\n💾 Full data saved to: {output_file}")

        return data

    except requests.exceptions.HTTPError as e:
        print(f"\n❌ Error: {e}")
        return None


def explore_team_transfers(team_id):
    """Explore /entry/{team_id}/transfers/ endpoint"""
    print("\n" + "=" * 80)
    print(f"TEAM TRANSFERS ENDPOINT: /entry/{team_id}/transfers/")
    print("=" * 80)

    try:
        url = f"{FPL_BASE_URL}/entry/{team_id}/transfers/"
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()

        print("\n📋 TRANSFER HISTORY:")
        print("-" * 80)

        if data:
            print(f"\nTotal transfers: {len(data)}")

            # Show first transfer to see structure
            if data:
                print("\nFirst transfer structure:")
                for key, value in data[0].items():
                    print(f"  {key}: {value}")

            print(f"\n{'GW':4s} {'OUT':10s} {'IN':10s} {'Cost':6s}")
            print("-" * 80)
            for transfer in data[:20]:  # Show first 20
                cost = transfer.get('entry_cost', transfer.get('event_cost', 0))
                print(f"{transfer['event']:4d} "
                      f"Player {transfer['element_out']:3d} -> "
                      f"Player {transfer['element_in']:3d}  "
                      f"{cost:3d} pts")

            if len(data) > 20:
                print(f"... and {len(data) - 20} more transfers")
        else:
            print("\nNo transfers made yet")

        # Save full response
        output_file = project_root / 'data' / 'api_exploration' / f'team_{team_id}_transfers.json'
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, 'w') as f:
            json.dump(data, f, indent=2)
        print(f"\n💾 Full data saved to: {output_file}")

        return data

    except requests.exceptions.HTTPError as e:
        print(f"\n❌ Error: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(description='Explore FPL Team API endpoints')
    parser.add_argument('--team-id', type=int, required=True,
                       help='FPL Team ID to explore')
    parser.add_argument('--gameweek', type=int, default=7,
                       help='Gameweek to check picks for (default: 7)')

    args = parser.parse_args()

    print("\n" + "=" * 80)
    print("FPL TEAM API EXPLORER")
    print("=" * 80)
    print(f"Team ID: {args.team_id}")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    # Test all endpoints
    entry_data = explore_team_entry(args.team_id)

    if entry_data:
        # Get current gameweek from entry data
        current_gw = entry_data.get('current_event', args.gameweek)

        history_data = explore_team_history(args.team_id)
        picks_data = explore_team_picks(args.team_id, current_gw)
        transfers_data = explore_team_transfers(args.team_id)

    print("\n" + "=" * 80)
    print("EXPLORATION COMPLETE")
    print("=" * 80)
    print("\n✅ All API endpoints tested")
    print(f"📁 Data saved to: {project_root / 'data' / 'api_exploration'}/")
    print("\nThese endpoints will be used to track Ron's team once registered.")


if __name__ == '__main__':
    main()

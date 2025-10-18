#!/usr/bin/env python3
"""
Ron Clanker's Team Performance Tracker

Fetches Ron's actual FPL team data and provides comprehensive analysis.
Uses team ID from config or command line.

Usage:
    python scripts/track_ron_team.py
    python scripts/track_ron_team.py --team-id 123456
    python scripts/track_ron_team.py --gameweek 8
    python scripts/track_ron_team.py --verbose
"""

import sys
from pathlib import Path
import argparse
import json
import requests
from datetime import datetime
from collections import defaultdict

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utils.config import load_config

FPL_BASE_URL = "https://fantasy.premierleague.com/api"
POSITION_MAP = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}


def get_team_id(args_team_id=None):
    """Get team ID from args, config, or prompt"""
    if args_team_id:
        return args_team_id

    config = load_config()
    if 'team_id' in config and config['team_id']:
        return config['team_id']

    print("\n⚠️  No team ID configured for Ron Clanker")
    print("Once Ron's team is registered, add to .env file:")
    print('FPL_TEAM_ID=123456\n')
    print("(Do NOT add to ron_config.json - keep sensitive data in .env)")
    return None


def fetch_bootstrap_data():
    """Fetch FPL bootstrap data (players, teams, gameweeks)"""
    response = requests.get(f"{FPL_BASE_URL}/bootstrap-static/")
    response.raise_for_status()
    return response.json()


def fetch_team_entry(team_id):
    """Fetch team overview"""
    response = requests.get(f"{FPL_BASE_URL}/entry/{team_id}/")
    response.raise_for_status()
    return response.json()


def fetch_team_history(team_id):
    """Fetch team season history"""
    response = requests.get(f"{FPL_BASE_URL}/entry/{team_id}/history/")
    response.raise_for_status()
    return response.json()


def fetch_team_picks(team_id, gameweek):
    """Fetch team picks for specific gameweek"""
    response = requests.get(f"{FPL_BASE_URL}/entry/{team_id}/event/{gameweek}/picks/")
    response.raise_for_status()
    return response.json()


def fetch_team_transfers(team_id):
    """Fetch all team transfers"""
    response = requests.get(f"{FPL_BASE_URL}/entry/{team_id}/transfers/")
    response.raise_for_status()
    return response.json()


def fetch_player_history(player_id):
    """Fetch individual player's gameweek history"""
    response = requests.get(f"{FPL_BASE_URL}/element-summary/{player_id}/")
    response.raise_for_status()
    return response.json()


def build_player_lookup(bootstrap):
    """Build lookup tables for players and teams"""
    players = {p['id']: p for p in bootstrap['elements']}
    teams = {t['id']: t['short_name'] for t in bootstrap['teams']}
    return players, teams


def display_team_overview(entry_data, history_data, bootstrap):
    """Display Ron's team overview"""
    players, teams = build_player_lookup(bootstrap)

    print("\n" + "=" * 80)
    print("RON CLANKER'S TEAM OVERVIEW")
    print("=" * 80)
    print(f"Team Name: {entry_data['name']}")
    print(f"Manager: {entry_data['player_first_name']} {entry_data['player_last_name']}")
    print(f"Started: GW{entry_data['started_event']}")
    print(f"Current Gameweek: GW{entry_data['current_event']}")
    print("=" * 80)

    print("\n📊 CURRENT SEASON PERFORMANCE:")
    print("-" * 80)
    print(f"Overall Points: {entry_data['summary_overall_points']}")
    print(f"Overall Rank: {entry_data['summary_overall_rank']:,}")
    print(f"Latest GW Points: {entry_data['summary_event_points']}")
    print(f"Latest GW Rank: {entry_data['summary_event_rank']:,}")
    print()
    print(f"Team Value: £{entry_data['last_deadline_value'] / 10:.1f}m")
    print(f"In The Bank: £{entry_data['last_deadline_bank'] / 10:.1f}m")
    print(f"Total Transfers: {entry_data['last_deadline_total_transfers']}")

    # Chips used
    chips_used = history_data.get('chips', [])
    print(f"\n🎴 CHIPS USED: {len(chips_used)}/8")
    if chips_used:
        for chip in chips_used:
            print(f"  - GW{chip['event']}: {chip['name']}")
    else:
        print("  - None used yet (all 8 chips available)")


def display_gameweek_history(history_data, num_gws=10):
    """Display recent gameweek history"""
    print("\n" + "=" * 80)
    print(f"GAMEWEEK HISTORY (Last {num_gws} gameweeks)")
    print("=" * 80)

    current = history_data['current']
    recent = current[-num_gws:] if len(current) > num_gws else current

    print(f"{'GW':4s} {'Pts':5s} {'Total':7s} {'OR':12s} {'GWR':12s} "
          f"{'Bank':7s} {'Value':8s} {'Trans':6s} {'Bench':6s}")
    print("-" * 80)

    for gw in recent:
        print(f"{gw['event']:4d} "
              f"{gw['points']:5d} "
              f"{gw['total_points']:7d} "
              f"{gw['overall_rank']:12,d} "
              f"{gw['rank']:12,d} "
              f"£{gw['bank']/10:5.1f}m "
              f"£{gw['value']/10:6.1f}m "
              f"{gw['event_transfers']:2d}({gw['event_transfers_cost']:+d}) "
              f"{gw['points_on_bench']:3d}")


def display_gameweek_squad(picks_data, bootstrap, gameweek, verbose=False):
    """Display squad for specific gameweek with player details"""
    players, teams = build_player_lookup(bootstrap)

    print("\n" + "=" * 80)
    print(f"GAMEWEEK {gameweek} SQUAD")
    print("=" * 80)

    # Gameweek summary
    entry_history = picks_data.get('entry_history', {})
    print(f"\n📊 Gameweek Summary:")
    print(f"  Points: {entry_history.get('points', 'N/A')}")
    print(f"  Gameweek Rank: {entry_history.get('rank', 'N/A'):,}")
    print(f"  Overall Rank: {entry_history.get('overall_rank', 'N/A'):,}")
    print(f"  Points on Bench: {entry_history.get('points_on_bench', 'N/A')}")
    print(f"  Transfers: {entry_history.get('event_transfers', 0)} "
          f"(Cost: {entry_history.get('event_transfers_cost', 0)} pts)")

    active_chip = picks_data.get('active_chip')
    if active_chip:
        print(f"  🎴 Active Chip: {active_chip}")

    # Squad
    picks = picks_data.get('picks', [])

    print(f"\n🔢 SQUAD ({len(picks)} players):")
    print("-" * 80)
    print(f"{'Pos':4s} {'Player':20s} {'Team':5s} {'Price':7s} {'Role':8s} {'Mult':5s}")
    print("-" * 80)

    total_value = 0

    for pick in picks:
        player_id = pick['element']
        player = players.get(player_id)

        if player:
            name = player['web_name']
            team = teams.get(player['team'], 'UNK')
            position = POSITION_MAP.get(player['element_type'], 'UNK')
            price = player['now_cost'] / 10

            role_parts = []
            if pick['is_captain']:
                role_parts.append('(C)')
            if pick['is_vice_captain']:
                role_parts.append('(VC)')
            role = ' '.join(role_parts) if role_parts else ''

            mult = f"x{pick['multiplier']}"
            status = '🟢' if pick['multiplier'] > 0 else '⚪'

            print(f"{status} {pick['position']:2d}  "
                  f"{name:20s} {team:5s} £{price:5.1f}m "
                  f"{role:8s} {mult:5s}")

            total_value += price
        else:
            print(f"  {pick['position']:2d}  Player {player_id} (not found in bootstrap)")

    print("-" * 80)
    print(f"Total Squad Value: £{total_value:.1f}m")

    # Automatic substitutions
    auto_subs = picks_data.get('automatic_subs', [])
    if auto_subs:
        print("\n🔄 AUTOMATIC SUBSTITUTIONS:")
        for sub in auto_subs:
            player_out = players.get(sub['element_out'], {})
            player_in = players.get(sub['element_in'], {})
            print(f"  OUT: {player_out.get('web_name', f'Player {sub["element_out"]}')} -> "
                  f"IN: {player_in.get('web_name', f'Player {sub["element_in"]}')} "
                  f"({sub['event']} mins)")


def display_detailed_player_performance(picks_data, bootstrap, gameweek, verbose=False):
    """Display detailed player-by-player performance for the gameweek"""
    players, teams = build_player_lookup(bootstrap)

    print("\n" + "=" * 80)
    print(f"DETAILED PLAYER PERFORMANCE - GW{gameweek}")
    print("=" * 80)

    picks = picks_data.get('picks', [])

    print(f"\n{'Player':20s} {'Team':5s} {'Mins':5s} {'Pts':5s} "
          f"{'G':3s} {'A':3s} {'DC':4s} {'Bonus':6s}")
    print("-" * 80)

    total_points = 0

    for pick in picks:
        player_id = pick['element']
        player = players.get(player_id)

        if not player:
            continue

        # Only fetch detailed history if verbose or player is in starting XI
        if verbose or pick['multiplier'] > 0:
            try:
                player_history = fetch_player_history(player_id)
                gw_data = next((h for h in player_history['history']
                              if h['round'] == gameweek), None)

                if gw_data:
                    name = player['web_name']
                    team = teams.get(player['team'], 'UNK')
                    mins = gw_data['minutes']
                    pts = gw_data['total_points'] * pick['multiplier']
                    goals = gw_data['goals_scored']
                    assists = gw_data['assists']
                    dc = gw_data.get('defensive_contribution', 0)
                    bonus = gw_data['bonus']

                    role = ''
                    if pick['is_captain']:
                        role = '(C)'
                    elif pick['is_vice_captain']:
                        role = '(VC)'
                    elif pick['multiplier'] == 0:
                        role = '(B)'

                    print(f"{name:20s} {team:5s} {mins:5d} "
                          f"{pts:5d} {goals:3d} {assists:3d} "
                          f"{dc:4d} {bonus:6d} {role}")

                    total_points += pts

            except Exception as e:
                if verbose:
                    print(f"{player['web_name']:20s} - Error fetching data: {e}")

    print("-" * 80)
    print(f"Total Points: {total_points}")


def display_recent_transfers(transfers_data, bootstrap, num_transfers=10):
    """Display recent transfers"""
    players, teams = build_player_lookup(bootstrap)

    print("\n" + "=" * 80)
    print(f"RECENT TRANSFERS (Last {num_transfers})")
    print("=" * 80)

    if not transfers_data:
        print("\nNo transfers made yet")
        return

    recent = transfers_data[:num_transfers] if len(transfers_data) > num_transfers else transfers_data

    print(f"\n{'GW':4s} {'OUT':25s} {'IN':25s} {'Cost':6s}")
    print("-" * 80)

    for transfer in recent:
        player_out = players.get(transfer['element_out'])
        player_in = players.get(transfer['element_in'])

        out_name = player_out['web_name'] if player_out else f"Player {transfer['element_out']}"
        in_name = player_in['web_name'] if player_in else f"Player {transfer['element_in']}"

        out_team = teams.get(player_out['team']) if player_out else '?'
        in_team = teams.get(player_in['team']) if player_in else '?'

        # Cost is in entry_history for the GW, not in transfer data
        # Transfer data doesn't include cost directly, need to look at GW history
        print(f"GW{transfer['event']:2d} {out_name} ({out_team}):25s -> "
              f"{in_name} ({in_team}):25s")

    print(f"\nTotal transfers this season: {len(transfers_data)}")


def main():
    parser = argparse.ArgumentParser(description="Track Ron Clanker's FPL team performance")
    parser.add_argument('--team-id', type=int,
                       help='FPL Team ID (overrides config)')
    parser.add_argument('--gameweek', '-gw', type=int,
                       help='Specific gameweek to analyze (default: current)')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Show detailed player-by-player performance')
    parser.add_argument('--save', action='store_true',
                       help='Save tracking data to file')

    args = parser.parse_args()

    # Get team ID
    team_id = get_team_id(args.team_id)
    if not team_id:
        print("\n❌ No team ID available. Ron's team not yet registered.")
        print("\nTo configure Ron's team ID:")
        print("1. Register Ron's team on FPL website")
        print("2. Get the team ID from the URL: fantasy.premierleague.com/entry/{TEAM_ID}/event/X")
        print("3. Add to .env file (do NOT use ron_config.json for sensitive data):")
        print('   FPL_TEAM_ID=YOUR_TEAM_ID')
        print("\nOr use: python scripts/track_ron_team.py --team-id YOUR_TEAM_ID")
        sys.exit(1)

    try:
        print(f"\n🔍 Fetching Ron's team data (ID: {team_id})...")

        # Fetch all data
        bootstrap = fetch_bootstrap_data()
        entry = fetch_team_entry(team_id)
        history = fetch_team_history(team_id)
        transfers = fetch_team_transfers(team_id)

        # Determine gameweek
        gameweek = args.gameweek or entry['current_event']

        # Fetch gameweek picks
        try:
            picks = fetch_team_picks(team_id, gameweek)
        except requests.exceptions.HTTPError:
            picks = None
            print(f"⚠️  No picks data available for GW{gameweek}")

        # Display overview
        display_team_overview(entry, history, bootstrap)
        display_gameweek_history(history)

        if picks:
            display_gameweek_squad(picks, bootstrap, gameweek, args.verbose)

            if args.verbose:
                print("\n⏳ Fetching detailed player performance (this may take a moment)...")
                display_detailed_player_performance(picks, bootstrap, gameweek, args.verbose)

        display_recent_transfers(transfers, bootstrap)

        # Save data if requested
        if args.save:
            output_dir = project_root / 'data' / 'ron_tracking'
            output_dir.mkdir(parents=True, exist_ok=True)

            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_file = output_dir / f'ron_team_gw{gameweek}_{timestamp}.json'

            tracking_data = {
                'team_id': team_id,
                'gameweek': gameweek,
                'timestamp': timestamp,
                'entry': entry,
                'history': history,
                'picks': picks,
                'transfers': transfers
            }

            with open(output_file, 'w') as f:
                json.dump(tracking_data, f, indent=2)

            print(f"\n💾 Tracking data saved to: {output_file}")

        print("\n" + "=" * 80)
        print("✅ TRACKING COMPLETE")
        print("=" * 80)

    except requests.exceptions.HTTPError as e:
        print(f"\n❌ Error fetching team data: {e}")
        if e.response.status_code == 404:
            print(f"   Team ID {team_id} not found. Check the ID is correct.")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()

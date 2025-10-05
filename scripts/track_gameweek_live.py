#!/usr/bin/env python3
"""
Live Gameweek Tracker for Ron Clanker's Team

Monitors live scores during a gameweek and calculates points as they happen.
Tracks Ron's squad performance in real-time.

Usage:
    python scripts/track_gameweek_live.py --gw 8
    python scripts/track_gameweek_live.py --gw 8 --watch  # Auto-refresh mode
"""

import sys
import os
from pathlib import Path
import time
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import argparse
import json
import requests
from typing import Dict, List, Optional
from collections import defaultdict

# FPL API
FPL_BASE_URL = "https://fantasy.premierleague.com/api"


def load_squad(gameweek: int) -> Dict:
    """Load Ron's squad for the specified gameweek."""
    squad_file = f"data/squads/gw{gameweek}_squad.json"

    if not os.path.exists(squad_file):
        print(f"❌ Squad file not found: {squad_file}")
        sys.exit(1)

    with open(squad_file) as f:
        return json.load(f)


def fetch_live_gameweek(gameweek: int) -> Dict:
    """Fetch live gameweek data from FPL API."""
    url = f"{FPL_BASE_URL}/event/{gameweek}/live/"
    response = requests.get(url)
    response.raise_for_status()
    return response.json()


def fetch_fixtures(gameweek: int) -> List[Dict]:
    """Fetch fixtures for the gameweek."""
    url = f"{FPL_BASE_URL}/fixtures/?event={gameweek}"
    response = requests.get(url)
    response.raise_for_status()
    return response.json()


def fetch_bootstrap() -> Dict:
    """Fetch bootstrap data for player/team info."""
    response = requests.get(f"{FPL_BASE_URL}/bootstrap-static/")
    response.raise_for_status()
    return response.json()


def calculate_player_points(player_id: int, live_data: Dict, bootstrap: Dict) -> Dict:
    """
    Calculate points for a player from live data.

    Returns:
        Dict with points breakdown
    """
    # Find player in live data
    player_live = next((p for p in live_data['elements'] if p['id'] == player_id), None)

    if not player_live:
        return {
            'points': 0,
            'played': False,
            'breakdown': {}
        }

    stats = player_live.get('stats', {})

    # Get player info for position
    player_info = next((p for p in bootstrap['elements'] if p['id'] == player_id), {})
    position = player_info.get('element_type', 0)

    breakdown = {
        'minutes': stats.get('minutes', 0),
        'goals_scored': stats.get('goals_scored', 0),
        'assists': stats.get('assists', 0),
        'clean_sheets': stats.get('clean_sheets', 0),
        'goals_conceded': stats.get('goals_conceded', 0),
        'saves': stats.get('saves', 0),
        'bonus': stats.get('bonus', 0),
        'defensive_contribution': stats.get('defensive_contribution', 0),
        'yellow_cards': stats.get('yellow_cards', 0),
        'red_cards': stats.get('red_cards', 0),
        'own_goals': stats.get('own_goals', 0),
        'penalties_missed': stats.get('penalties_missed', 0),
        'penalties_saved': stats.get('penalties_saved', 0),
    }

    total_points = stats.get('total_points', 0)

    return {
        'points': total_points,
        'played': stats.get('minutes', 0) > 0,
        'breakdown': breakdown,
        'explain': player_live.get('explain', [])
    }


def get_fixture_status(fixtures: List[Dict], player_team_id: int) -> str:
    """Get fixture status for a team."""
    fixture = next((f for f in fixtures
                   if f['team_h'] == player_team_id or f['team_a'] == player_team_id), None)

    if not fixture:
        return "No fixture"

    if fixture['finished']:
        return "Finished"
    elif fixture['started']:
        return f"Live ({fixture.get('minutes', 0)}')"
    else:
        # Get kickoff time
        kickoff = fixture.get('kickoff_time', '')
        if kickoff:
            ko_time = datetime.fromisoformat(kickoff.replace('Z', '+00:00'))
            return f"Kicks off {ko_time.strftime('%H:%M')}"
        return "Not started"


def calculate_team_points(squad: Dict, live_data: Dict, bootstrap: Dict, fixtures: List[Dict]) -> Dict:
    """Calculate total points for Ron's team."""

    team_map = {t['id']: t['short_name'] for t in bootstrap['teams']}
    player_map = {p['id']: p for p in bootstrap['elements']}

    # Get captain and vice
    captain_id = squad['captain']['id']
    vice_id = squad['vice_captain']['id']

    results = {
        'starting_xi': [],
        'bench': [],
        'total_points': 0,
        'captain_points': 0,
        'auto_subs': []
    }

    # Process all players
    all_players = []

    # Starting XI (positions 1-11)
    for pos_group in ['goalkeepers', 'defenders', 'midfielders', 'forwards']:
        for player in squad['squad'][pos_group]:
            player_info = player_map.get(player['id'])
            if not player_info:
                continue

            points_data = calculate_player_points(player['id'], live_data, bootstrap)
            fixture_status = get_fixture_status(fixtures, player_info['team'])

            is_captain = player['id'] == captain_id
            is_vice = player['id'] == vice_id

            player_result = {
                'id': player['id'],
                'name': player['name'],
                'team': team_map.get(player_info['team'], 'Unknown'),
                'position': pos_group[:3].upper(),
                'points': points_data['points'],
                'played': points_data['played'],
                'breakdown': points_data['breakdown'],
                'fixture_status': fixture_status,
                'is_captain': is_captain,
                'is_vice': is_vice,
                'multiplier': 2 if is_captain else 1
            }

            all_players.append(player_result)

    # Sort into starting XI and bench (first 11 = starting, rest = bench based on squad file order)
    # For now, assume squad JSON has correct ordering
    # TODO: Implement auto-sub logic

    starting_xi = all_players[:11]
    bench = all_players[11:]

    # Calculate points
    total = 0
    captain_contribution = 0

    for player in starting_xi:
        player_pts = player['points']

        if player['is_captain']:
            # Captain gets double points
            total += player_pts * 2
            captain_contribution = player_pts * 2
            player['points_earned'] = player_pts * 2
        else:
            total += player_pts
            player['points_earned'] = player_pts

    results['starting_xi'] = starting_xi
    results['bench'] = bench
    results['total_points'] = total
    results['captain_points'] = captain_contribution

    return results


def display_live_tracker(results: Dict, gameweek: int):
    """Display live tracking in terminal."""

    print("\n" + "=" * 80)
    print(f"🔴 LIVE GAMEWEEK {gameweek} TRACKER - TWO POINTS FC")
    print(f"⏰ Updated: {datetime.now().strftime('%H:%M:%S')}")
    print("=" * 80)

    # Current total
    total = results['total_points']
    print(f"\n📊 CURRENT TOTAL: {total} points")
    print(f"⭐ Captain contribution: {results['captain_points']} points")

    # Starting XI
    print(f"\n{'=' * 80}")
    print("STARTING XI")
    print(f"{'=' * 80}\n")

    print(f"{'Player':<20} {'Team':<6} {'Pos':<5} {'Status':<15} {'Pts':<5} {'Details'}")
    print("-" * 80)

    for player in results['starting_xi']:
        captain_marker = "(C)" if player['is_captain'] else "(VC)" if player['is_vice'] else ""
        name_display = f"{player['name'][:17]} {captain_marker}"

        # Build details string
        details = []
        b = player['breakdown']
        if b['goals_scored'] > 0:
            details.append(f"{b['goals_scored']}G")
        if b['assists'] > 0:
            details.append(f"{b['assists']}A")
        if b['clean_sheets'] > 0:
            details.append(f"CS")
        if b['defensive_contribution'] > 0:
            details.append(f"DC({b['defensive_contribution']})")
        if b['bonus'] > 0:
            details.append(f"BP({b['bonus']})")

        details_str = ", ".join(details) if details else "-"

        print(f"{name_display:<20} {player['team']:<6} {player['position']:<5} "
              f"{player['fixture_status']:<15} {player['points_earned']:<5} {details_str}")

    # Bench
    print(f"\n{'=' * 80}")
    print("BENCH")
    print(f"{'=' * 80}\n")

    for i, player in enumerate(results['bench'], 1):
        status = "✅" if player['played'] else "🔒"
        print(f"{i}. {status} {player['name']:<20} {player['team']:<6} - "
              f"{player['points']} pts - {player['fixture_status']}")

    print("\n" + "=" * 80)


def watch_mode(gameweek: int, refresh_seconds: int = 60):
    """Watch mode - auto refresh every N seconds."""

    print(f"\n🔴 LIVE WATCH MODE - Refreshing every {refresh_seconds}s")
    print("Press Ctrl+C to exit\n")

    try:
        while True:
            # Clear screen (Unix/Mac)
            os.system('clear' if os.name != 'nt' else 'cls')

            # Fetch and display
            squad = load_squad(gameweek)
            bootstrap = fetch_bootstrap()
            live_data = fetch_live_gameweek(gameweek)
            fixtures = fetch_fixtures(gameweek)

            results = calculate_team_points(squad, live_data, bootstrap, fixtures)
            display_live_tracker(results, gameweek)

            # Wait
            time.sleep(refresh_seconds)

    except KeyboardInterrupt:
        print("\n\n✅ Live tracking stopped")
        sys.exit(0)


def save_snapshot(results: Dict, gameweek: int):
    """Save a snapshot of current scores."""

    output_dir = "data/live_tracking"
    os.makedirs(output_dir, exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_file = os.path.join(output_dir, f"gw{gameweek}_snapshot_{timestamp}.json")

    snapshot = {
        'gameweek': gameweek,
        'timestamp': timestamp,
        'total_points': results['total_points'],
        'captain_points': results['captain_points'],
        'starting_xi': results['starting_xi'],
        'bench': results['bench']
    }

    with open(output_file, 'w') as f:
        json.dump(snapshot, f, indent=2)

    print(f"\n💾 Snapshot saved: {output_file}")


def main():
    parser = argparse.ArgumentParser(description="Track Ron's FPL gameweek live")
    parser.add_argument('--gw', type=int, required=True, help='Gameweek number')
    parser.add_argument('--watch', action='store_true', help='Watch mode (auto-refresh)')
    parser.add_argument('--refresh', type=int, default=60, help='Refresh interval in seconds (default: 60)')
    parser.add_argument('--save', action='store_true', help='Save snapshot to file')

    args = parser.parse_args()

    if args.watch:
        watch_mode(args.gw, args.refresh)
    else:
        # Single check
        print(f"\n📡 Fetching GW{args.gw} live data...")

        squad = load_squad(args.gw)
        bootstrap = fetch_bootstrap()
        live_data = fetch_live_gameweek(args.gw)
        fixtures = fetch_fixtures(args.gw)

        results = calculate_team_points(squad, live_data, bootstrap, fixtures)
        display_live_tracker(results, args.gw)

        if args.save:
            save_snapshot(results, args.gw)

        print("\n✅ Tracking complete")
        print(f"💡 Tip: Use --watch flag for live auto-refresh mode\n")


if __name__ == "__main__":
    main()

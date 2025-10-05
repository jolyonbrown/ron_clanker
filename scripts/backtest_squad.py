#!/usr/bin/env python3
"""
Backtest Squad Performance

Calculate how a squad would have performed in a specific gameweek.
Useful for validating strategy with historical data.

Usage:
    python scripts/backtest_squad.py --squad gw7 --gameweek 7
    python scripts/backtest_squad.py --squad gw8 --gameweek 7
"""

import sys
from pathlib import Path
import argparse
import json
import requests
from collections import defaultdict

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

FPL_BASE_URL = "https://fantasy.premierleague.com/api"
POSITION_MAP = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}


def fetch_bootstrap_data():
    """Fetch FPL bootstrap data"""
    response = requests.get(f"{FPL_BASE_URL}/bootstrap-static/")
    response.raise_for_status()
    return response.json()


def fetch_player_history(player_id):
    """Fetch player gameweek history"""
    response = requests.get(f"{FPL_BASE_URL}/element-summary/{player_id}/")
    response.raise_for_status()
    return response.json()


def load_squad(squad_name):
    """Load squad from JSON file"""
    squad_path = project_root / 'data' / 'squads' / f'{squad_name}_squad.json'
    if not squad_path.exists():
        raise FileNotFoundError(f"Squad file not found: {squad_path}")

    with open(squad_path, 'r') as f:
        return json.load(f)


def calculate_gw_points(squad_data, gameweek, bootstrap):
    """Calculate points for squad in specific gameweek"""

    players = {p['id']: p for p in bootstrap['elements']}
    teams = {t['id']: t['short_name'] for t in bootstrap['teams']}

    # Flatten squad
    all_players = []
    squad = squad_data.get('squad', {})
    for position_group in ['goalkeepers', 'defenders', 'midfielders', 'forwards']:
        if position_group in squad:
            all_players.extend(squad[position_group])

    print(f"\n🔍 Fetching GW{gameweek} data for {len(all_players)} players...")

    results = []
    total_points = 0

    for squad_player in all_players:
        player_id = squad_player['id']
        player = players.get(player_id)

        if not player:
            print(f"⚠️  Player ID {player_id} not found")
            continue

        # Fetch player history
        try:
            history = fetch_player_history(player_id)
            gw_data = next((h for h in history['history']
                          if h['round'] == gameweek), None)

            if gw_data:
                team_name = teams.get(player['team'], 'UNK')
                position = POSITION_MAP.get(player['element_type'], 'UNK')

                # Get all point components
                minutes = gw_data['minutes']
                total_pts = gw_data['total_points']
                goals = gw_data['goals_scored']
                assists = gw_data['assists']
                dc = gw_data.get('defensive_contribution', 0)
                bonus = gw_data['bonus']
                clean_sheet = gw_data['clean_sheets']
                goals_conceded = gw_data['goals_conceded']
                saves = gw_data.get('saves', 0)
                bps = gw_data['bps']

                results.append({
                    'name': squad_player['name'],
                    'team': team_name,
                    'position': position,
                    'price': squad_player['price'],
                    'minutes': minutes,
                    'points': total_pts,
                    'goals': goals,
                    'assists': assists,
                    'dc': dc,
                    'bonus': bonus,
                    'clean_sheet': clean_sheet,
                    'goals_conceded': goals_conceded,
                    'saves': saves,
                    'bps': bps,
                    'is_dc_specialist': squad_player.get('is_dc_specialist', False)
                })

                total_points += total_pts

        except Exception as e:
            print(f"⚠️  Error fetching {squad_player['name']}: {e}")
            results.append({
                'name': squad_player['name'],
                'team': '?',
                'position': '?',
                'price': squad_player['price'],
                'minutes': 0,
                'points': 0,
                'error': str(e)
            })

    return results, total_points


def display_results(results, total_points, squad_data, gameweek):
    """Display detailed results"""

    print("\n" + "=" * 80)
    print(f"BACKTEST RESULTS - GW{gameweek}")
    print("=" * 80)
    print(f"Squad: {squad_data.get('gameweek', 'N/A')}")
    print(f"Formation: {squad_data.get('formation', 'N/A')}")
    print(f"Captain: {squad_data.get('captain', {}).get('name', 'N/A')}")
    print(f"Vice-Captain: {squad_data.get('vice_captain', {}).get('name', 'N/A')}")

    # Sort by position then points
    position_order = {'GKP': 0, 'DEF': 1, 'MID': 2, 'FWD': 3}
    results_sorted = sorted(results,
                           key=lambda x: (position_order.get(x.get('position', 'UNK'), 99),
                                        -x.get('points', 0)))

    print("\n" + "=" * 80)
    print("PLAYER PERFORMANCE")
    print("=" * 80)
    print(f"{'Player':20s} {'Pos':4s} {'Team':5s} {'Min':4s} {'Pts':4s} "
          f"{'G':3s} {'A':3s} {'DC':4s} {'Bon':4s} {'BPS':5s}")
    print("-" * 80)

    dc_points = 0
    attacking_points = 0
    captain_name = squad_data.get('captain', {}).get('name', '')

    for r in results_sorted:
        is_captain = '(C)' if r['name'] == captain_name else ''
        dc_marker = '✓' if r.get('is_dc_specialist') else ' '

        print(f"{r['name']:20s} {r['position']:4s} {r['team']:5s} "
              f"{r['minutes']:4d} {r['points']:4d} "
              f"{r['goals']:3d} {r['assists']:3d} "
              f"{r['dc']:4d} {r['bonus']:4d} "
              f"{r['bps']:5d} {dc_marker} {is_captain}")

        # Track DC vs attacking returns
        if r.get('dc', 0) > 0:
            dc_points += r['dc']
        if r.get('goals', 0) > 0 or r.get('assists', 0) > 0:
            # Goals/assists points (goals: 4/5/6/4 for GKP/DEF/MID/FWD, assists: 3)
            pos = r.get('position', '')
            goal_pts = r['goals'] * {'GKP': 4, 'DEF': 6, 'MID': 5, 'FWD': 4}.get(pos, 0)
            assist_pts = r['assists'] * 3
            attacking_points += goal_pts + assist_pts

    print("-" * 80)

    # Apply captain multiplier
    captain_player = next((r for r in results if r['name'] == captain_name), None)
    captain_bonus = 0
    if captain_player:
        captain_bonus = captain_player['points']  # Captain doubles, so bonus = 1x points

    total_with_captain = total_points + captain_bonus

    print(f"Base Total (no captain): {total_points}")
    print(f"Captain Bonus ({captain_name}): +{captain_bonus}")
    print(f"TOTAL POINTS: {total_with_captain}")

    print("\n" + "=" * 80)
    print("STRATEGY BREAKDOWN")
    print("=" * 80)
    print(f"DC Points: {dc_points} ({dc_points/total_with_captain*100:.1f}%)")
    print(f"Attacking Returns (G+A): ~{attacking_points} pts")
    print(f"Other (Bonus, CS, etc): ~{total_with_captain - dc_points - attacking_points} pts")

    # DC specialist performance
    dc_specialists = [r for r in results if r.get('is_dc_specialist')]
    if dc_specialists:
        dc_total = sum(r['points'] for r in dc_specialists)
        dc_avg = dc_total / len(dc_specialists)
        print(f"\nDC Specialists: {len(dc_specialists)} players")
        print(f"DC Specialist Total: {dc_total} pts")
        print(f"DC Specialist Average: {dc_avg:.1f} pts/player")

        dc_with_dc_pts = [r for r in dc_specialists if r.get('dc', 0) > 0]
        if dc_with_dc_pts:
            dc_consistency = len(dc_with_dc_pts) / len(dc_specialists) * 100
            print(f"DC Consistency: {len(dc_with_dc_pts)}/{len(dc_specialists)} "
                  f"earned DC points ({dc_consistency:.0f}%)")

    return total_with_captain


def compare_to_average(total_points, gameweek, bootstrap):
    """Compare squad total to GW average"""

    # Get gameweek data
    events = bootstrap['events']
    gw_data = next((e for e in events if e['id'] == gameweek), None)

    if gw_data:
        avg_score = gw_data.get('average_entry_score', 0)
        highest_score = gw_data.get('highest_score', 0)

        print("\n" + "=" * 80)
        print("COMPARISON TO GW AVERAGE")
        print("=" * 80)
        print(f"Ron's Score: {total_points}")
        print(f"GW Average: {avg_score}")
        print(f"Difference: {total_points - avg_score:+d} ({(total_points - avg_score)/avg_score*100:+.1f}%)")
        print(f"GW Highest: {highest_score}")
        print(f"vs Highest: {total_points - highest_score:+d}")

        if total_points > avg_score:
            print(f"\n✅ Beat the average by {total_points - avg_score} points!")
        else:
            print(f"\n📉 Below average by {abs(total_points - avg_score)} points")


def main():
    parser = argparse.ArgumentParser(description='Backtest squad performance in historical gameweek')
    parser.add_argument('--squad', required=True,
                       help='Squad file to test (e.g., gw7, gw8)')
    parser.add_argument('--gameweek', '--gw', type=int, required=True,
                       dest='gameweek', help='Gameweek to backtest')
    parser.add_argument('--save', action='store_true',
                       help='Save results to file')

    args = parser.parse_args()

    print("=" * 80)
    print("SQUAD BACKTEST")
    print("=" * 80)
    print(f"Squad: {args.squad}")
    print(f"Gameweek: {args.gameweek}")
    print("=" * 80)

    try:
        # Load data
        print("\n📥 Loading data...")
        bootstrap = fetch_bootstrap_data()
        squad_data = load_squad(args.squad)

        # Calculate points
        results, total_points = calculate_gw_points(squad_data, args.gameweek, bootstrap)

        # Display results
        total_with_captain = display_results(results, total_points, squad_data, args.gameweek)

        # Compare to average
        compare_to_average(total_with_captain, args.gameweek, bootstrap)

        # Save if requested
        if args.save:
            output_dir = project_root / 'data' / 'backtests'
            output_dir.mkdir(parents=True, exist_ok=True)

            output_file = output_dir / f'{args.squad}_gw{args.gameweek}_backtest.json'

            backtest_data = {
                'squad': args.squad,
                'gameweek': args.gameweek,
                'total_points': total_with_captain,
                'results': results,
                'squad_data': squad_data
            }

            with open(output_file, 'w') as f:
                json.dump(backtest_data, f, indent=2)

            print(f"\n💾 Results saved to: {output_file}")

        print("\n" + "=" * 80)
        print("✅ BACKTEST COMPLETE")
        print("=" * 80)

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()

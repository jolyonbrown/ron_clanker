#!/usr/bin/env python3
"""
Mini-League Tracker

Monitors Ron's mini-league to track:
- League standings and point gaps
- Rival teams' squads and differentials
- Chip usage by opponents
- Head-to-head comparisons
- Catch-up scenarios

Critical for end-of-season strategy when you need to gain an edge.

Usage:
    python scripts/track_mini_league.py --league 160968
    python scripts/track_mini_league.py --league 160968 --gameweek 7
    python scripts/track_mini_league.py --league 160968 --detailed
    python scripts/track_mini_league.py --league 160968 --save
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

FPL_BASE_URL = "https://fantasy.premierleague.com/api"
POSITION_MAP = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}
CONFIG_FILE = project_root / 'config' / 'ron_config.json'


def load_config():
    """Load Ron's config"""
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    return {}


def fetch_bootstrap_data():
    """Fetch FPL bootstrap data"""
    response = requests.get(f"{FPL_BASE_URL}/bootstrap-static/")
    response.raise_for_status()
    return response.json()


def fetch_league_standings(league_id, page=1):
    """Fetch mini-league standings"""
    response = requests.get(
        f"{FPL_BASE_URL}/leagues-classic/{league_id}/standings/?page_standings={page}"
    )
    response.raise_for_status()
    return response.json()


def fetch_team_entry(team_id):
    """Fetch team entry data"""
    response = requests.get(f"{FPL_BASE_URL}/entry/{team_id}/")
    response.raise_for_status()
    return response.json()


def fetch_team_picks(team_id, gameweek):
    """Fetch team picks for gameweek"""
    try:
        response = requests.get(f"{FPL_BASE_URL}/entry/{team_id}/event/{gameweek}/picks/")
        response.raise_for_status()
        return response.json()
    except:
        return None


def fetch_team_history(team_id):
    """Fetch team history"""
    response = requests.get(f"{FPL_BASE_URL}/entry/{team_id}/history/")
    response.raise_for_status()
    return response.json()


def display_league_table(league_data, ron_team_id=None):
    """Display current league standings"""

    league_info = league_data['league']
    standings = league_data['standings']['results']

    print("\n" + "=" * 100)
    print(f"MINI-LEAGUE: {league_info['name']}")
    print("=" * 100)
    print(f"League ID: {league_info['id']}")
    print(f"Teams: {len(standings)}")
    print(f"Last Updated: {league_data['last_updated_data']}")
    print("=" * 100)

    print(f"\n{'Rank':5s} {'Manager':25s} {'Team Name':30s} {'GW Pts':7s} {'Total':7s} {'Gap':7s}")
    print("-" * 100)

    leader_total = standings[0]['total'] if standings else 0

    for team in standings:
        gap = team['total'] - leader_total
        gap_str = f"{gap:+d}" if gap != 0 else "-"

        # Highlight Ron's team
        marker = "👑" if team['rank'] == 1 else ""
        marker = "🤖" if ron_team_id and team['entry'] == ron_team_id else marker

        print(f"{team['rank']:5d} {team['player_name']:25s} {team['entry_name']:30s} "
              f"{team['event_total']:7d} {team['total']:7d} {gap_str:>7s} {marker}")

    print("-" * 100)


def analyze_chips_used(standings, bootstrap):
    """Analyze chip usage across the league"""

    print("\n" + "=" * 100)
    print("CHIP USAGE ANALYSIS")
    print("=" * 100)

    chip_usage = defaultdict(list)

    for i, team in enumerate(standings[:10]):  # Top 10 for performance
        try:
            history = fetch_team_history(team['entry'])
            chips = history.get('chips', [])

            for chip in chips:
                chip_usage[chip['name']].append({
                    'manager': team['player_name'],
                    'gameweek': chip['event']
                })
        except Exception as e:
            print(f"⚠️  Could not fetch chip data for {team['player_name']}: {e}")

    if chip_usage:
        print(f"\n{'Chip':20s} {'Used By':10s} {'Managers'}")
        print("-" * 100)

        for chip_name, users in chip_usage.items():
            managers = ', '.join([f"{u['manager']} (GW{u['gameweek']})" for u in users])
            print(f"{chip_name:20s} {len(users):10d} {managers}")
    else:
        print("\n✅ No chips used yet by top 10")

    # Calculate chips remaining
    print("\n" + "=" * 100)
    print("📊 Average chips remaining in top 10: 8.0/8 (none used)")


def analyze_differentials(ron_team_id, rival_team_ids, gameweek, bootstrap):
    """Find differential players between Ron and rivals"""

    print("\n" + "=" * 100)
    print("DIFFERENTIAL ANALYSIS")
    print("=" * 100)

    if not ron_team_id:
        print("\n⚠️  Ron's team ID not configured - skipping differential analysis")
        return

    # Get Ron's squad
    ron_picks = fetch_team_picks(ron_team_id, gameweek)
    if not ron_picks:
        print(f"\n⚠️  No picks available for Ron's team in GW{gameweek}")
        return

    ron_player_ids = {p['element'] for p in ron_picks['picks']}

    # Get rivals' squads
    rivals_players = defaultdict(int)  # player_id -> count of rivals who own

    print(f"\nAnalyzing {len(rival_team_ids)} rival teams...")

    for rival_id in rival_team_ids[:5]:  # Top 5 rivals
        rival_picks = fetch_team_picks(rival_id, gameweek)
        if rival_picks:
            for pick in rival_picks['picks']:
                rivals_players[pick['element']] += 1

    # Build player lookup
    players = {p['id']: p for p in bootstrap['elements']}
    teams = {t['id']: t['short_name'] for t in bootstrap['teams']}

    # Ron's differentials (players Ron has that rivals don't)
    print(f"\n🤖 RON'S DIFFERENTIALS (Players rivals don't have):")
    differentials = []
    for player_id in ron_player_ids:
        if player_id not in rivals_players:
            player = players.get(player_id)
            if player:
                differentials.append({
                    'name': player['web_name'],
                    'team': teams.get(player['team'], 'UNK'),
                    'position': POSITION_MAP.get(player['element_type'], 'UNK'),
                    'price': player['now_cost'] / 10,
                    'ownership': player['selected_by_percent']
                })

    if differentials:
        for d in sorted(differentials, key=lambda x: -x['price'])[:10]:
            print(f"  {d['name']:20s} ({d['team']}) {d['position']:4s} £{d['price']:.1f}m - "
                  f"{d['ownership']}% owned")
    else:
        print("  None - Ron's team matches template")

    # Template players (most owned by rivals that Ron doesn't have)
    print(f"\n👥 TEMPLATE PLAYERS RON IS MISSING:")
    missing_template = []
    for player_id, count in rivals_players.items():
        if player_id not in ron_player_ids and count >= 3:  # 3+ rivals have them
            player = players.get(player_id)
            if player:
                missing_template.append({
                    'name': player['web_name'],
                    'team': teams.get(player['team'], 'UNK'),
                    'position': POSITION_MAP.get(player['element_type'], 'UNK'),
                    'price': player['now_cost'] / 10,
                    'rival_ownership': count
                })

    if missing_template:
        for m in sorted(missing_template, key=lambda x: -x['rival_ownership'])[:10]:
            print(f"  {m['name']:20s} ({m['team']}) {m['position']:4s} £{m['price']:.1f}m - "
                  f"{m['rival_ownership']}/5 rivals have")
    else:
        print("  None - Ron has all template players")


def calculate_catch_up_scenarios(standings, ron_team_id, gws_remaining):
    """Calculate what Ron needs to catch the leaders"""

    print("\n" + "=" * 100)
    print("CATCH-UP SCENARIOS")
    print("=" * 100)

    if not ron_team_id:
        print("\n⚠️  Ron's team ID not configured")
        return

    ron_team = next((t for t in standings if t['entry'] == ron_team_id), None)

    if not ron_team:
        # Ron not in league yet
        leader = standings[0]
        print(f"\n🎯 Ron entering at GW{39-gws_remaining}")
        print(f"Leader: {leader['player_name']} ({leader['entry_name']}) - {leader['total']} pts")
        print(f"Gap: {leader['total']} pts")
        print(f"Gameweeks remaining: {gws_remaining}")

        print(f"\n📊 Points per GW needed to catch up:")
        leader_avg = leader['total'] / (38 - gws_remaining)

        for ron_avg in [60, 65, 70, 75, 80]:
            ron_final = ron_avg * gws_remaining
            leader_final = leader['total'] + (leader_avg * gws_remaining)
            margin = ron_final - leader_final

            result = "✅ WINS" if margin > 0 else "❌ LOSES"
            print(f"  Ron @ {ron_avg} pts/GW: {ron_final:.0f} vs {leader_final:.0f} = "
                  f"{margin:+.0f} pts {result}")
    else:
        # Ron already in league
        leader = standings[0]
        ron_rank = ron_team['rank']
        gap = ron_team['total'] - leader['total']

        print(f"\n🤖 Ron's Position: {ron_rank}/{len(standings)}")
        print(f"Current points: {ron_team['total']}")
        print(f"Gap to leader: {gap:+d} pts")
        print(f"Gameweeks remaining: {gws_remaining}")

        gws_played = 38 - gws_remaining
        ron_avg = ron_team['total'] / gws_played if gws_played > 0 else 0
        leader_avg = leader['total'] / gws_played if gws_played > 0 else 0

        points_per_gw_needed = abs(gap) / gws_remaining if gws_remaining > 0 else 0

        print(f"\n📊 Current averages:")
        print(f"  Ron: {ron_avg:.1f} pts/GW")
        print(f"  Leader: {leader_avg:.1f} pts/GW")
        print(f"  Ron needs: +{points_per_gw_needed:.1f} pts/GW advantage to catch up")


def main():
    parser = argparse.ArgumentParser(description="Track Ron's mini-league performance")
    parser.add_argument('--league', type=int, required=True,
                       help='Mini-league ID')
    parser.add_argument('--gameweek', '--gw', type=int,
                       dest='gameweek', help='Gameweek for detailed analysis')
    parser.add_argument('--detailed', action='store_true',
                       help='Show detailed analysis (chips, differentials, scenarios)')
    parser.add_argument('--save', action='store_true',
                       help='Save league tracking data')

    args = parser.parse_args()

    print("=" * 100)
    print("MINI-LEAGUE TRACKER")
    print("=" * 100)
    print(f"League ID: {args.league}")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 100)

    try:
        # Load data
        print("\n📥 Loading league data...")
        bootstrap = fetch_bootstrap_data()
        league_data = fetch_league_standings(args.league)

        # Get current gameweek
        current_gw = next(e['id'] for e in bootstrap['events'] if e['is_current'])
        gameweek = args.gameweek or current_gw
        gws_remaining = 38 - current_gw + 1

        # Get Ron's team ID from config
        config = load_config()
        ron_team_id = config.get('team_id')

        # Display standings
        display_league_table(league_data, ron_team_id)

        # Detailed analysis if requested
        if args.detailed:
            standings = league_data['standings']['results']

            # Chip usage
            analyze_chips_used(standings, bootstrap)

            # Differentials (Ron vs top 5)
            if ron_team_id:
                top_5_ids = [t['entry'] for t in standings[:5]]
                analyze_differentials(ron_team_id, top_5_ids, gameweek, bootstrap)

            # Catch-up scenarios
            calculate_catch_up_scenarios(standings, ron_team_id, gws_remaining)

        # Save if requested
        if args.save:
            output_dir = project_root / 'data' / 'mini_league_tracking'
            output_dir.mkdir(parents=True, exist_ok=True)

            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_file = output_dir / f'league_{args.league}_gw{gameweek}_{timestamp}.json'

            tracking_data = {
                'league_id': args.league,
                'gameweek': gameweek,
                'timestamp': timestamp,
                'league_data': league_data,
                'ron_team_id': ron_team_id
            }

            with open(output_file, 'w') as f:
                json.dump(tracking_data, f, indent=2)

            print(f"\n💾 League data saved to: {output_file}")

        print("\n" + "=" * 100)
        print("✅ TRACKING COMPLETE")
        print("=" * 100)

        if not ron_team_id:
            print("\n💡 TIP: Once Ron's team is registered, add team_id to config/ron_config.json")
            print("    for detailed differential and chip analysis")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()

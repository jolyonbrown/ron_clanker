#!/usr/bin/env python3
"""
Fixture Difficulty Analyzer - Look ahead 6 gameweeks

Analyzes upcoming fixtures to identify:
- Players with good fixture runs
- Teams to target/avoid
- Optimal transfer timing based on fixture swings

Ron's philosophy: "Look ahead 3-6 gameweeks for planning"
"""

import requests
import json
from pathlib import Path
from collections import defaultdict

FPL_BASE_URL = "https://fantasy.premierleague.com/api"

def load_data():
    """Load FPL data"""
    print("🔄 Loading FPL data...")

    bootstrap = requests.get(f"{FPL_BASE_URL}/bootstrap-static/").json()
    fixtures = requests.get(f"{FPL_BASE_URL}/fixtures/").json()

    teams = {t['id']: t for t in bootstrap['teams']}
    players = {p['id']: p for p in bootstrap['elements']}

    return bootstrap, fixtures, teams, players

def get_fixture_run(team_id, fixtures, start_gw, num_gws=6):
    """Get fixture difficulty for a team over next N gameweeks"""
    team_fixtures = []

    for gw in range(start_gw, start_gw + num_gws):
        gw_fixtures = [f for f in fixtures if f['event'] == gw]

        for fix in gw_fixtures:
            if fix['team_h'] == team_id:
                team_fixtures.append({
                    'gw': gw,
                    'opponent': fix['team_a'],
                    'home': True,
                    'difficulty': fix['team_h_difficulty']
                })
            elif fix['team_a'] == team_id:
                team_fixtures.append({
                    'gw': gw,
                    'opponent': fix['team_h'],
                    'home': False,
                    'difficulty': fix['team_a_difficulty']
                })

    return team_fixtures

def calculate_fixture_score(fixtures_list):
    """Calculate average difficulty (lower = better)"""
    if not fixtures_list:
        return 0

    total_difficulty = sum(f['difficulty'] for f in fixtures_list)
    return total_difficulty / len(fixtures_list)

def analyze_team_fixtures(teams, fixtures, start_gw=8, num_gws=6):
    """Analyze all teams' fixture difficulty"""
    team_analysis = []

    for team_id, team in teams.items():
        fixture_run = get_fixture_run(team_id, fixtures, start_gw, num_gws)
        avg_difficulty = calculate_fixture_score(fixture_run)

        team_analysis.append({
            'team_id': team_id,
            'team_name': team['short_name'],
            'fixtures': fixture_run,
            'avg_difficulty': avg_difficulty
        })

    # Sort by easiest fixtures (lowest difficulty)
    team_analysis.sort(key=lambda x: x['avg_difficulty'])

    return team_analysis

def get_player_fixtures(player, teams, fixtures, start_gw=8, num_gws=6):
    """Get fixture run for a specific player"""
    team_id = player['team']
    team_name = teams[team_id]['short_name']
    fixture_run = get_fixture_run(team_id, fixtures, start_gw, num_gws)

    return {
        'player_name': player['web_name'],
        'team': team_name,
        'position': ['GKP', 'DEF', 'MID', 'FWD'][player['element_type'] - 1],
        'price': player['now_cost'] / 10,
        'fixtures': fixture_run,
        'avg_difficulty': calculate_fixture_score(fixture_run)
    }

def analyze_squad_fixtures(squad_file, teams, fixtures, start_gw=8):
    """Analyze fixtures for our preliminary squad"""

    with open(squad_file, 'r') as f:
        squad_data = json.load(f)

    # Get all player IDs
    all_players = []
    for pos, players_list in squad_data['squad']['squad'].items():
        all_players.extend(players_list)

    # Get player fixture analysis
    players_response = requests.get(f"{FPL_BASE_URL}/bootstrap-static/").json()
    players_dict = {p['id']: p for p in players_response['elements']}

    fixture_analysis = []
    for player_data in all_players:
        player = players_dict[player_data['id']]
        player_fixtures = get_player_fixtures(player, teams, fixtures, start_gw, 6)
        fixture_analysis.append(player_fixtures)

    return fixture_analysis

def display_team_fixtures(team_analysis, teams, num_display=20):
    """Display team fixture analysis"""
    print("\n" + "=" * 80)
    print("FIXTURE DIFFICULTY - GW8-13 (Next 6 Gameweeks)")
    print("=" * 80)
    print("Difficulty: 1=Easy, 2=Moderate, 3=Average, 4=Hard, 5=Very Hard")
    print()
    print(f"{'Rank':<5} {'Team':<6} {'Avg':<5} GW8  GW9  GW10 GW11 GW12 GW13")
    print("-" * 80)

    for i, team_data in enumerate(team_analysis[:num_display], 1):
        team_name = team_data['team_name']
        avg_diff = team_data['avg_difficulty']

        # Build fixture string
        fixture_str = ""
        for fix in team_data['fixtures']:
            opp_name = teams[fix['opponent']]['short_name']
            home_marker = "" if fix['home'] else "@"
            diff = fix['difficulty']

            # Color code difficulty
            if diff <= 2:
                color = "✅"  # Easy
            elif diff == 3:
                color = "🟡"  # Average
            else:
                color = "🔴"  # Hard

            fixture_str += f"{color}{home_marker}{opp_name:<3} "

        print(f"{i:<5} {team_name:<6} {avg_diff:4.1f}  {fixture_str}")

def display_squad_fixtures(fixture_analysis):
    """Display fixture analysis for our squad"""
    print("\n" + "=" * 80)
    print("OUR SQUAD - FIXTURE ANALYSIS (GW8-13)")
    print("=" * 80)

    # Group by position
    by_position = defaultdict(list)
    for player in fixture_analysis:
        by_position[player['position']].append(player)

    for pos in ['GKP', 'DEF', 'MID', 'FWD']:
        if pos not in by_position:
            continue

        print(f"\n{pos}:")

        # Sort by fixture difficulty (easiest first)
        by_position[pos].sort(key=lambda x: x['avg_difficulty'])

        for player in by_position[pos]:
            print(f"\n  {player['player_name']:20s} {player['team']:4s} £{player['price']:.1f}m  Avg: {player['avg_difficulty']:.1f}")

            fixture_str = "    "
            for fix in player['fixtures']:
                home = "" if fix['home'] else "@"
                diff = fix['difficulty']

                if diff <= 2:
                    color = "✅"
                elif diff == 3:
                    color = "🟡"
                else:
                    color = "🔴"

                fixture_str += f"GW{fix['gw']}:{color}{home} "

            print(fixture_str)

def main():
    print("=" * 80)
    print("FIXTURE DIFFICULTY ANALYZER")
    print("=" * 80)

    # Load data
    bootstrap, fixtures, teams, players = load_data()

    # Analyze all teams
    team_analysis = analyze_team_fixtures(teams, fixtures, start_gw=8, num_gws=6)

    # Display team fixtures
    display_team_fixtures(team_analysis, teams)

    # Analyze our squad
    project_root = Path(__file__).parent.parent
    squad_file = project_root / 'data' / 'squads' / 'gw8_optimized_squad.json'

    if squad_file.exists():
        print("\n" + "=" * 80)
        print("ANALYZING OUR PRELIMINARY SQUAD")
        print("=" * 80)

        squad_fixtures = analyze_squad_fixtures(squad_file, teams, fixtures, start_gw=8)
        display_squad_fixtures(squad_fixtures)

        # Identify concerns
        print("\n" + "=" * 80)
        print("FIXTURE CONCERNS")
        print("=" * 80)

        poor_fixtures = [p for p in squad_fixtures if p['avg_difficulty'] >= 3.5]

        if poor_fixtures:
            print("\n⚠️  Players with tough fixtures (avg ≥ 3.5):")
            for p in poor_fixtures:
                print(f"  - {p['player_name']} ({p['team']}) - Avg: {p['avg_difficulty']:.1f}")
        else:
            print("\n✅ No major fixture concerns in the squad")

        # Identify opportunities
        good_fixtures = [p for p in squad_fixtures if p['avg_difficulty'] <= 2.5]
        print(f"\n✅ Players with great fixtures (avg ≤ 2.5): {len(good_fixtures)}")
        for p in good_fixtures[:5]:
            print(f"  - {p['player_name']} ({p['team']}) - Avg: {p['avg_difficulty']:.1f}")

    print("\n" + "=" * 80)
    print("✅ FIXTURE ANALYSIS COMPLETE")
    print("=" * 80)

if __name__ == '__main__':
    main()

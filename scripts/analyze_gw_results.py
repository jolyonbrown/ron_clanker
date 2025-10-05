#!/usr/bin/env python3
"""
Post-Gameweek Results Analyzer

Comprehensive analysis after a gameweek completes:
- Final points breakdown
- Performance vs predictions
- DC strategy effectiveness
- Captain success
- Player performance ratings
- Template comparison
- Price changes impact
- Learnings for next GW

Usage:
    python scripts/analyze_gw_results.py --gw 8
    python scripts/analyze_gw_results.py --gw 8 --save-report
"""

import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import argparse
import json
import requests
from typing import Dict, List
from datetime import datetime
from collections import defaultdict

# FPL API
FPL_BASE_URL = "https://fantasy.premierleague.com/api"


def load_squad(gameweek: int) -> Dict:
    """Load Ron's squad."""
    squad_file = f"data/squads/gw{gameweek}_squad.json"
    with open(squad_file) as f:
        return json.load(f)


def fetch_gameweek_data(gameweek: int) -> Dict:
    """Fetch completed gameweek data."""
    url = f"{FPL_BASE_URL}/event/{gameweek}/live/"
    response = requests.get(url)
    response.raise_for_status()
    return response.json()


def fetch_bootstrap() -> Dict:
    """Fetch bootstrap data."""
    response = requests.get(f"{FPL_BASE_URL}/bootstrap-static/")
    response.raise_for_status()
    return response.json()


def fetch_gameweek_summary(gameweek: int, bootstrap: Dict) -> Dict:
    """Get gameweek summary stats."""
    gw_data = next((gw for gw in bootstrap['events'] if gw['id'] == gameweek), None)
    return gw_data if gw_data else {}


def calculate_final_points(squad: Dict, live_data: Dict, bootstrap: Dict) -> Dict:
    """Calculate final points with full breakdown."""

    team_map = {t['id']: t['short_name'] for t in bootstrap['teams']}
    player_map = {p['id']: p for p in bootstrap['elements']}

    captain_id = squad['captain']['id']
    vice_id = squad['vice_captain']['id']

    results = {
        'players': [],
        'total_points': 0,
        'starting_xi_points': 0,
        'bench_points': 0,
        'captain_points': 0,
        'dc_points': 0,
        'attacking_points': 0,
        'clean_sheet_points': 0,
        'bonus_points': 0
    }

    # Process all players
    for pos_group in ['goalkeepers', 'defenders', 'midfielders', 'forwards']:
        for player in squad['squad'][pos_group]:
            player_info = player_map.get(player['id'])
            if not player_info:
                continue

            # Get live stats
            player_live = next((p for p in live_data['elements'] if p['id'] == player['id']), None)
            if not player_live:
                continue

            stats = player_live.get('stats', {})
            explain = player_live.get('explain', [])

            # Detailed breakdown
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

            total_pts = stats.get('total_points', 0)
            is_captain = player['id'] == captain_id
            multiplier = 2 if is_captain else 1

            player_result = {
                'id': player['id'],
                'name': player['name'],
                'team': team_map.get(player_info['team'], 'Unknown'),
                'position': pos_group[:3].upper(),
                'points_raw': total_pts,
                'points_earned': total_pts * multiplier,
                'breakdown': breakdown,
                'is_captain': is_captain,
                'is_vice': player['id'] == vice_id,
                'explain': explain
            }

            results['players'].append(player_result)

            # Accumulate totals (assuming first 11 are starters for now)
            # TODO: Handle auto-subs properly
            if len(results['players']) <= 11:
                results['starting_xi_points'] += total_pts * multiplier
                if is_captain:
                    results['captain_points'] += total_pts * multiplier
            else:
                results['bench_points'] += total_pts

            # Category totals
            results['dc_points'] += breakdown['defensive_contribution']
            results['attacking_points'] += (breakdown['goals_scored'] * 5 + breakdown['assists'] * 3)  # Approx
            results['clean_sheet_points'] += (breakdown['clean_sheets'] * 4)  # Approx for DEF
            results['bonus_points'] += breakdown['bonus']

    results['total_points'] = results['starting_xi_points']

    return results


def analyze_dc_performance(results: Dict) -> Dict:
    """Analyze defensive contribution strategy effectiveness."""

    dc_players = [p for p in results['players'] if p['breakdown']['defensive_contribution'] > 0]

    dc_analysis = {
        'dc_earners': len(dc_players),
        'total_dc_points': results['dc_points'],
        'dc_player_names': [p['name'] for p in dc_players],
        'dc_contribution_pct': (results['dc_points'] / results['total_points'] * 100) if results['total_points'] > 0 else 0,
        'highest_dc': max(dc_players, key=lambda p: p['breakdown']['defensive_contribution']) if dc_players else None
    }

    return dc_analysis


def analyze_captain_performance(results: Dict) -> Dict:
    """Analyze captain choice effectiveness."""

    captain = next((p for p in results['players'] if p['is_captain']), None)

    if not captain:
        return {'success': False, 'reason': 'No captain found'}

    # Compare to other potential captains
    all_points = sorted(results['players'], key=lambda p: p['points_raw'], reverse=True)
    optimal_captain = all_points[0]

    captain_analysis = {
        'captain_name': captain['name'],
        'captain_points': captain['points_raw'],
        'captain_contribution': captain['points_earned'],
        'optimal_captain': optimal_captain['name'],
        'optimal_points': optimal_captain['points_raw'],
        'points_left_on_table': (optimal_captain['points_raw'] - captain['points_raw']) * 2,
        'was_optimal': captain['id'] == optimal_captain['id'],
        'captain_breakdown': captain['breakdown']
    }

    return captain_analysis


def compare_to_template(gameweek: int, results: Dict, gw_summary: Dict) -> Dict:
    """Compare Ron's score to gameweek averages."""

    avg_score = gw_summary.get('average_entry_score', 0)
    highest_score = gw_summary.get('highest_score', 0)

    comparison = {
        'ron_score': results['total_points'],
        'average_score': avg_score,
        'highest_score': highest_score,
        'vs_average': results['total_points'] - avg_score,
        'percentile': 'N/A',  # Would need full rank data
        'beat_average': results['total_points'] > avg_score
    }

    return comparison


def identify_learnings(results: Dict, dc_analysis: Dict, captain_analysis: Dict) -> List[str]:
    """Identify key learnings for Ellie's review."""

    learnings = []

    # DC strategy check
    if dc_analysis['dc_earners'] >= 8:
        learnings.append(f"✅ Strong DC performance: {dc_analysis['dc_earners']} players earned DC points ({dc_analysis['total_dc_points']} pts total)")
    else:
        learnings.append(f"⚠️  Lower DC earners than expected: Only {dc_analysis['dc_earners']} players ({dc_analysis['total_dc_points']} pts)")

    # Captain decision
    if captain_analysis['was_optimal']:
        learnings.append(f"✅ Optimal captain choice: {captain_analysis['captain_name']} was the best pick")
    else:
        learnings.append(f"❌ Captain hindsight: {captain_analysis['optimal_captain']} would have been better ({captain_analysis['points_left_on_table']} pts lost)")

    # Blanks check
    blanks = [p for p in results['players'][:11] if p['points_raw'] <= 2]
    if len(blanks) > 3:
        learnings.append(f"⚠️  Multiple blanks: {len(blanks)} starting players scored ≤2 pts")

    # Big hauls
    hauls = [p for p in results['players'] if p['points_raw'] >= 10]
    if hauls:
        learnings.append(f"🌟 Hauls: {', '.join(p['name'] for p in hauls)} delivered big")

    return learnings


def generate_staff_comments(results: Dict, dc_analysis: Dict, captain_analysis: Dict, comparison: Dict) -> Dict:
    """Generate comments from each staff member."""

    comments = {}

    # Ron's overall take
    beat_avg = "Good" if comparison['beat_average'] else "Not good enough"
    comments['ron'] = f"{results['total_points']} points. {beat_avg}. {'Captain choice was right.' if captain_analysis['was_optimal'] else 'Captain let us down.'}"

    # Digger (Defense coach)
    comments['digger'] = f"{dc_analysis['dc_earners']} players earned DC points, lad. {dc_analysis['total_dc_points']} points from defensive work. {'Proper stuff!' if dc_analysis['dc_earners'] >= 8 else 'Need more DC merchants.'}"

    # Sophia (Attack coach)
    goals = sum(p['breakdown']['goals_scored'] for p in results['players'])
    assists = sum(p['breakdown']['assists'] for p in results['players'])
    comments['sophia'] = f"{goals} goals, {assists} assists. {'Good attacking returns!' if goals + assists >= 3 else 'We need more creativity.'}"

    # Maggie (Data analyst)
    comments['maggie'] = f"Actual: {results['total_points']} pts. Average: {comparison['average_score']} pts. Variance: {comparison['vs_average']:+.0f} pts. {'Above expectation.' if comparison['beat_average'] else 'Below average.'}"

    # Jimmy (Value)
    comments['jimmy'] = f"Points per player: {results['total_points']/11:.1f}. {'Value delivered.' if results['total_points'] >= 60 else 'Value lacking.'}"

    # Ellie (Learning)
    comments['ellie'] = f"Key learning: {'DC strategy working as planned.' if dc_analysis['dc_earners'] >= 8 else 'DC consistency lower than projected - investigate why.'}"

    return comments


def print_analysis(results: Dict, dc_analysis: Dict, captain_analysis: Dict,
                  comparison: Dict, learnings: List[str], comments: Dict, gameweek: int):
    """Print comprehensive analysis to terminal."""

    print("\n" + "=" * 80)
    print(f"📊 GAMEWEEK {gameweek} RESULTS ANALYSIS - TWO POINTS FC")
    print("=" * 80)

    # Final score
    print(f"\n🎯 FINAL SCORE: {results['total_points']} points")
    print(f"   vs Average: {comparison['average_score']} ({comparison['vs_average']:+.0f})")
    print(f"   vs Highest: {comparison['highest_score']}")
    status = "✅ BEAT AVERAGE" if comparison['beat_average'] else "❌ BELOW AVERAGE"
    print(f"   Status: {status}")

    # Points breakdown
    print(f"\n📈 POINTS BREAKDOWN:")
    print(f"   Starting XI: {results['starting_xi_points']} pts")
    print(f"   Captain: {results['captain_points']} pts ({captain_analysis['captain_name']})")
    print(f"   Bench: {results['bench_points']} pts")
    print(f"   DC Points: {results['dc_points']} pts ({dc_analysis['dc_contribution_pct']:.1f}% of total)")
    print(f"   Bonus: {results['bonus_points']} pts")

    # Player performances
    print(f"\n⭐ TOP PERFORMERS:")
    top_3 = sorted(results['players'], key=lambda p: p['points_earned'], reverse=True)[:3]
    for i, p in enumerate(top_3, 1):
        cap = "(C)" if p['is_captain'] else ""
        print(f"   {i}. {p['name']} {cap} - {p['points_earned']} pts")

    # DC Analysis
    print(f"\n🛡️  DC STRATEGY ANALYSIS:")
    print(f"   DC Earners: {dc_analysis['dc_earners']}/15 players")
    print(f"   Total DC Points: {dc_analysis['total_dc_points']}")
    print(f"   DC Players: {', '.join(dc_analysis['dc_player_names'][:10])}")

    # Captain analysis
    print(f"\n👑 CAPTAIN ANALYSIS:")
    print(f"   Choice: {captain_analysis['captain_name']} ({captain_analysis['captain_points']} pts)")
    print(f"   Optimal: {captain_analysis['optimal_captain']} ({captain_analysis['optimal_points']} pts)")
    if not captain_analysis['was_optimal']:
        print(f"   Points Lost: {captain_analysis['points_left_on_table']} pts")

    # Learnings
    print(f"\n📚 KEY LEARNINGS:")
    for learning in learnings:
        print(f"   {learning}")

    # Staff comments
    print(f"\n💬 STAFF MEETING SOUNDBITES:")
    print(f"   Ron: \"{comments['ron']}\"")
    print(f"   Digger: \"{comments['digger']}\"")
    print(f"   Sophia: \"{comments['sophia']}\"")
    print(f"   Maggie: \"{comments['maggie']}\"")
    print(f"   Ellie: \"{comments['ellie']}\"")

    print("\n" + "=" * 80)


def save_analysis_report(results: Dict, dc_analysis: Dict, captain_analysis: Dict,
                        comparison: Dict, learnings: List[str], comments: Dict, gameweek: int):
    """Save full analysis to JSON."""

    output_dir = "data/gw_results"
    os.makedirs(output_dir, exist_ok=True)

    report = {
        'gameweek': gameweek,
        'timestamp': datetime.now().isoformat(),
        'final_score': results['total_points'],
        'vs_average': comparison['vs_average'],
        'beat_average': comparison['beat_average'],
        'points_breakdown': {
            'starting_xi': results['starting_xi_points'],
            'captain': results['captain_points'],
            'bench': results['bench_points'],
            'dc_points': results['dc_points'],
            'bonus': results['bonus_points']
        },
        'dc_analysis': dc_analysis,
        'captain_analysis': captain_analysis,
        'comparison': comparison,
        'learnings': learnings,
        'staff_comments': comments,
        'player_details': results['players']
    }

    output_file = os.path.join(output_dir, f"gw{gameweek}_analysis.json")
    with open(output_file, 'w') as f:
        json.dump(report, f, indent=2)

    print(f"\n💾 Analysis report saved: {output_file}")


def main():
    parser = argparse.ArgumentParser(description="Analyze completed gameweek results")
    parser.add_argument('--gw', type=int, required=True, help='Gameweek number')
    parser.add_argument('--save-report', action='store_true', help='Save analysis report to file')

    args = parser.parse_args()

    print(f"\n📊 Analyzing Gameweek {args.gw} results...")

    # Fetch all data
    squad = load_squad(args.gw)
    live_data = fetch_gameweek_data(args.gw)
    bootstrap = fetch_bootstrap()
    gw_summary = fetch_gameweek_summary(args.gw, bootstrap)

    # Run analysis
    results = calculate_final_points(squad, live_data, bootstrap)
    dc_analysis = analyze_dc_performance(results)
    captain_analysis = analyze_captain_performance(results)
    comparison = compare_to_template(args.gw, results, gw_summary)
    learnings = identify_learnings(results, dc_analysis, captain_analysis)
    comments = generate_staff_comments(results, dc_analysis, captain_analysis, comparison)

    # Display
    print_analysis(results, dc_analysis, captain_analysis, comparison, learnings, comments, args.gw)

    # Save if requested
    if args.save_report:
        save_analysis_report(results, dc_analysis, captain_analysis, comparison,
                           learnings, comments, args.gw)

    print("\n✅ Analysis complete!")
    print(f"💡 Next: Review learnings and plan GW{args.gw + 1} transfers\n")


if __name__ == "__main__":
    main()

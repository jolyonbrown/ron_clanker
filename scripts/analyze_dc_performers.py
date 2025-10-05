#!/usr/bin/env python3
"""
Analyze Defensive Contribution Performance - Gameweeks 1-7

This script analyzes all players' defensive contribution performance
across the first 7 gameweeks of the 2025/26 season.

Identifies:
- Consistent DC point earners
- Value players (DC points per £m)
- Position-specific rankings
"""

import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import requests
from typing import Dict, List, Tuple
import json
from collections import defaultdict

# FPL API constants
FPL_BASE_URL = "https://fantasy.premierleague.com/api"
POSITION_MAP = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}


def fetch_bootstrap_data() -> Dict:
    """Fetch main FPL data (players, teams, gameweeks)."""
    print("Fetching FPL bootstrap data...")
    response = requests.get(f"{FPL_BASE_URL}/bootstrap-static/")
    response.raise_for_status()
    return response.json()


def fetch_player_history(player_id: int) -> Dict:
    """Fetch individual player's gameweek history."""
    response = requests.get(f"{FPL_BASE_URL}/element-summary/{player_id}/")
    response.raise_for_status()
    return response.json()


def analyze_dc_consistency(player: Dict, history: List[Dict], max_gw: int = 7) -> Dict:
    """
    Analyze a player's defensive contribution consistency.

    Returns:
        Dict with DC stats including:
        - dc_weeks: Number of weeks earning DC points
        - dc_consistency: % of weeks played where DC earned
        - total_dc_points: Total DC points earned
        - avg_dc_per_gw: Average DC points per gameweek played
    """
    position_type = player['element_type']

    # Filter to GW1-7 and games where player actually played
    gw_history = [
        gw for gw in history
        if gw['round'] <= max_gw and gw['minutes'] > 0
    ]

    if not gw_history:
        return {
            'weeks_played': 0,
            'dc_weeks': 0,
            'dc_consistency': 0.0,
            'total_dc_points': 0,
            'avg_dc_per_gw': 0.0,
            'avg_tackles': 0.0,
            'avg_cbi': 0.0,
            'avg_recoveries': 0.0
        }

    weeks_played = len(gw_history)
    dc_weeks = sum(1 for gw in gw_history if gw.get('defensive_contribution', 0) > 0)
    total_dc_points = sum(gw.get('defensive_contribution', 0) for gw in gw_history)

    # Calculate average defensive actions
    total_tackles = sum(gw.get('tackles', 0) for gw in gw_history)
    total_cbi = sum(gw.get('clearances_blocks_interceptions', 0) for gw in gw_history)
    total_recoveries = sum(gw.get('recoveries', 0) for gw in gw_history)

    return {
        'weeks_played': weeks_played,
        'dc_weeks': dc_weeks,
        'dc_consistency': (dc_weeks / weeks_played * 100) if weeks_played > 0 else 0,
        'total_dc_points': total_dc_points,
        'avg_dc_per_gw': total_dc_points / weeks_played if weeks_played > 0 else 0,
        'avg_tackles': total_tackles / weeks_played if weeks_played > 0 else 0,
        'avg_cbi': total_cbi / weeks_played if weeks_played > 0 else 0,
        'avg_recoveries': total_recoveries / weeks_played if weeks_played > 0 else 0
    }


def calculate_value_metrics(player: Dict, dc_stats: Dict) -> Dict:
    """Calculate value-based metrics for a player."""
    price = player['now_cost'] / 10.0  # Convert from 63 -> 6.3m
    total_points = player['total_points']

    return {
        'price': price,
        'total_points': total_points,
        'points_per_million': total_points / price if price > 0 else 0,
        'dc_points_per_million': dc_stats['total_dc_points'] / price if price > 0 else 0,
        'selected_by_percent': player['selected_by_percent']
    }


def analyze_all_players(bootstrap: Dict, sample_size: int = None) -> Dict[int, Dict]:
    """
    Analyze all players (or sample) for DC performance.

    Args:
        bootstrap: FPL bootstrap data
        sample_size: If set, only analyze first N players (for testing)

    Returns:
        Dict mapping player_id to analysis results
    """
    players = bootstrap['elements']
    if sample_size:
        players = players[:sample_size]
        print(f"⚠️  SAMPLE MODE: Analyzing only {sample_size} players")

    results = {}
    total = len(players)

    print(f"\nAnalyzing {total} players across GW1-7...")

    for i, player in enumerate(players, 1):
        player_id = player['id']
        name = player['web_name']

        # Progress indicator every 50 players
        if i % 50 == 0 or i == total:
            print(f"  Progress: {i}/{total} ({i/total*100:.1f}%)")

        try:
            # Fetch detailed history
            player_data = fetch_player_history(player_id)
            history = player_data.get('history', [])

            # Analyze DC performance
            dc_stats = analyze_dc_consistency(player, history)
            value_metrics = calculate_value_metrics(player, dc_stats)

            results[player_id] = {
                'id': player_id,
                'name': name,
                'team': player['team'],
                'position': POSITION_MAP[player['element_type']],
                'position_id': player['element_type'],
                **dc_stats,
                **value_metrics
            }

        except Exception as e:
            print(f"  ⚠️  Error analyzing {name}: {e}")
            continue

    print(f"✅ Analysis complete: {len(results)} players processed\n")
    return results


def generate_rankings(results: Dict[int, Dict]) -> Dict[str, List[Dict]]:
    """
    Generate rankings by position and criteria.

    Returns:
        Dict with keys like 'def_by_consistency', 'mid_by_dc_value', etc.
    """
    rankings = defaultdict(list)

    # Group by position
    by_position = defaultdict(list)
    for player in results.values():
        pos = player['position']
        by_position[pos].append(player)

    # Defenders - ranked by DC consistency
    defenders = sorted(
        by_position['DEF'],
        key=lambda p: (p['dc_consistency'], p['total_dc_points']),
        reverse=True
    )
    rankings['defenders_by_consistency'] = defenders[:30]

    # Defenders - ranked by value (DC points per £m)
    defenders_value = sorted(
        [d for d in by_position['DEF'] if d['weeks_played'] >= 3],  # Min 3 games
        key=lambda p: p['dc_points_per_million'],
        reverse=True
    )
    rankings['defenders_by_value'] = defenders_value[:20]

    # Midfielders - ranked by DC consistency
    midfielders = sorted(
        by_position['MID'],
        key=lambda p: (p['dc_consistency'], p['total_dc_points']),
        reverse=True
    )
    rankings['midfielders_by_consistency'] = midfielders[:30]

    # Midfielders - ranked by value
    midfielders_value = sorted(
        [m for m in by_position['MID'] if m['weeks_played'] >= 3],
        key=lambda p: p['dc_points_per_million'],
        reverse=True
    )
    rankings['midfielders_by_value'] = midfielders_value[:20]

    # Overall - best DC performers regardless of position
    all_dc_players = sorted(
        [p for p in results.values() if p['weeks_played'] >= 3],
        key=lambda p: (p['dc_consistency'], p['total_dc_points']),
        reverse=True
    )
    rankings['overall_dc_performers'] = all_dc_players[:40]

    return rankings


def print_rankings(rankings: Dict[str, List[Dict]]):
    """Print formatted rankings to console."""

    print("=" * 80)
    print("DEFENSIVE CONTRIBUTION ANALYSIS - GAMEWEEKS 1-7")
    print("=" * 80)

    # Top Defenders by Consistency
    print("\n🛡️  TOP DEFENDERS - DC CONSISTENCY\n")
    print(f"{'Rank':<5} {'Player':<20} {'Price':<8} {'Played':<7} {'DC Wks':<8} {'DC %':<8} {'DC Pts':<8} {'Avg Actions'}")
    print("-" * 90)

    for i, player in enumerate(rankings['defenders_by_consistency'][:20], 1):
        avg_actions = player['avg_tackles'] + player['avg_cbi']
        print(f"{i:<5} {player['name']:<20} £{player['price']:.1f}m    "
              f"{player['weeks_played']:<7} {player['dc_weeks']:<8} "
              f"{player['dc_consistency']:.1f}%    {player['total_dc_points']:<8} "
              f"{avg_actions:.1f}")

    # Top Midfielders by Consistency
    print("\n⚡ TOP MIDFIELDERS - DC CONSISTENCY\n")
    print(f"{'Rank':<5} {'Player':<20} {'Price':<8} {'Played':<7} {'DC Wks':<8} {'DC %':<8} {'DC Pts':<8} {'Avg Actions'}")
    print("-" * 90)

    for i, player in enumerate(rankings['midfielders_by_consistency'][:20], 1):
        avg_actions = player['avg_tackles'] + player['avg_cbi'] + player['avg_recoveries']
        print(f"{i:<5} {player['name']:<20} £{player['price']:.1f}m    "
              f"{player['weeks_played']:<7} {player['dc_weeks']:<8} "
              f"{player['dc_consistency']:.1f}%    {player['total_dc_points']:<8} "
              f"{avg_actions:.1f}")

    # Value Defenders
    print("\n💰 BEST VALUE DEFENDERS (DC Points per £m)\n")
    print(f"{'Rank':<5} {'Player':<20} {'Price':<8} {'DC Pts':<8} {'DC/£m':<10} {'Own %'}")
    print("-" * 75)

    for i, player in enumerate(rankings['defenders_by_value'][:15], 1):
        print(f"{i:<5} {player['name']:<20} £{player['price']:.1f}m    "
              f"{player['total_dc_points']:<8} {player['dc_points_per_million']:.2f}       "
              f"{player['selected_by_percent']}%")

    # Value Midfielders
    print("\n💰 BEST VALUE MIDFIELDERS (DC Points per £m)\n")
    print(f"{'Rank':<5} {'Player':<20} {'Price':<8} {'DC Pts':<8} {'DC/£m':<10} {'Own %'}")
    print("-" * 75)

    for i, player in enumerate(rankings['midfielders_by_value'][:15], 1):
        print(f"{i:<5} {player['name']:<20} £{player['price']:.1f}m    "
              f"{player['total_dc_points']:<8} {player['dc_points_per_million']:.2f}       "
              f"{player['selected_by_percent']}%")

    # Elite DC Performers
    print("\n🌟 ELITE DC PERFORMERS (80%+ Consistency, Min 3 Games)\n")
    print(f"{'Player':<20} {'Pos':<5} {'Price':<8} {'DC %':<8} {'DC Pts':<8} {'Total Pts':<10} {'Pts/£m'}")
    print("-" * 85)

    elite = [p for p in rankings['overall_dc_performers'] if p['dc_consistency'] >= 80]
    for player in elite[:25]:
        print(f"{player['name']:<20} {player['position']:<5} £{player['price']:.1f}m    "
              f"{player['dc_consistency']:.1f}%    {player['total_dc_points']:<8} "
              f"{player['total_points']:<10} {player['points_per_million']:.2f}")

    print("\n" + "=" * 80)


def save_results(results: Dict[int, Dict], rankings: Dict[str, List[Dict]], output_dir: str = "data/analysis"):
    """Save analysis results to JSON files."""
    os.makedirs(output_dir, exist_ok=True)

    # Save full results
    results_file = os.path.join(output_dir, "dc_analysis_gw1-7.json")
    with open(results_file, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"✅ Full results saved: {results_file}")

    # Save rankings
    rankings_file = os.path.join(output_dir, "dc_rankings_gw1-7.json")
    with open(rankings_file, 'w') as f:
        json.dump(rankings, f, indent=2)
    print(f"✅ Rankings saved: {rankings_file}")

    # Save Ron's recommended picks (top candidates for GW8)
    recommendations = {
        'updated': '2025-10-05',
        'gameweeks_analyzed': '1-7',
        'top_defenders': rankings['defenders_by_consistency'][:10],
        'value_defenders': rankings['defenders_by_value'][:8],
        'top_midfielders': rankings['midfielders_by_consistency'][:10],
        'value_midfielders': rankings['midfielders_by_value'][:8],
        'elite_dc_performers': [
            p for p in rankings['overall_dc_performers']
            if p['dc_consistency'] >= 80
        ][:15]
    }

    rec_file = os.path.join(output_dir, "gw8_dc_recommendations.json")
    with open(rec_file, 'w') as f:
        json.dump(recommendations, f, indent=2)
    print(f"✅ GW8 recommendations saved: {rec_file}")


def main():
    """Main analysis pipeline."""
    print("\n🔍 RON CLANKER'S DC PERFORMANCE ANALYZER")
    print("Analyzing Gameweeks 1-7 (2025/26 Season)\n")

    # Fetch data
    bootstrap = fetch_bootstrap_data()

    # Check if we should run in sample mode (for testing)
    sample_mode = '--sample' in sys.argv
    sample_size = 100 if sample_mode else None

    # Analyze all players
    results = analyze_all_players(bootstrap, sample_size=sample_size)

    # Generate rankings
    rankings = generate_rankings(results)

    # Print to console
    print_rankings(rankings)

    # Save to files
    if not sample_mode:
        save_results(results, rankings)
    else:
        print("\n⚠️  SAMPLE MODE: Results not saved. Run without --sample to save.")

    print("\n✅ Analysis complete!")
    print("\nNext step: Run 'python scripts/select_gw8_squad.py' to build Ron's team\n")


if __name__ == "__main__":
    main()

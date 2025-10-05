#!/usr/bin/env python3
"""
Comprehensive Player Performance Analysis

Analyzes ALL relevant FPL statistics to identify optimal player selections:
- Defensive Contribution (DC) performance
- Expected Goals (xG) and Expected Assists (xA)
- Expected Goals Conceded (xGC) for defenders/keepers
- Form, ICT Index, Bonus Points System (BPS)
- Fixture difficulty analysis
- Value metrics (points per million, xGI per million)

Generic and reusable for any gameweek range in any season.

Usage:
    python scripts/analyze_player_performance.py --start-gw 1 --end-gw 7
    python scripts/analyze_player_performance.py --start-gw 1 --end-gw 10 --output data/analysis/gw10
"""

import sys
import os
from pathlib import Path
import argparse
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import requests
from typing import Dict, List, Optional
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


def fetch_fixtures() -> List[Dict]:
    """Fetch all fixtures."""
    response = requests.get(f"{FPL_BASE_URL}/fixtures/")
    response.raise_for_status()
    return response.json()


def analyze_dc_performance(player: Dict, history: List[Dict], gw_range: range) -> Dict:
    """
    Analyze defensive contribution consistency.

    Args:
        player: Player bootstrap data
        history: Player's gameweek history
        gw_range: Range of gameweeks to analyze

    Returns:
        Dict with DC stats
    """
    position_type = player['element_type']

    # Filter to specified gameweeks where player actually played
    gw_history = [
        gw for gw in history
        if gw['round'] in gw_range and gw['minutes'] > 0
    ]

    if not gw_history:
        return {
            'weeks_played': 0,
            'dc_weeks': 0,
            'dc_consistency_pct': 0.0,
            'total_dc_points': 0,
            'avg_dc_per_gw': 0.0,
            'avg_tackles': 0.0,
            'avg_cbi': 0.0,
            'avg_recoveries': 0.0
        }

    weeks_played = len(gw_history)
    dc_weeks = sum(1 for gw in gw_history if gw.get('defensive_contribution', 0) > 0)
    total_dc_points = sum(gw.get('defensive_contribution', 0) for gw in gw_history)

    # Average defensive actions
    total_tackles = sum(gw.get('tackles', 0) for gw in gw_history)
    total_cbi = sum(gw.get('clearances_blocks_interceptions', 0) for gw in gw_history)
    total_recoveries = sum(gw.get('recoveries', 0) for gw in gw_history)

    return {
        'weeks_played': weeks_played,
        'dc_weeks': dc_weeks,
        'dc_consistency_pct': (dc_weeks / weeks_played * 100) if weeks_played > 0 else 0,
        'total_dc_points': total_dc_points,
        'avg_dc_per_gw': total_dc_points / weeks_played if weeks_played > 0 else 0,
        'avg_tackles': total_tackles / weeks_played if weeks_played > 0 else 0,
        'avg_cbi': total_cbi / weeks_played if weeks_played > 0 else 0,
        'avg_recoveries': total_recoveries / weeks_played if weeks_played > 0 else 0
    }


def analyze_attacking_metrics(player: Dict, history: List[Dict], gw_range: range) -> Dict:
    """
    Analyze attacking performance using xG, xA, and actual returns.

    Returns:
        Dict with attacking stats including xG, xA, goals, assists
    """
    gw_history = [
        gw for gw in history
        if gw['round'] in gw_range and gw['minutes'] > 0
    ]

    if not gw_history:
        return {
            'total_xg': 0.0,
            'total_xa': 0.0,
            'total_xgi': 0.0,
            'goals': 0,
            'assists': 0,
            'goal_involvements': 0,
            'avg_xg_per_90': 0.0,
            'avg_xa_per_90': 0.0,
            'xg_overperformance': 0.0,  # Actual goals - xG (elite finishers are positive)
            'xa_overperformance': 0.0,  # Actual assists - xA
            'total_minutes': 0
        }

    # Convert string fields to float
    total_xg = sum(float(gw.get('expected_goals', 0) or 0) for gw in gw_history)
    total_xa = sum(float(gw.get('expected_assists', 0) or 0) for gw in gw_history)
    goals = sum(gw.get('goals_scored', 0) for gw in gw_history)
    assists = sum(gw.get('assists', 0) for gw in gw_history)
    total_minutes = sum(gw.get('minutes', 0) for gw in gw_history)

    minutes_90s = total_minutes / 90.0 if total_minutes > 0 else 0

    return {
        'total_xg': round(total_xg, 2),
        'total_xa': round(total_xa, 2),
        'total_xgi': round(total_xg + total_xa, 2),
        'goals': goals,
        'assists': assists,
        'goal_involvements': goals + assists,
        'avg_xg_per_90': round(total_xg / minutes_90s, 2) if minutes_90s > 0 else 0.0,
        'avg_xa_per_90': round(total_xa / minutes_90s, 2) if minutes_90s > 0 else 0.0,
        'xg_overperformance': round(goals - total_xg, 2),
        'xa_overperformance': round(assists - total_xa, 2),
        'total_minutes': total_minutes
    }


def analyze_defensive_metrics(player: Dict, history: List[Dict], gw_range: range) -> Dict:
    """
    Analyze defensive performance using xGC and clean sheets.
    Relevant for goalkeepers and defenders.

    Returns:
        Dict with defensive stats
    """
    gw_history = [
        gw for gw in history
        if gw['round'] in gw_range and gw['minutes'] > 0
    ]

    if not gw_history:
        return {
            'total_xgc': 0.0,
            'clean_sheets': 0,
            'goals_conceded': 0,
            'xgc_overperformance': 0.0,  # xGC - actual GC (positive = better than expected)
            'clean_sheet_pct': 0.0,
            'avg_saves': 0.0  # For keepers
        }

    # Convert string fields to float
    total_xgc = sum(float(gw.get('expected_goals_conceded', 0) or 0) for gw in gw_history)
    clean_sheets = sum(1 for gw in gw_history if gw.get('clean_sheets', 0) > 0)
    goals_conceded = sum(gw.get('goals_conceded', 0) for gw in gw_history)
    total_saves = sum(gw.get('saves', 0) for gw in gw_history)

    weeks_played = len(gw_history)

    return {
        'total_xgc': round(total_xgc, 2),
        'clean_sheets': clean_sheets,
        'goals_conceded': goals_conceded,
        'xgc_overperformance': round(total_xgc - goals_conceded, 2),  # Positive is good
        'clean_sheet_pct': (clean_sheets / weeks_played * 100) if weeks_played > 0 else 0,
        'avg_saves': round(total_saves / weeks_played, 1) if weeks_played > 0 else 0.0
    }


def analyze_form_and_quality(player: Dict, history: List[Dict], gw_range: range) -> Dict:
    """
    Analyze form, consistency, and quality metrics.

    Returns:
        Dict with form, ICT, BPS stats
    """
    gw_history = [
        gw for gw in history
        if gw['round'] in gw_range and gw['minutes'] > 0
    ]

    if not gw_history:
        return {
            'avg_points_per_gw': 0.0,
            'total_points': 0,
            'avg_bps': 0.0,
            'total_bonus': 0,
            'avg_ict_index': 0.0,
            'points_variance': 0.0,  # Lower is more consistent
            'blanks': 0,
            'returns': 0  # Games with goals/assists
        }

    total_points = sum(gw.get('total_points', 0) for gw in gw_history)
    total_bps = sum(gw.get('bps', 0) for gw in gw_history)
    total_bonus = sum(gw.get('bonus', 0) for gw in gw_history)
    # ICT index is a string in API
    total_ict = sum(float(gw.get('ict_index', 0) or 0) for gw in gw_history)

    weeks_played = len(gw_history)

    # Count blanks (2 or fewer points) and returns (goals/assists)
    blanks = sum(1 for gw in gw_history if gw.get('total_points', 0) <= 2)
    returns = sum(1 for gw in gw_history
                 if gw.get('goals_scored', 0) > 0 or gw.get('assists', 0) > 0)

    # Calculate variance for consistency
    avg_points = total_points / weeks_played if weeks_played > 0 else 0
    if weeks_played > 1:
        variance = sum((gw.get('total_points', 0) - avg_points) ** 2 for gw in gw_history) / weeks_played
    else:
        variance = 0.0

    return {
        'avg_points_per_gw': round(avg_points, 2),
        'total_points': total_points,
        'avg_bps': round(total_bps / weeks_played, 1) if weeks_played > 0 else 0.0,
        'total_bonus': total_bonus,
        'avg_ict_index': round(total_ict / weeks_played, 1) if weeks_played > 0 else 0.0,
        'points_variance': round(variance, 2),
        'blanks': blanks,
        'returns': returns,
        'return_pct': round(returns / weeks_played * 100, 1) if weeks_played > 0 else 0.0
    }


def calculate_value_metrics(player: Dict, all_stats: Dict) -> Dict:
    """
    Calculate value-based metrics.

    Returns:
        Dict with price and value stats
    """
    price = player['now_cost'] / 10.0
    total_points = all_stats['form_quality']['total_points']
    total_xgi = all_stats['attacking']['total_xgi']

    # selected_by_percent is a string in API
    ownership = float(player.get('selected_by_percent', 0) or 0)

    return {
        'price': price,
        'total_points': total_points,
        'points_per_million': round(total_points / price, 2) if price > 0 else 0,
        'xgi_per_million': round(total_xgi / price, 2) if price > 0 else 0,
        'selected_by_pct': ownership,
        'transfers_in': player.get('transfers_in_event', 0),
        'transfers_out': player.get('transfers_out_event', 0),
        'net_transfers': player.get('transfers_in_event', 0) - player.get('transfers_out_event', 0)
    }


def analyze_player(player: Dict, start_gw: int, end_gw: int) -> Optional[Dict]:
    """
    Comprehensive analysis of a single player.

    Args:
        player: Player bootstrap data
        start_gw: Starting gameweek
        end_gw: Ending gameweek

    Returns:
        Dict with all analysis results, or None if error
    """
    try:
        player_data = fetch_player_history(player['id'])
        history = player_data.get('history', [])
        gw_range = range(start_gw, end_gw + 1)

        # Run all analyses
        dc_stats = analyze_dc_performance(player, history, gw_range)
        attacking_stats = analyze_attacking_metrics(player, history, gw_range)
        defensive_stats = analyze_defensive_metrics(player, history, gw_range)
        form_quality = analyze_form_and_quality(player, history, gw_range)

        # Combined stats
        all_stats = {
            'dc': dc_stats,
            'attacking': attacking_stats,
            'defensive': defensive_stats,
            'form_quality': form_quality
        }

        value_metrics = calculate_value_metrics(player, all_stats)

        return {
            'id': player['id'],
            'name': player['web_name'],
            'full_name': f"{player['first_name']} {player['second_name']}",
            'team': player['team'],
            'position': POSITION_MAP[player['element_type']],
            'position_id': player['element_type'],
            **dc_stats,
            **attacking_stats,
            **defensive_stats,
            **form_quality,
            **value_metrics,
            'status': player.get('status', 'a'),  # a=available, i=injured, etc.
            'chance_of_playing': player.get('chance_of_playing_next_round'),
        }

    except Exception as e:
        print(f"  ⚠️  Error analyzing {player['web_name']}: {e}")
        return None


def analyze_all_players(bootstrap: Dict, start_gw: int, end_gw: int, sample_size: Optional[int] = None) -> Dict[int, Dict]:
    """
    Analyze all players (or sample) comprehensively.

    Args:
        bootstrap: FPL bootstrap data
        start_gw: Starting gameweek
        end_gw: Ending gameweek
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

    print(f"\nAnalyzing {total} players for GW{start_gw}-{end_gw}...")

    for i, player in enumerate(players, 1):
        # Progress indicator
        if i % 50 == 0 or i == total:
            print(f"  Progress: {i}/{total} ({i/total*100:.1f}%)")

        result = analyze_player(player, start_gw, end_gw)
        if result and result['weeks_played'] > 0:  # Only include players who actually played
            results[player['id']] = result

    print(f"✅ Analysis complete: {len(results)} players with data\n")
    return results


def generate_rankings(results: Dict[int, Dict], min_games: int = 3) -> Dict[str, List[Dict]]:
    """
    Generate comprehensive rankings by multiple criteria.

    Args:
        results: Player analysis results
        min_games: Minimum games played to be included in rankings

    Returns:
        Dict with various ranking lists
    """
    rankings = {}

    # Filter for players with minimum games
    qualified = [p for p in results.values() if p['weeks_played'] >= min_games]

    # Group by position
    by_position = defaultdict(list)
    for player in qualified:
        by_position[player['position']].append(player)

    # === DEFENDERS ===
    defenders = by_position['DEF']

    # By DC consistency
    rankings['def_by_dc_consistency'] = sorted(
        defenders,
        key=lambda p: (p['dc_consistency_pct'], p['total_dc_points']),
        reverse=True
    )[:30]

    # By total points
    rankings['def_by_points'] = sorted(
        defenders,
        key=lambda p: p['total_points'],
        reverse=True
    )[:25]

    # By value (points per million)
    rankings['def_by_value'] = sorted(
        defenders,
        key=lambda p: p['points_per_million'],
        reverse=True
    )[:20]

    # By clean sheet potential (xGC + clean sheet %)
    rankings['def_by_clean_sheet_potential'] = sorted(
        [d for d in defenders if d['weeks_played'] >= min_games],
        key=lambda p: (p['clean_sheet_pct'], -p['total_xgc']),
        reverse=True
    )[:20]

    # === MIDFIELDERS ===
    midfielders = by_position['MID']

    # By DC consistency
    rankings['mid_by_dc_consistency'] = sorted(
        midfielders,
        key=lambda p: (p['dc_consistency_pct'], p['total_dc_points']),
        reverse=True
    )[:30]

    # By xGI (expected goal involvement)
    rankings['mid_by_xgi'] = sorted(
        midfielders,
        key=lambda p: p['total_xgi'],
        reverse=True
    )[:25]

    # By total points
    rankings['mid_by_points'] = sorted(
        midfielders,
        key=lambda p: p['total_points'],
        reverse=True
    )[:25]

    # By value
    rankings['mid_by_value'] = sorted(
        midfielders,
        key=lambda p: p['points_per_million'],
        reverse=True
    )[:20]

    # === FORWARDS ===
    forwards = by_position['FWD']

    # By xG (best finishers getting chances)
    rankings['fwd_by_xg'] = sorted(
        forwards,
        key=lambda p: p['total_xg'],
        reverse=True
    )[:20]

    # By total points
    rankings['fwd_by_points'] = sorted(
        forwards,
        key=lambda p: p['total_points'],
        reverse=True
    )[:20]

    # By value
    rankings['fwd_by_value'] = sorted(
        forwards,
        key=lambda p: p['points_per_million'],
        reverse=True
    )[:15]

    # === GOALKEEPERS ===
    keepers = by_position['GKP']

    # By total points
    rankings['gkp_by_points'] = sorted(
        keepers,
        key=lambda p: p['total_points'],
        reverse=True
    )[:15]

    # By clean sheet potential
    rankings['gkp_by_clean_sheets'] = sorted(
        keepers,
        key=lambda p: (p['clean_sheet_pct'], p['avg_saves']),
        reverse=True
    )[:15]

    # === CROSS-POSITION ===

    # Elite DC performers (80%+ consistency)
    rankings['elite_dc_performers'] = sorted(
        [p for p in qualified if p['dc_consistency_pct'] >= 80],
        key=lambda p: (p['dc_consistency_pct'], p['total_dc_points']),
        reverse=True
    )[:30]

    # Best overall value (any position)
    rankings['best_value_overall'] = sorted(
        qualified,
        key=lambda p: p['points_per_million'],
        reverse=True
    )[:30]

    # Most consistent (low variance, high points)
    rankings['most_consistent'] = sorted(
        [p for p in qualified if p['total_points'] >= 20],  # Minimum 20 points
        key=lambda p: (-p['points_variance'], p['avg_points_per_gw']),
    )[:25]

    # Elite finishers (xG overperformance)
    rankings['elite_finishers'] = sorted(
        [p for p in qualified if p['total_xg'] >= 1.0],  # Minimum 1.0 xG
        key=lambda p: p['xg_overperformance'],
        reverse=True
    )[:20]

    # Differential picks (low ownership, high points)
    rankings['differential_picks'] = sorted(
        [p for p in qualified if p['selected_by_pct'] < 10.0 and p['total_points'] >= 25],
        key=lambda p: p['points_per_million'],
        reverse=True
    )[:20]

    return rankings


def print_summary_stats(results: Dict[int, Dict], start_gw: int, end_gw: int):
    """Print high-level summary statistics."""
    total_players = len(results)
    by_position = defaultdict(list)
    for player in results.values():
        by_position[player['position']].append(player)

    print("=" * 80)
    print(f"COMPREHENSIVE PLAYER ANALYSIS - GAMEWEEKS {start_gw}-{end_gw}")
    print("=" * 80)
    print(f"\n📊 SUMMARY STATISTICS\n")
    print(f"Total players analyzed: {total_players}")
    print(f"  Goalkeepers: {len(by_position['GKP'])}")
    print(f"  Defenders: {len(by_position['DEF'])}")
    print(f"  Midfielders: {len(by_position['MID'])}")
    print(f"  Forwards: {len(by_position['FWD'])}")

    # DC stats
    dc_performers = [p for p in results.values() if p['total_dc_points'] > 0]
    elite_dc = [p for p in results.values() if p['dc_consistency_pct'] >= 80]

    print(f"\n💪 DEFENSIVE CONTRIBUTION")
    print(f"  Players earning DC points: {len(dc_performers)}")
    print(f"  Elite DC (80%+ consistency): {len(elite_dc)}")

    # Top scorers by position
    print(f"\n🌟 TOP SCORERS BY POSITION")
    for pos in ['GKP', 'DEF', 'MID', 'FWD']:
        if by_position[pos]:
            top = max(by_position[pos], key=lambda p: p['total_points'])
            print(f"  {pos}: {top['name']} - {top['total_points']} pts (£{top['price']}m)")

    print()


def print_key_rankings(rankings: Dict[str, List[Dict]]):
    """Print the most important rankings to console."""

    # Top defenders by DC
    print("\n" + "=" * 80)
    print("🛡️  TOP DEFENDERS - DC CONSISTENCY")
    print("=" * 80)
    print(f"\n{'Rank':<5} {'Player':<20} {'Price':<8} {'Played':<7} {'DC%':<8} {'CS%':<8} {'Pts':<6} {'Pts/£m'}")
    print("-" * 85)
    for i, p in enumerate(rankings['def_by_dc_consistency'][:15], 1):
        print(f"{i:<5} {p['name']:<20} £{p['price']:.1f}m    {p['weeks_played']:<7} "
              f"{p['dc_consistency_pct']:.1f}%    {p['clean_sheet_pct']:.1f}%    "
              f"{p['total_points']:<6} {p['points_per_million']:.2f}")

    # Top midfielders by xGI
    print("\n" + "=" * 80)
    print("⚡ TOP MIDFIELDERS - EXPECTED GOAL INVOLVEMENT (xGI)")
    print("=" * 80)
    print(f"\n{'Rank':<5} {'Player':<20} {'Price':<8} {'xGI':<7} {'G+A':<7} {'DC%':<8} {'Pts':<6} {'Pts/£m'}")
    print("-" * 85)
    for i, p in enumerate(rankings['mid_by_xgi'][:15], 1):
        print(f"{i:<5} {p['name']:<20} £{p['price']:.1f}m    {p['total_xgi']:<7} "
              f"{p['goal_involvements']:<7} {p['dc_consistency_pct']:.1f}%    "
              f"{p['total_points']:<6} {p['points_per_million']:.2f}")

    # Top forwards by xG
    print("\n" + "=" * 80)
    print("🎯 TOP FORWARDS - EXPECTED GOALS (xG)")
    print("=" * 80)
    print(f"\n{'Rank':<5} {'Player':<20} {'Price':<8} {'xG':<7} {'Goals':<7} {'xG Δ':<8} {'Pts':<6} {'Pts/£m'}")
    print("-" * 85)
    for i, p in enumerate(rankings['fwd_by_xg'][:12], 1):
        delta_symbol = "+" if p['xg_overperformance'] > 0 else ""
        print(f"{i:<5} {p['name']:<20} £{p['price']:.1f}m    {p['total_xg']:<7} "
              f"{p['goals']:<7} {delta_symbol}{p['xg_overperformance']:<8} "
              f"{p['total_points']:<6} {p['points_per_million']:.2f}")

    # Elite DC performers
    print("\n" + "=" * 80)
    print("💎 ELITE DC PERFORMERS (80%+ Consistency)")
    print("=" * 80)
    print(f"\n{'Player':<20} {'Pos':<5} {'Price':<8} {'DC%':<8} {'DC Pts':<8} {'Total':<7} {'Pts/£m'}")
    print("-" * 80)
    for p in rankings['elite_dc_performers'][:20]:
        print(f"{p['name']:<20} {p['position']:<5} £{p['price']:.1f}m    "
              f"{p['dc_consistency_pct']:.1f}%    {p['total_dc_points']:<8} "
              f"{p['total_points']:<7} {p['points_per_million']:.2f}")

    # Best value overall
    print("\n" + "=" * 80)
    print("💰 BEST VALUE PICKS (Points per £m)")
    print("=" * 80)
    print(f"\n{'Rank':<5} {'Player':<20} {'Pos':<5} {'Price':<8} {'Pts':<6} {'Pts/£m':<9} {'Own%'}")
    print("-" * 80)
    for i, p in enumerate(rankings['best_value_overall'][:20], 1):
        print(f"{i:<5} {p['name']:<20} {p['position']:<5} £{p['price']:.1f}m    "
              f"{p['total_points']:<6} {p['points_per_million']:<9} {p['selected_by_pct']}%")

    # Differential picks
    print("\n" + "=" * 80)
    print("🎲 DIFFERENTIAL PICKS (<10% ownership, strong points)")
    print("=" * 80)
    print(f"\n{'Player':<20} {'Pos':<5} {'Price':<8} {'Pts':<6} {'Pts/£m':<9} {'Own%'}")
    print("-" * 75)
    for p in rankings['differential_picks'][:15]:
        print(f"{p['name']:<20} {p['position']:<5} £{p['price']:.1f}m    "
              f"{p['total_points']:<6} {p['points_per_million']:<9} {p['selected_by_pct']}%")

    print("\n" + "=" * 80)


def save_results(results: Dict[int, Dict], rankings: Dict[str, List[Dict]],
                start_gw: int, end_gw: int, output_dir: str):
    """Save all analysis results to JSON files."""
    os.makedirs(output_dir, exist_ok=True)

    # Full results
    results_file = os.path.join(output_dir, f"player_analysis_gw{start_gw}-{end_gw}.json")
    with open(results_file, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"✅ Full analysis saved: {results_file}")

    # Rankings
    rankings_file = os.path.join(output_dir, f"rankings_gw{start_gw}-{end_gw}.json")
    with open(rankings_file, 'w') as f:
        json.dump(rankings, f, indent=2)
    print(f"✅ Rankings saved: {rankings_file}")

    # Recommendations for squad selection
    recommendations = {
        'generated': datetime.now().isoformat(),
        'gameweeks_analyzed': f'{start_gw}-{end_gw}',
        'elite_dc_performers': rankings['elite_dc_performers'][:15],
        'top_defenders': rankings['def_by_dc_consistency'][:10],
        'value_defenders': rankings['def_by_value'][:8],
        'top_midfielders_xgi': rankings['mid_by_xgi'][:10],
        'top_midfielders_dc': rankings['mid_by_dc_consistency'][:8],
        'value_midfielders': rankings['mid_by_value'][:8],
        'top_forwards': rankings['fwd_by_xg'][:8],
        'value_forwards': rankings['fwd_by_value'][:6],
        'top_keepers': rankings['gkp_by_points'][:6],
        'best_value_overall': rankings['best_value_overall'][:20],
        'differential_picks': rankings['differential_picks'][:15]
    }

    rec_file = os.path.join(output_dir, f"recommendations_gw{start_gw}-{end_gw}.json")
    with open(rec_file, 'w') as f:
        json.dump(recommendations, f, indent=2)
    print(f"✅ Recommendations saved: {rec_file}")


def main():
    """Main analysis pipeline."""
    parser = argparse.ArgumentParser(description='Comprehensive FPL player analysis')
    parser.add_argument('--start-gw', type=int, default=1, help='Starting gameweek (default: 1)')
    parser.add_argument('--end-gw', type=int, help='Ending gameweek (default: current GW - 1)')
    parser.add_argument('--sample', type=int, help='Sample size for testing (e.g., 100)')
    parser.add_argument('--output', type=str, default='data/analysis', help='Output directory')
    parser.add_argument('--min-games', type=int, default=3, help='Minimum games for rankings (default: 3)')

    args = parser.parse_args()

    print("\n🔍 RON CLANKER'S COMPREHENSIVE PLAYER ANALYZER\n")

    # Fetch data
    bootstrap = fetch_bootstrap_data()

    # Determine current gameweek if not specified
    if args.end_gw is None:
        current_gw = next((gw for gw in bootstrap['events'] if gw['is_current']), None)
        if current_gw:
            args.end_gw = current_gw['id'] - 1 if current_gw['finished'] else current_gw['id']
        else:
            args.end_gw = 1

    print(f"Analyzing gameweeks {args.start_gw} to {args.end_gw}\n")

    # Analyze all players
    results = analyze_all_players(bootstrap, args.start_gw, args.end_gw, sample_size=args.sample)

    # Generate rankings
    rankings = generate_rankings(results, min_games=args.min_games)

    # Print summary and key rankings
    print_summary_stats(results, args.start_gw, args.end_gw)
    print_key_rankings(rankings)

    # Save results
    if not args.sample:
        save_results(results, rankings, args.start_gw, args.end_gw, args.output)
    else:
        print("\n⚠️  SAMPLE MODE: Results not saved. Run without --sample to save.")

    print("\n✅ Analysis complete!\n")


if __name__ == "__main__":
    main()

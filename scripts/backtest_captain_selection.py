#!/usr/bin/env python3
"""
Captain Selection Backtest

Compares the old captain algorithm (max xP) against the new multi-factor
algorithm across GW8-29 using Ron's actual squad data and real outcomes.

Shows:
- What Ron actually picked vs what each algorithm would pick
- Points gained/lost from each approach
- Hit rate (% of weeks picking the optimal captain from squad)

Usage:
    python scripts/backtest_captain_selection.py
"""

import sqlite3
import sys
from pathlib import Path
import numpy as np

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

DB_PATH = project_root / 'data' / 'ron_clanker.db'


def get_squad_for_gw(conn, gw):
    """Get Ron's starting XI for a gameweek with all needed data."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            dt.player_id, dt.position, dt.is_captain, dt.is_vice_captain,
            p.web_name, p.element_type, p.team_id, p.now_cost,
            p.form, p.points_per_game, p.selected_by_percent,
            p.chance_of_playing_next_round, p.status,
            pgh.total_points, pgh.minutes
        FROM draft_team dt
        JOIN players p ON dt.player_id = p.id
        LEFT JOIN player_gameweek_history pgh
            ON dt.player_id = pgh.player_id AND pgh.gameweek = dt.for_gameweek
        WHERE dt.for_gameweek = ? AND dt.position <= 11
        ORDER BY dt.position
    """, (gw,))

    rows = cursor.fetchall()
    squad = []
    for r in rows:
        squad.append({
            'player_id': r[0],
            'position': r[1],
            'is_captain': bool(r[2]),
            'is_vice_captain': bool(r[3]),
            'web_name': r[4],
            'element_type': r[5],
            'team_id': r[6],
            'now_cost': r[7],
            'form': float(r[8] or 0),
            'points_per_game': float(r[9] or 0),
            'selected_by_percent': float(r[10] or 0),
            'chance_of_playing_next_round': r[11],
            'status': r[12] or 'a',
            'actual_points': r[13] or 0,
            'minutes': r[14] or 0,
        })
    return squad


def get_xp_for_player(conn, player_id, gameweek):
    """
    Estimate xP for a player at a given gameweek using data available BEFORE that GW.
    Uses form + points_per_game as a proxy for what the ML model would have predicted.
    """
    cursor = conn.cursor()
    # Get recent history (before this GW) for form estimate
    cursor.execute("""
        SELECT total_points, minutes
        FROM player_gameweek_history
        WHERE player_id = ? AND gameweek < ? AND gameweek >= ?
        ORDER BY gameweek DESC
        LIMIT 6
    """, (player_id, gameweek, max(1, gameweek - 6)))

    history = cursor.fetchall()
    if not history:
        return 2.0  # default

    points = [h[0] for h in history if h[1] and h[1] > 0]
    if not points:
        return 2.0

    # Weighted average (recent games weighted more)
    weights = [0.85 ** i for i in range(len(points))]
    weighted_xp = sum(p * w for p, w in zip(points, weights)) / sum(weights)

    return max(0.5, weighted_xp)


def old_algorithm_pick(squad):
    """Old algorithm: just pick max xP player."""
    if not squad:
        return None
    return max(squad, key=lambda p: p.get('xP', 0))


def new_algorithm_pick(squad, conn, gameweek):
    """
    New algorithm: multi-factor captain score.
    Mirrors _calculate_captain_score from manager_agent_v2.py.
    """
    if not squad:
        return None

    best_player = None
    best_score = -1

    for player in squad:
        score = calculate_captain_score(player, conn, gameweek)
        if score > best_score:
            best_score = score
            best_player = player

    return best_player


def calculate_captain_score(player, conn, gameweek):
    """
    Multi-factor captain scoring. Same logic as _calculate_captain_score
    in manager_agent_v2.py.
    """
    base_xp = player.get('xP', 0)
    if base_xp <= 0:
        return 0.0

    # 1. Position multiplier
    position = player.get('element_type', 3)
    position_multiplier = {
        1: 0.25,   # GK
        2: 0.70,   # DEF
        3: 1.00,   # MID
        4: 1.15,   # FWD
    }.get(position, 1.0)

    score = base_xp * position_multiplier

    # 2. Ceiling/variance bonus from recent history
    player_id = player.get('player_id')
    cursor = conn.cursor()

    cursor.execute("""
        SELECT total_points, minutes
        FROM player_gameweek_history
        WHERE player_id = ? AND gameweek < ?
        ORDER BY gameweek DESC
        LIMIT 6
    """, (player_id, gameweek))

    history = cursor.fetchall()
    if history and len(history) >= 3:
        points = [h[0] for h in history if h[1] and h[1] > 0]
        if points:
            std_pts = np.std(points) if len(points) > 1 else 0
            max_pts = max(points)

            ceiling_bonus = 0.3 * std_pts
            if max_pts >= 12:
                ceiling_bonus += 1.5
            elif max_pts >= 8:
                ceiling_bonus += 0.75
            elif max_pts >= 6:
                ceiling_bonus += 0.25

            score += ceiling_bonus

    # 3. Fixture difficulty and home advantage
    team_id = player.get('team_id')
    if team_id:
        cursor.execute("""
            SELECT team_h, team_a, team_h_difficulty, team_a_difficulty
            FROM fixtures
            WHERE event = ? AND (team_h = ? OR team_a = ?)
            LIMIT 1
        """, (gameweek, team_id, team_id))

        fixture = cursor.fetchone()
        if fixture:
            is_home = fixture[0] == team_id
            if is_home:
                fdr = fixture[2]  # team_h_difficulty
            else:
                fdr = fixture[3]  # team_a_difficulty

            fixture_multiplier = {
                1: 1.15, 2: 1.10, 3: 1.00, 4: 0.95, 5: 0.90,
            }.get(fdr, 1.0)

            score *= fixture_multiplier
            if is_home:
                score *= 1.05

    # 4. Availability adjustment
    chance = player.get('chance_of_playing_next_round')
    if chance is not None and chance < 75:
        score *= (chance / 100)

    # 5. Minutes reliability penalty
    cursor.execute("""
        SELECT minutes FROM player_gameweek_history
        WHERE player_id = ? AND gameweek < ?
        ORDER BY gameweek DESC LIMIT 3
    """, (player_id, gameweek))
    recent_mins = cursor.fetchall()
    if recent_mins and len(recent_mins) >= 2:
        avg_mins = sum(r[0] or 0 for r in recent_mins) / len(recent_mins)
        if avg_mins < 45:
            score *= 0.3
        elif avg_mins < 70:
            score *= 0.7

    return score


def run_backtest():
    conn = sqlite3.connect(str(DB_PATH))

    pos_map = {1: 'GK', 2: 'DEF', 3: 'MID', 4: 'FWD'}

    # Track results
    old_total = 0
    new_total = 0
    actual_total = 0
    optimal_total = 0
    old_optimal_count = 0
    new_optimal_count = 0
    actual_optimal_count = 0

    gw_results = []

    print("=" * 100)
    print("CAPTAIN SELECTION BACKTEST: Old (max xP) vs New (multi-factor)")
    print("=" * 100)
    print()
    print(f"{'GW':>3}  {'Actual Pick':>18} {'Pts':>4}  {'Old Algo':>18} {'Pts':>4}  "
          f"{'New Algo':>18} {'Pts':>4}  {'Optimal':>18} {'Pts':>4}")
    print("-" * 100)

    for gw in range(8, 30):
        squad = get_squad_for_gw(conn, gw)
        if not squad:
            continue

        # Enrich with xP estimates (proxy for ML predictions)
        for p in squad:
            p['xP'] = get_xp_for_player(conn, p['player_id'], gw)

        # Who did Ron actually captain?
        actual_captain = next((p for p in squad if p['is_captain']), None)
        if not actual_captain:
            continue

        # Old algorithm: max xP
        old_pick = old_algorithm_pick(squad)

        # New algorithm: multi-factor
        new_pick = new_algorithm_pick(squad, conn, gw)

        # Optimal: who actually scored the most?
        optimal = max(squad, key=lambda p: p['actual_points'])

        # Calculate captain points (doubled)
        actual_pts = actual_captain['actual_points'] * 2
        old_pts = old_pick['actual_points'] * 2 if old_pick else 0
        new_pts = new_pick['actual_points'] * 2 if new_pick else 0
        optimal_pts = optimal['actual_points'] * 2

        actual_total += actual_pts
        old_total += old_pts
        new_total += new_pts
        optimal_total += optimal_pts

        if actual_captain['player_id'] == optimal['player_id']:
            actual_optimal_count += 1
        if old_pick and old_pick['player_id'] == optimal['player_id']:
            old_optimal_count += 1
        if new_pick and new_pick['player_id'] == optimal['player_id']:
            new_optimal_count += 1

        # Format output
        def fmt(p, pts):
            pos = pos_map.get(p['element_type'], '?')
            return f"{p['web_name']}({pos})", pts

        act_name, act_pts = fmt(actual_captain, actual_pts)
        old_name, old_p = fmt(old_pick, old_pts) if old_pick else ("N/A", 0)
        new_name, new_p = fmt(new_pick, new_pts) if new_pick else ("N/A", 0)
        opt_name, opt_p = fmt(optimal, optimal_pts)

        # Highlight improvements
        new_vs_old = ""
        if new_p > old_p:
            new_vs_old = " ++"
        elif new_p < old_p:
            new_vs_old = " --"

        print(f"GW{gw:>2}  {act_name:>18} {act_pts:>4}  {old_name:>18} {old_p:>4}  "
              f"{new_name:>18} {new_p:>4}{new_vs_old:>3}  {opt_name:>18} {opt_p:>4}")

        gw_results.append({
            'gw': gw,
            'actual': actual_pts,
            'old': old_pts,
            'new': new_pts,
            'optimal': optimal_pts,
        })

    n_gws = len(gw_results)

    print("-" * 100)
    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Gameweeks analyzed: {n_gws}")
    print()
    print(f"{'Method':<25} {'Total Pts':>10} {'Avg/GW':>8} {'Optimal%':>10}")
    print("-" * 55)
    print(f"{'Ron Actual Picks':<25} {actual_total:>10} {actual_total/n_gws:>8.1f} {actual_optimal_count/n_gws*100:>9.0f}%")
    print(f"{'Old Algo (max xP)':<25} {old_total:>10} {old_total/n_gws:>8.1f} {old_optimal_count/n_gws*100:>9.0f}%")
    print(f"{'NEW Algo (multi-factor)':<25} {new_total:>10} {new_total/n_gws:>8.1f} {new_optimal_count/n_gws*100:>9.0f}%")
    print(f"{'Perfect Hindsight':<25} {optimal_total:>10} {optimal_total/n_gws:>8.1f} {'100':>9}%")
    print()

    # Show improvement
    improvement_vs_actual = new_total - actual_total
    improvement_vs_old = new_total - old_total

    print(f"New algo vs Ron's actual:  {improvement_vs_actual:+d} points ({improvement_vs_actual/n_gws:+.1f}/GW)")
    print(f"New algo vs old algo:      {improvement_vs_old:+d} points ({improvement_vs_old/n_gws:+.1f}/GW)")
    print(f"Ceiling (perfect picks):   {optimal_total - new_total:+d} points remaining gap")
    print()

    # Position analysis
    print("=" * 60)
    print("CAPTAIN PICKS BY POSITION (New Algorithm)")
    print("=" * 60)

    # Re-run to count positions
    pos_counts = {1: 0, 2: 0, 3: 0, 4: 0}
    for gw in range(8, 30):
        squad = get_squad_for_gw(conn, gw)
        if not squad:
            continue
        for p in squad:
            p['xP'] = get_xp_for_player(conn, p['player_id'], gw)
        pick = new_algorithm_pick(squad, conn, gw)
        if pick:
            pos_counts[pick['element_type']] = pos_counts.get(pick['element_type'], 0) + 1

    for pos_id, count in sorted(pos_counts.items()):
        print(f"  {pos_map[pos_id]}: {count} times ({count/n_gws*100:.0f}%)")

    print()
    print("Note: xP values are approximated from form history (not actual ML predictions).")
    print("Real-world improvement may differ but position/ceiling effects are reliable.")

    conn.close()


if __name__ == '__main__':
    run_backtest()

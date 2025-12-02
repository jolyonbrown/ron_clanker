#!/usr/bin/env python3
"""
Debug script to see exactly what features are being fed to the ML model
for Haaland vs Woltemade to understand why predictions are inverted.
"""

import sys
from pathlib import Path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from data.database import Database
from ml.prediction.features import FeatureEngineer
import pandas as pd

def main():
    db = Database()
    fe = FeatureEngineer(db)

    # Get player IDs
    haaland_id = db.execute_query("SELECT id FROM players WHERE web_name = 'Haaland'")[0]['id']
    woltemade_id = db.execute_query("SELECT id FROM players WHERE web_name = 'Woltemade'")[0]['id']
    pedro_id = db.execute_query("SELECT id FROM players WHERE web_name = 'João Pedro'")[0]['id']

    gameweek = 10

    print("=" * 80)
    print("FEATURE COMPARISON - GW10")
    print("=" * 80)

    for player_name, player_id in [('Haaland', haaland_id), ('Woltemade', woltemade_id), ('João Pedro', pedro_id)]:
        print(f"\n{player_name} (ID: {player_id})")
        print("-" * 80)

        # Get player stats
        player = db.execute_query("""
            SELECT
                element_type, now_cost, selected_by_percent,
                form, points_per_game, total_points,
                influence, creativity, threat, ict_index,
                team_id
            FROM players WHERE id = ?
        """, (player_id,))[0]

        # Get recent form
        form = fe.get_player_recent_form(player_id, gameweek, window=5)

        # Get fixture
        fixture = fe.get_fixture_difficulty(player['team_id'], gameweek)

        print(f"  Position: {player['element_type']}")
        print(f"  Price: £{player['now_cost'] / 10:.1f}m")
        print(f"  Ownership: {player['selected_by_percent']:.1f}%")
        print(f"  FPL Form: {player['form']}")
        print(f"  FPL PPG: {player['points_per_game']}")
        print(f"  Current ICT: {player['ict_index']}")
        print(f"    - Influence: {player['influence']}")
        print(f"    - Creativity: {player['creativity']}")
        print(f"    - Threat: {player['threat']}")
        print(f"\n  Form (last 5 GWs):")
        print(f"    - Avg Points: {form['avg_points']:.2f}")
        print(f"    - Avg Minutes: {form['avg_minutes']:.1f}")
        print(f"    - Avg Goals: {form['avg_goals']:.2f}")
        print(f"    - Avg ICT: {form['avg_ict_index']:.2f}")
        print(f"    - Form Trend: {form['form_trend']:.2f}")
        print(f"    - Games Played: {form['games_played']}")
        print(f"\n  Fixture (GW{gameweek}):")
        print(f"    - Difficulty: {fixture['difficulty']}")
        print(f"    - Home: {fixture['is_home']}")
        print(f"    - Opponent Strength: {fixture['opponent_strength']}")

        # Get the prediction
        pred = db.execute_query("""
            SELECT predicted_points
            FROM player_predictions
            WHERE player_id = ? AND gameweek = ?
        """, (player_id, gameweek))

        if pred:
            print(f"\n  ML PREDICTION: {pred[0]['predicted_points']:.2f} points")
        print()

if __name__ == '__main__':
    main()

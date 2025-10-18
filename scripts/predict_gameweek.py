#!/usr/bin/env python3
"""
Generate Player Predictions for Next Gameweek

Loads trained models and generates expected points predictions for all players.

Usage:
    python predict_gameweek.py --gw 8  # Predict for GW8
    python predict_gameweek.py --gw 8 --top 50  # Show only top 50 predicted players
    python predict_gameweek.py --gw 8 --position 3  # Only midfielders
"""

import sys
import logging
from pathlib import Path
from datetime import datetime
import argparse

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from data.database import Database
from ml.prediction.features import FeatureEngineer
from ml.prediction.model import PlayerPerformancePredictor

logger = logging.getLogger('ron_clanker.predict')


def main():
    parser = argparse.ArgumentParser(description='Generate player predictions for next gameweek')
    parser.add_argument('--gw', type=int, required=True, help='Gameweek to predict for')
    parser.add_argument('--version', type=str, default='latest', help='Model version to use (default: latest)')
    parser.add_argument('--top', type=int, help='Show only top N players (default: all)')
    parser.add_argument('--position', type=int, help='Filter by position (1=GK, 2=DEF, 3=MID, 4=FWD)')
    parser.add_argument('--save', action='store_true', help='Save predictions to database')

    args = parser.parse_args()

    start_time = datetime.now()

    print("\n" + "=" * 80)
    print(f"PLAYER PREDICTIONS FOR GW{args.gw}")
    print("=" * 80)
    print(f"Started: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Model version: {args.version}")

    logger.info(f"Prediction: Generating predictions for GW{args.gw}")

    # Initialize
    db = Database()
    feature_engineer = FeatureEngineer(db)
    predictor = PlayerPerformancePredictor(model_dir=project_root / 'models' / 'prediction')

    # Load trained models
    print("\n📦 Loading models...")
    predictor.load_models(version=args.version)

    # Get all players (or filtered by position)
    if args.position:
        players = db.execute_query("""
            SELECT id, web_name, element_type, team_id, now_cost, selected_by_percent
            FROM players
            WHERE element_type = ?
            ORDER BY id
        """, (args.position,))
    else:
        players = db.execute_query("""
            SELECT id, web_name, element_type, team_id, now_cost, selected_by_percent
            FROM players
            ORDER BY id
        """)

    if not players:
        print("❌ No players found")
        return 1

    print(f"Generating predictions for {len(players)} players...")

    # Generate predictions
    predictions = []

    for i, player in enumerate(players, 1):
        if i % 100 == 0:
            print(f"  Processed {i}/{len(players)}...")

        try:
            player_id = player['id']

            # Engineer features
            features = feature_engineer.engineer_features(player_id, args.gw)

            if not features:
                continue

            # Predict
            expected_points = predictor.predict(features)

            predictions.append({
                'player_id': player_id,
                'web_name': player['web_name'],
                'position': player['element_type'],
                'team_id': player['team_id'],
                'price': player['now_cost'] / 10.0,
                'ownership': float(player['selected_by_percent'] or 0),
                'expected_points': expected_points,
                'value': expected_points / (player['now_cost'] / 10.0) if player['now_cost'] > 0 else 0
            })

        except Exception as e:
            logger.error(f"Prediction: Error predicting for player {player['id']}: {e}")
            continue

    if not predictions:
        print("❌ No predictions generated")
        return 1

    # Sort by expected points
    predictions.sort(key=lambda x: x['expected_points'], reverse=True)

    # Display top predictions
    print("\n" + "=" * 80)
    print(f"TOP PREDICTIONS FOR GW{args.gw}")
    print("=" * 80)

    position_names = {1: 'GK', 2: 'DEF', 3: 'MID', 4: 'FWD'}

    limit = args.top if args.top else len(predictions)

    print(f"\n{'#':>3} {'Player':<20} {'Pos':<4} {'Price':>6} {'xPts':>6} {'Value':>6} {'Own%':>6}")
    print("-" * 80)

    for i, pred in enumerate(predictions[:limit], 1):
        pos_name = position_names.get(pred['position'], '?')
        print(
            f"{i:>3} {pred['web_name']:<20} {pos_name:<4} "
            f"£{pred['price']:>5.1f} {pred['expected_points']:>6.2f} "
            f"{pred['value']:>6.3f} {pred['ownership']:>6.1f}%"
        )

    # Save to database if requested
    if args.save:
        print("\n💾 Saving predictions to database...")

        saved = 0
        for pred in predictions:
            try:
                db.execute_update("""
                    INSERT OR REPLACE INTO player_predictions
                    (player_id, gameweek, predicted_points, created_at)
                    VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                """, (pred['player_id'], args.gw, pred['expected_points']))
                saved += 1
            except Exception as e:
                logger.error(f"Failed to save prediction for player {pred['player_id']}: {e}")

        print(f"✅ Saved {saved} predictions to database")

    # Summary stats by position
    print("\n" + "-" * 80)
    print("AVERAGE xPTS BY POSITION")
    print("-" * 80)

    for position in [1, 2, 3, 4]:
        pos_preds = [p for p in predictions if p['position'] == position]
        if pos_preds:
            avg_xpts = sum(p['expected_points'] for p in pos_preds) / len(pos_preds)
            print(f"{position_names[position]}: {avg_xpts:.2f} xPts (from {len(pos_preds)} players)")

    duration = (datetime.now() - start_time).total_seconds()

    print("\n" + "=" * 80)
    print("PREDICTIONS COMPLETE")
    print("=" * 80)
    print(f"Duration: {duration:.1f}s")
    print(f"Players predicted: {len(predictions)}")

    logger.info(
        f"Prediction: Complete - "
        f"Duration: {duration:.1f}s, "
        f"Predictions: {len(predictions)}, "
        f"GW: {args.gw}"
    )

    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\nPrediction cancelled.")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Prediction: Fatal error: {e}", exc_info=True)
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

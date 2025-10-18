#!/usr/bin/env python3
"""
Train Player Performance Prediction Models

Trains position-specific models using historical gameweek data.

Usage:
    python train_prediction_models.py --train-start 1 --train-end 6  # Train on GW1-6, test on GW7
    python train_prediction_models.py --full  # Use all available data for training
"""

import sys
import logging
from pathlib import Path
from datetime import datetime
from collections import defaultdict
import argparse
import numpy as np

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from data.database import Database
from ml.prediction.features import FeatureEngineer
from ml.prediction.model import PlayerPerformancePredictor

logger = logging.getLogger('ron_clanker.train_models')


def collect_training_data(db: Database, feature_engineer: FeatureEngineer,
                          train_start_gw: int, train_end_gw: int) -> dict:
    """
    Collect training data: features + targets for each gameweek.

    For each gameweek in the range, we:
    1. Engineer features based on data BEFORE that gameweek
    2. Get actual points scored IN that gameweek (target)

    Returns:
        Dict with features and targets organized by position
    """
    print(f"\nCollecting training data for GW{train_start_gw}-{train_end_gw}...")

    # Get all players
    players = db.execute_query("SELECT id, web_name, element_type FROM players")

    if not players:
        print("❌ No players found in database")
        return None

    # Organize by position
    features_by_position = defaultdict(list)
    targets_by_position = defaultdict(list)

    total_samples = 0

    for gw in range(train_start_gw, train_end_gw + 1):
        print(f"  Processing GW{gw}... ", end='', flush=True)

        samples_this_gw = 0

        for player in players:
            player_id = player['id']
            position = player['element_type']

            try:
                # Engineer features based on data BEFORE this gameweek
                features = feature_engineer.engineer_features(player_id, gw)

                if not features:
                    continue

                # Get actual points scored IN this gameweek (target)
                actual = db.execute_query("""
                    SELECT total_points
                    FROM player_gameweek_history
                    WHERE player_id = ? AND gameweek = ?
                """, (player_id, gw))

                if not actual:
                    continue  # Player didn't play this GW

                target = actual[0]['total_points']

                # Add to training data
                features_by_position[position].append(features)
                targets_by_position[position].append(target)

                samples_this_gw += 1

            except Exception as e:
                logger.error(f"Error processing player {player_id} GW{gw}: {e}")
                continue

        total_samples += samples_this_gw
        print(f"{samples_this_gw} samples")

    print(f"\nTotal training samples: {total_samples}")

    # Show breakdown by position
    position_names = {1: 'Goalkeepers', 2: 'Defenders', 3: 'Midfielders', 4: 'Forwards'}
    for position in [1, 2, 3, 4]:
        count = len(features_by_position[position])
        print(f"  {position_names[position]}: {count} samples")

    return {
        'features_by_position': dict(features_by_position),
        'targets_by_position': dict(targets_by_position)
    }


def main():
    parser = argparse.ArgumentParser(description='Train player performance prediction models')
    parser.add_argument('--train-start', type=int, default=1, help='Start gameweek for training (default: 1)')
    parser.add_argument('--train-end', type=int, default=6, help='End gameweek for training (default: 6)')
    parser.add_argument('--test-gw', type=int, help='Gameweek to test on (optional)')
    parser.add_argument('--full', action='store_true', help='Use all available data for training (no holdout)')
    parser.add_argument('--save', action='store_true', default=True, help='Save trained models (default: True)')
    parser.add_argument('--version', type=str, default='latest', help='Model version name (default: latest)')

    args = parser.parse_args()

    start_time = datetime.now()

    print("\n" + "=" * 80)
    print("PLAYER PERFORMANCE PREDICTION MODEL TRAINING")
    print("=" * 80)
    print(f"Started: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Training range: GW{args.train_start}-{args.train_end}")

    logger.info(f"ModelTraining: Starting training for GW{args.train_start}-{args.train_end}")

    # Initialize
    db = Database()
    feature_engineer = FeatureEngineer(db)
    predictor = PlayerPerformancePredictor(model_dir=project_root / 'models' / 'prediction')

    # Collect training data
    training_data = collect_training_data(
        db, feature_engineer,
        args.train_start, args.train_end
    )

    if not training_data:
        print("\n❌ No training data collected")
        return 1

    features_by_position = training_data['features_by_position']
    targets_by_position = training_data['targets_by_position']

    # Train models
    print("\n" + "-" * 80)
    print("TRAINING MODELS")
    print("-" * 80)

    metrics = predictor.train_all_models(features_by_position, targets_by_position)

    # Display metrics
    print("\n" + "-" * 80)
    print("MODEL PERFORMANCE")
    print("-" * 80)

    position_names = {1: 'Goalkeepers', 2: 'Defenders', 3: 'Midfielders', 4: 'Forwards'}

    for position, pos_metrics in metrics.items():
        print(f"\n{position_names[position]}:")
        print(f"  Train samples: {pos_metrics['train_samples']}")
        print(f"  Test samples: {pos_metrics['test_samples']}")
        print(f"  Test RMSE: {pos_metrics['test_rmse']:.2f} points")
        print(f"  Test MAE: {pos_metrics['test_mae']:.2f} points")
        print(f"  Test R²: {pos_metrics['test_r2']:.3f}")
        print(f"  CV RMSE: {pos_metrics['cv_rmse']:.2f} points")

    # Feature importance
    print("\n" + "-" * 80)
    print("TOP FEATURES BY POSITION")
    print("-" * 80)

    for position in [1, 2, 3, 4]:
        if position in metrics:
            print(f"\n{position_names[position]}:")
            top_features = predictor.get_feature_importance(position, top_n=10)
            for i, (feature, importance) in enumerate(top_features, 1):
                print(f"  {i}. {feature}: {importance:.4f}")

    # Optional: Test on holdout gameweek
    if args.test_gw:
        print("\n" + "-" * 80)
        print(f"TESTING ON GW{args.test_gw}")
        print("-" * 80)

        test_features_by_pos = defaultdict(list)
        test_targets_by_pos = defaultdict(list)

        players = db.execute_query("SELECT id, element_type FROM players")

        for player in players:
            player_id = player['id']
            position = player['element_type']

            features = feature_engineer.engineer_features(player_id, args.test_gw)
            if not features:
                continue

            actual = db.execute_query("""
                SELECT total_points FROM player_gameweek_history
                WHERE player_id = ? AND gameweek = ?
            """, (player_id, args.test_gw))

            if not actual:
                continue

            test_features_by_pos[position].append(features)
            test_targets_by_pos[position].append(actual[0]['total_points'])

        # Make predictions
        for position in [1, 2, 3, 4]:
            if position not in test_features_by_pos:
                continue

            predictions = predictor.predict_batch(test_features_by_pos[position])
            actuals = test_targets_by_pos[position]

            from sklearn.metrics import mean_squared_error, mean_absolute_error

            rmse = np.sqrt(mean_squared_error(actuals, predictions))
            mae = mean_absolute_error(actuals, predictions)

            print(f"{position_names[position]}: RMSE={rmse:.2f}, MAE={mae:.2f}")

    # Save models
    if args.save:
        print("\n" + "-" * 80)
        print("SAVING MODELS")
        print("-" * 80)
        predictor.save_models(version=args.version)
        print(f"✅ Models saved to models/prediction/ with version '{args.version}'")

    duration = (datetime.now() - start_time).total_seconds()

    print("\n" + "=" * 80)
    print("TRAINING COMPLETE")
    print("=" * 80)
    print(f"Duration: {duration:.1f}s")
    print(f"Models trained: {len(metrics)}")

    logger.info(
        f"ModelTraining: Complete - "
        f"Duration: {duration:.1f}s, "
        f"Models: {len(metrics)}, "
        f"Version: {args.version}"
    )

    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\nTraining cancelled.")
        sys.exit(1)
    except Exception as e:
        logger.error(f"ModelTraining: Fatal error: {e}", exc_info=True)
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

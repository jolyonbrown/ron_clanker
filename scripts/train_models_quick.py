#!/usr/bin/env python3
"""
Quick ML Model Training

Trains player performance prediction models using GW1-7 historical data.
Creates position-specific Gradient Boosting models.

Usage:
    python scripts/train_models_quick.py
    python scripts/train_models_quick.py --version gw8_v1
"""

import sys
from pathlib import Path
import argparse
from datetime import datetime
from collections import defaultdict

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from data.database import Database
from ml.prediction.features import FeatureEngineer
from ml.prediction.model import PlayerPerformancePredictor


def main():
    parser = argparse.ArgumentParser(description='Train ML prediction models')
    parser.add_argument('--version', type=str, default='latest',
                       help='Model version identifier (default: latest)')
    parser.add_argument('--train-gws', type=str, default=None,
                       help='Training gameweeks range (e.g., 1-8). If not specified, uses GW1 to latest finished GW')

    args = parser.parse_args()

    # Initialize DB to detect latest finished gameweek
    db = Database()

    # Auto-detect training range if not specified
    if args.train_gws is None:
        latest_finished = db.execute_query("""
            SELECT MAX(id) as max_gw
            FROM gameweeks
            WHERE finished = 1
        """)
        max_gw = latest_finished[0]['max_gw'] if latest_finished and latest_finished[0]['max_gw'] else 1
        args.train_gws = f'1-{max_gw}'
        print(f"Auto-detected training range: GW{args.train_gws} (latest finished gameweek)")

    # Continue with original args handling...

    start_time = datetime.now()

    print("\n" + "=" * 80)
    print("ML MODEL TRAINING")
    print("=" * 80)
    print(f"Started: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Training GWs: {args.train_gws}")
    print(f"Model version: {args.version}")
    print("=" * 80)

    # Parse gameweek range
    gw_start, gw_end = map(int, args.train_gws.split('-'))

    # db already initialized above for auto-detection
    feature_engineer = FeatureEngineer(db)
    predictor = PlayerPerformancePredictor(model_dir=project_root / 'models' / 'prediction')

    # Step 1: Collect training data
    print("\n📥 STEP 1: Collecting training data...")
    print(f"   Gameweeks: {gw_start} to {gw_end}")

    training_data = defaultdict(lambda: {'features': [], 'targets': []})

    total_samples = 0

    for gw in range(gw_start, gw_end + 1):
        print(f"\n   Processing GW{gw}...")

        # Get all players who played in this GW
        players_gw = db.execute_query("""
            SELECT DISTINCT player_id, total_points
            FROM player_gameweek_history
            WHERE gameweek = ? AND minutes > 0
        """, (gw,))

        if not players_gw:
            print(f"      ⚠️  No data for GW{gw}")
            continue

        gw_samples = 0

        for player_row in players_gw:
            player_id = player_row['player_id']
            actual_points = player_row['total_points']

            # Get player position
            player = db.execute_query("""
                SELECT element_type FROM players WHERE id = ?
            """, (player_id,))

            if not player:
                continue

            position = player[0]['element_type']

            # Engineer features for predicting THIS gameweek
            # (using data from BEFORE this gameweek)
            try:
                features = feature_engineer.engineer_features(
                    player_id=player_id,
                    gameweek=gw
                )

                if features:
                    training_data[position]['features'].append(features)
                    training_data[position]['targets'].append(actual_points)
                    gw_samples += 1
                    total_samples += 1

            except Exception as e:
                # Skip players with missing data
                continue

        print(f"      ✅ {gw_samples} samples from GW{gw}")

    print(f"\n   Total samples collected: {total_samples}")

    # Show breakdown by position
    print(f"\n   Samples by position:")
    position_names = {1: 'Goalkeepers', 2: 'Defenders', 3: 'Midfielders', 4: 'Forwards'}
    for pos in [1, 2, 3, 4]:
        count = len(training_data[pos]['features'])
        print(f"      {position_names[pos]}: {count} samples")

    # Step 2: Train models
    print("\n" + "-" * 80)
    print("📊 STEP 2: Training position-specific models...")
    print("-" * 80)

    all_metrics = predictor.train_all_models(
        features_by_position={pos: data['features'] for pos, data in training_data.items()},
        targets_by_position={pos: data['targets'] for pos, data in training_data.items()}
    )

    # Display metrics
    print("\n   Model Performance:")
    print(f"   {'Position':<15} {'Train Samples':<12} {'Test RMSE':<12} {'Test R²':<10}")
    print("   " + "-" * 60)

    for pos, metrics in all_metrics.items():
        pos_name = position_names[pos]
        ensemble_metrics = metrics['ensemble']
        print(f"   {pos_name:<15} {metrics['train_samples']:<12} "
              f"{ensemble_metrics['test_rmse']:<12.3f} {ensemble_metrics['test_r2']:<10.3f}")

    # Step 3: Save models
    print("\n" + "-" * 80)
    print("💾 STEP 3: Saving trained models...")
    print("-" * 80)

    predictor.save_models(version=args.version)
    print(f"   ✅ Models saved to: models/prediction/*_{args.version}.pkl")

    # Step 4: Quick validation
    print("\n" + "-" * 80)
    print("🔍 STEP 4: Validation - Sample predictions...")
    print("-" * 80)

    # Load the models we just saved
    predictor.load_models(version=args.version)

    # Make predictions for a few sample players
    sample_players = db.execute_query("""
        SELECT id, web_name, element_type, form, selected_by_percent
        FROM players
        WHERE status != 'u'
        ORDER BY CAST(selected_by_percent AS FLOAT) DESC
        LIMIT 10
    """)

    print(f"\n   Sample predictions for popular players (GW8):")
    print(f"   {'Player':<20} {'Pos':<5} {'Form':<6} {'Predicted xP':<15}")
    print("   " + "-" * 60)

    for player in sample_players:
        features = feature_engineer.engineer_features(
            player_id=player['id'],
            gameweek=8  # Predict next GW
        )

        if features:
            xp = predictor.predict(features)
            pos = ['', 'GKP', 'DEF', 'MID', 'FWD'][player['element_type']]
            form = player.get('form', 0) or 0

            print(f"   {player['web_name']:<20} {pos:<5} {form:<6.1f} {xp:<15.2f}")

    duration = (datetime.now() - start_time).total_seconds()

    print("\n" + "=" * 80)
    print("✅ TRAINING COMPLETE")
    print("=" * 80)
    print(f"Duration: {duration:.1f}s")
    print(f"Total samples: {total_samples}")
    print(f"Models trained: {len(all_metrics)}")
    print(f"Version: {args.version}")
    print("\nNext step: Run synthesis engine to generate predictions for all players")
    print(f"   python scripts/test_synthesis_engine.py --gw 9")

    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\nTraining cancelled.")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

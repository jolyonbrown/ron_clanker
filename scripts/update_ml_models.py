#!/usr/bin/env python3
"""
Weekly ML Model Update Pipeline

Updates all ML models with latest gameweek data:
1. Elo ratings - update after each completed GW
2. Captain optimizer - retrain periodically
3. xP ensemble - check if retraining needed

Run this after collect_post_gameweek_data.py when GW results are in.

Usage:
    python scripts/update_ml_models.py           # Update all
    python scripts/update_ml_models.py --elo     # Just Elo
    python scripts/update_ml_models.py --captain # Just captain model
    python scripts/update_ml_models.py --gw 14   # Specific gameweek
"""

import sys
import argparse
import logging
from pathlib import Path
from datetime import datetime

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('ml_update')


def get_current_gameweek():
    """Get current gameweek from database."""
    import sqlite3
    conn = sqlite3.connect('data/ron_clanker.db')
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id FROM gameweeks
        WHERE is_current = 1
        LIMIT 1
    """)
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None


def update_elo_ratings(gameweek: int = None):
    """Update Elo ratings with latest results."""
    from ml.elo_ratings import EloRatingSystem

    print("\n" + "=" * 60)
    print("UPDATING ELO RATINGS")
    print("=" * 60)

    elo = EloRatingSystem()

    if gameweek is None:
        gameweek = get_current_gameweek()
        if gameweek:
            gameweek -= 1  # Update for completed GW

    if not gameweek:
        print("Could not determine gameweek")
        return False

    print(f"Processing GW{gameweek} results...")
    matches = elo.update_after_gameweek(gameweek)

    if matches > 0:
        print(f"Updated {matches} match results")

        # Show top 5 teams
        rankings = elo.get_rankings()[:5]
        print("\nTop 5 teams by Elo:")
        for r in rankings:
            print(f"  {r['rank']}. {r['short_name']} - {r['overall_elo']:.0f}")

        return True
    else:
        print(f"No new matches to process for GW{gameweek}")
        return False


def update_captain_model(force: bool = False):
    """Retrain captain optimizer if needed."""
    from ml.captain_optimizer import CaptainOptimizer

    print("\n" + "=" * 60)
    print("UPDATING CAPTAIN OPTIMIZER")
    print("=" * 60)

    optimizer = CaptainOptimizer()
    model_path = optimizer.model_dir / f'captain_optimizer_{optimizer.MODEL_VERSION}.pkl'

    # Check if model exists and age
    should_retrain = force
    if not model_path.exists():
        print("No existing model found - training new model")
        should_retrain = True
    else:
        # Check model age - retrain weekly
        import os
        model_age_days = (datetime.now().timestamp() - os.path.getmtime(model_path)) / 86400
        if model_age_days > 7:
            print(f"Model is {model_age_days:.1f} days old - retraining")
            should_retrain = True
        else:
            print(f"Model is {model_age_days:.1f} days old - skipping (retrain weekly)")

    if should_retrain:
        print("Training captain optimizer...")
        metrics = optimizer.train()
        optimizer.save()

        print(f"\nTraining complete:")
        for k, v in metrics.items():
            if isinstance(v, float):
                print(f"  {k}: {v:.3f}")
            else:
                print(f"  {k}: {v}")

        return True

    return False


def check_xp_model_performance():
    """Check if xP models need retraining based on recent performance."""
    from ml.model_registry import ModelRegistry

    print("\n" + "=" * 60)
    print("CHECKING XP MODEL PERFORMANCE")
    print("=" * 60)

    registry = ModelRegistry()

    for pos in [1, 2, 3, 4]:
        pos_name = {1: 'GK', 2: 'DEF', 3: 'MID', 4: 'FWD'}[pos]
        model = registry.get_active_model('ensemble', 'xp_prediction', pos)

        if model:
            metrics = model.get('metrics', {})
            rmse = metrics.get('mean_rmse', 'N/A')
            samples = model.get('training_samples', 'N/A')
            print(f"  {pos_name}: v{model['version']} - RMSE: {rmse}, samples: {samples}")
        else:
            print(f"  {pos_name}: No active model!")

    print("\nNote: Run tune_hyperparameters.py + train_with_tuned_params.py to retrain")


def main():
    parser = argparse.ArgumentParser(description='Update ML models with latest data')
    parser.add_argument('--elo', action='store_true', help='Update Elo ratings only')
    parser.add_argument('--captain', action='store_true', help='Update captain model only')
    parser.add_argument('--check-xp', action='store_true', help='Check xP model performance')
    parser.add_argument('--gw', type=int, help='Specific gameweek to process')
    parser.add_argument('--force', action='store_true', help='Force retraining even if not needed')

    args = parser.parse_args()

    # Default: update all
    update_all = not (args.elo or args.captain or args.check_xp)

    print("\n" + "=" * 60)
    print("ML MODEL UPDATE PIPELINE")
    print("=" * 60)
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    start_time = datetime.now()

    if args.elo or update_all:
        update_elo_ratings(args.gw)

    if args.captain or update_all:
        update_captain_model(args.force)

    if args.check_xp or update_all:
        check_xp_model_performance()

    duration = (datetime.now() - start_time).total_seconds()

    print("\n" + "=" * 60)
    print("UPDATE COMPLETE")
    print("=" * 60)
    print(f"Duration: {duration:.1f} seconds")


if __name__ == '__main__':
    main()

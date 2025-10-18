#!/usr/bin/env python3
"""
Automated Model Retraining

Triggers model retraining when:
1. New gameweek data is available
2. Sufficient data has accumulated (retrain every 3-4 GWs)
3. Performance has degraded significantly

Usage:
    python auto_retrain_models.py --check  # Check if retraining needed
    python auto_retrain_models.py --force  # Force retrain regardless
"""

import sys
import argparse
import subprocess
from pathlib import Path
from datetime import datetime
import logging

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from data.database import Database
from learning.performance_tracker import PerformanceTracker

logger = logging.getLogger('ron_clanker.auto_retrain')


def check_retrain_needed(db: Database, tracker: PerformanceTracker) -> dict:
    """
    Determine if model retraining is needed.

    Returns:
        Dict with:
            - should_retrain: bool
            - reason: str explaining why
            - last_trained_gw: int
            - current_gw: int
    """
    # Get latest gameweek with data
    latest_gw_query = db.execute_query("""
        SELECT MAX(gameweek) as gw FROM player_gameweek_history
    """)

    if not latest_gw_query or not latest_gw_query[0]['gw']:
        return {'should_retrain': False, 'reason': 'No gameweek data available'}

    current_gw = latest_gw_query[0]['gw']

    # Check when models were last trained
    # Look at model file timestamps
    model_dir = project_root / 'models' / 'prediction'
    latest_model = model_dir / 'position_1_latest.pkl'

    if not latest_model.exists():
        return {
            'should_retrain': True,
            'reason': 'No trained models found',
            'current_gw': current_gw
        }

    # Check model age (days since last training)
    model_age_days = (datetime.now() - datetime.fromtimestamp(latest_model.stat().st_mtime)).days

    # Retrain every 3-4 gameweeks (roughly weekly)
    if model_age_days > 21:  # ~3 weeks
        return {
            'should_retrain': True,
            'reason': f'Models are {model_age_days} days old (retrain every ~21 days)',
            'current_gw': current_gw
        }

    # Check performance degradation
    recent_rmse = tracker.get_performance_trend('prediction_rmse', last_n_weeks=2)
    if len(recent_rmse) >= 2:
        # If RMSE increased significantly in last 2 weeks
        latest_rmse = recent_rmse[0]['value']
        previous_rmse = recent_rmse[1]['value']

        if latest_rmse > previous_rmse * 1.3:  # 30% worse
            return {
                'should_retrain': True,
                'reason': f'Performance degraded: RMSE {previous_rmse:.2f} → {latest_rmse:.2f}',
                'current_gw': current_gw
            }

    return {
        'should_retrain': False,
        'reason': f'Models recent ({model_age_days} days old) and performing well',
        'current_gw': current_gw
    }


def retrain_models(train_end_gw: int, dry_run: bool = False) -> bool:
    """
    Trigger model retraining.

    Args:
        train_end_gw: Use data up to this gameweek
        dry_run: If True, only show what would happen

    Returns:
        True if retraining succeeded
    """
    train_start_gw = max(1, train_end_gw - 6)  # Use last 6 GWs for training

    version_name = f'gw{train_end_gw}_retrain'

    print(f"\n{'[DRY RUN] ' if dry_run else ''}Retraining models...")
    print(f"  Training data: GW{train_start_gw}-{train_end_gw}")
    print(f"  Version: {version_name}")

    if dry_run:
        print("\n  (Dry run - no actual retraining)")
        return True

    # Run training script
    cmd = [
        'venv/bin/python',
        'scripts/train_prediction_models.py',
        '--train-start', str(train_start_gw),
        '--train-end', str(train_end_gw),
        '--save',
        '--version', version_name
    ]

    logger.info(f"AutoRetrain: Executing: {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd,
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=600  # 10 minute timeout
        )

        if result.returncode == 0:
            print("\n✅ Retraining completed successfully")
            logger.info(f"AutoRetrain: Retraining succeeded for version {version_name}")

            # Also save as 'latest'
            import shutil
            model_dir = project_root / 'models' / 'prediction'

            for pos in [1, 2, 3, 4]:
                old_file = model_dir / f'position_{pos}_{version_name}.pkl'
                new_file = model_dir / f'position_{pos}_latest.pkl'
                if old_file.exists():
                    shutil.copy(old_file, new_file)

            # Copy feature columns
            old_features = model_dir / f'feature_columns_{version_name}.pkl'
            new_features = model_dir / 'feature_columns_latest.pkl'
            if old_features.exists():
                shutil.copy(old_features, new_features)

            print(f"✅ Updated 'latest' models to version {version_name}")

            return True
        else:
            print(f"\n❌ Retraining failed with return code {result.returncode}")
            print(f"Error output:\n{result.stderr}")
            logger.error(f"AutoRetrain: Failed - {result.stderr}")
            return False

    except subprocess.TimeoutExpired:
        print("\n❌ Retraining timed out after 10 minutes")
        logger.error("AutoRetrain: Timeout after 600s")
        return False
    except Exception as e:
        print(f"\n❌ Retraining error: {e}")
        logger.error(f"AutoRetrain: Exception - {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description='Automated model retraining')
    parser.add_argument('--check', action='store_true', help='Check if retraining needed')
    parser.add_argument('--force', action='store_true', help='Force retrain regardless')
    parser.add_argument('--dry-run', action='store_true', help='Show what would happen without retraining')

    args = parser.parse_args()

    print("\n" + "=" * 80)
    print("AUTOMATED MODEL RETRAINING")
    print("=" * 80)

    logger.info("AutoRetrain: Starting")

    # Initialize
    db = Database()
    tracker = PerformanceTracker(db)

    # Check if retraining needed
    check_result = check_retrain_needed(db, tracker)

    print(f"\nCurrent Status:")
    print(f"  Latest gameweek: {check_result.get('current_gw', 'Unknown')}")
    print(f"  Should retrain: {check_result['should_retrain']}")
    print(f"  Reason: {check_result['reason']}")

    if args.check:
        # Just show status, don't retrain
        return 0

    # Decide whether to retrain
    if args.force or check_result['should_retrain']:
        if args.force:
            print("\n⚠️  Force flag set - retraining regardless of need")

        current_gw = check_result.get('current_gw')
        if not current_gw:
            print("\n❌ Cannot retrain: No gameweek data available")
            return 1

        success = retrain_models(current_gw, dry_run=args.dry_run)

        return 0 if success else 1
    else:
        print("\n✓ No retraining needed")
        return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\nRetraining cancelled.")
        sys.exit(1)
    except Exception as e:
        logger.error(f"AutoRetrain: Fatal error: {e}", exc_info=True)
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

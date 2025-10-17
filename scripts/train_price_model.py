#!/usr/bin/env python3
"""
Train Price Change Prediction Model

Trains ML model on historical snapshot data.
Optimized for Raspberry Pi 3 - lightweight, efficient.

Requirements:
- At least 7 days of snapshot data
- At least 20 historical price changes (for meaningful training)
"""

import sys
from pathlib import Path
from datetime import datetime
import json

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from models.price_change import PriceChangePredictor
from data.database import Database
import logging

logger = logging.getLogger('ron_clanker.price_training')


def main():
    """Train price prediction model."""

    start_time = datetime.now()

    print("\n" + "=" * 80)
    print("PRICE PREDICTION MODEL TRAINING")
    print("=" * 80)
    print(f"Time: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")

    db = Database()

    # Check if we have enough data
    print("\n" + "-" * 80)
    print("CHECKING DATA AVAILABILITY")
    print("-" * 80)

    snapshot_stats = db.execute_query("""
        SELECT
            COUNT(DISTINCT snapshot_date) as days,
            COUNT(*) as total_snapshots,
            MIN(snapshot_date) as first_date,
            MAX(snapshot_date) as last_date
        FROM player_transfer_snapshots
    """)

    if not snapshot_stats or snapshot_stats[0]['days'] < 7:
        days = snapshot_stats[0]['days'] if snapshot_stats else 0
        print(f"\n❌ Not enough snapshot data")
        print(f"   Current: {days} days")
        print(f"   Required: 7 days minimum")
        print(f"\n   Run daily snapshot collection for {7 - days} more days:")
        print(f"   venv/bin/python scripts/collect_price_snapshots.py")
        return 1

    stats = snapshot_stats[0]
    print(f"✓ Snapshot data: {stats['days']} days ({stats['total_snapshots']:,} snapshots)")
    print(f"  Date range: {stats['first_date']} to {stats['last_date']}")

    # Check price changes
    price_change_stats = db.execute_query("""
        SELECT COUNT(*) as count FROM price_changes
    """)

    change_count = price_change_stats[0]['count'] if price_change_stats else 0
    print(f"✓ Price changes: {change_count}")

    if change_count < 20:
        print(f"\n⚠️  Warning: Only {change_count} price changes")
        print(f"   Model may have low accuracy with limited data")
        print(f"   Recommended: 100+ price changes for good training")

        if change_count == 0:
            print(f"\n💡 Price changes are tracked automatically by monitor_prices.py")
            print(f"   They will accumulate as players' prices change")
            return 1

    # Load data for training
    print("\n" + "-" * 80)
    print("LOADING TRAINING DATA")
    print("-" * 80)

    snapshots = db.execute_query("""
        SELECT * FROM player_transfer_snapshots
        ORDER BY snapshot_date, player_id
    """)

    price_changes = db.execute_query("""
        SELECT * FROM price_changes
        ORDER BY detected_at
    """)

    print(f"Loaded {len(snapshots):,} snapshots")
    print(f"Loaded {len(price_changes)} price changes")

    # Initialize and train model
    print("\n" + "-" * 80)
    print("TRAINING MODEL")
    print("-" * 80)

    print("\nModel: Logistic Regression (optimized for RPi3)")
    print("Features: 12 (transfers, form, ownership, price, position)")
    print("Classes: 3 (Rise, Hold, Fall)")

    predictor = PriceChangePredictor(model_type="logistic")

    try:
        metrics = predictor.train(snapshots, price_changes, test_size=0.2)

        print("\n" + "-" * 80)
        print("TRAINING RESULTS")
        print("-" * 80)

        print(f"\nAccuracy: {metrics['accuracy']:.1%}")
        print(f"F1 Score: {metrics['f1_score']:.3f}")
        print(f"\nRise Prediction:")
        print(f"  Precision: {metrics['precision_rise']:.1%}")
        print(f"  Recall: {metrics['recall_rise']:.1%}")
        print(f"\nFall Prediction:")
        print(f"  Precision: {metrics['precision_fall']:.1%}")
        print(f"  Recall: {metrics['recall_fall']:.1%}")
        print(f"\nTraining time: {metrics['train_duration']:.1f} seconds")
        print(f"Train samples: {metrics['train_samples']}")
        print(f"Test samples: {metrics['test_samples']}")

        # Save model
        model_path = project_root / "models" / "price_model.pkl"
        predictor.save(str(model_path))
        print(f"\n✓ Model saved: {model_path}")

        # Store performance in database
        db.execute_update("""
            INSERT INTO price_model_performance (
                model_version, evaluation_date,
                accuracy, precision_rise, recall_rise,
                precision_fall, recall_fall, f1_score,
                training_samples, test_samples,
                notes
            ) VALUES (?, DATE('now'), ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            predictor.MODEL_VERSION,
            metrics['accuracy'],
            metrics['precision_rise'],
            metrics['recall_rise'],
            metrics['precision_fall'],
            metrics['recall_fall'],
            metrics['f1_score'],
            metrics['train_samples'],
            metrics['test_samples'],
            f"Trained on {stats['days']} days of data, {change_count} price changes"
        ))

        print("✓ Performance metrics saved to database")

        # Quality assessment
        print("\n" + "-" * 80)
        print("MODEL QUALITY ASSESSMENT")
        print("-" * 80)

        if metrics['accuracy'] >= 0.70:
            print("\n✅ GOOD - Model meets 70% accuracy target")
        elif metrics['accuracy'] >= 0.60:
            print("\n⚠️  ACCEPTABLE - Model above 60% but below target")
            print("   Collect more data to improve accuracy")
        else:
            print("\n❌ POOR - Model below 60% accuracy")
            print("   More data needed for reliable predictions")

        if metrics['precision_rise'] >= 0.65 and metrics['recall_rise'] >= 0.50:
            print("✅ Rise predictions are reliable")
        else:
            print("⚠️  Rise predictions need improvement")

        if metrics['precision_fall'] >= 0.65 and metrics['recall_fall'] >= 0.50:
            print("✅ Fall predictions are reliable")
        else:
            print("⚠️  Fall predictions need improvement")

        duration = (datetime.now() - start_time).total_seconds()

        print("\n" + "=" * 80)
        print("TRAINING COMPLETE")
        print("=" * 80)
        print(f"Total duration: {duration:.1f} seconds")
        print(f"Status: SUCCESS")
        print(f"\nNext step: Generate predictions")
        print(f"  venv/bin/python scripts/predict_price_changes.py")

        return 0

    except Exception as e:
        logger.error(f"Training error: {e}", exc_info=True)
        print(f"\n❌ Training failed: {e}")
        return 1


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\nTraining cancelled.")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        print(f"\n❌ Fatal error: {e}")
        sys.exit(1)

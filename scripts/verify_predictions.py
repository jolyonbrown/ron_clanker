#!/usr/bin/env python3
"""
Verify Price Prediction Accuracy

Compares predictions vs actual price changes to measure model performance.
Run after price changes occur (after 02:00 AM).
"""

import sys
from pathlib import Path
from datetime import datetime, date, timedelta

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from data.database import Database


def main():
    """Verify prediction accuracy."""

    print("\n" + "=" * 80)
    print("PRICE PREDICTION ACCURACY VERIFICATION")
    print("=" * 80)
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    db = Database()

    # Get recent predictions that should have outcomes by now
    yesterday = date.today() - timedelta(days=1)
    today = date.today()

    print(f"\nChecking predictions for: {yesterday} to {today}")

    # Get predictions
    predictions = db.execute_query("""
        SELECT
            pp.*,
            p.web_name
        FROM price_predictions pp
        JOIN players p ON pp.player_id = p.id
        WHERE pp.prediction_for_date >= ? AND pp.prediction_for_date <= ?
        AND pp.actual_change IS NULL
        ORDER BY pp.prediction_for_date, pp.player_id
    """, (yesterday, today))

    if not predictions:
        print(f"\n⚠️  No unverified predictions found for {yesterday} to {today}")
        return 0

    print(f"Found {len(predictions)} predictions to verify")

    # Get actual price changes
    price_changes = db.execute_query("""
        SELECT
            player_id,
            change_amount,
            detected_at
        FROM price_changes
        WHERE DATE(detected_at) >= ? AND DATE(detected_at) <= ?
    """, (yesterday, today))

    # Build lookup of actual changes
    actual_changes_map = {}
    for change in price_changes:
        player_id = change['player_id']
        change_direction = 1 if change['change_amount'] > 0 else -1
        detected_date = change['detected_at'][:10]

        if player_id not in actual_changes_map:
            actual_changes_map[player_id] = []

        actual_changes_map[player_id].append({
            'date': detected_date,
            'change': change_direction
        })

    print(f"Found {len(price_changes)} actual price changes")

    # Verify each prediction
    correct = 0
    incorrect = 0
    unresolved = 0

    for pred in predictions:
        player_id = pred['player_id']
        pred_date = pred['prediction_for_date']
        predicted_change = pred['predicted_change']

        # Check if player had actual change
        actual_change = 0  # Default: no change

        if player_id in actual_changes_map:
            for change in actual_changes_map[player_id]:
                if change['date'] == pred_date or change['date'] == str(date.today()):
                    actual_change = change['change']
                    break

        # Update database with outcome
        prediction_correct = (predicted_change == actual_change)

        db.execute_update("""
            UPDATE price_predictions
            SET actual_change = ?,
                prediction_correct = ?
            WHERE id = ?
        """, (actual_change, prediction_correct, pred['id']))

        if prediction_correct:
            correct += 1
        else:
            incorrect += 1

    # Calculate metrics
    total_verified = correct + incorrect
    accuracy = (correct / total_verified * 100) if total_verified > 0 else 0

    print("\n" + "-" * 80)
    print("VERIFICATION RESULTS")
    print("-" * 80)

    print(f"\nTotal predictions verified: {total_verified}")
    print(f"Correct: {correct}")
    print(f"Incorrect: {incorrect}")
    print(f"\nAccuracy: {accuracy:.1f}%")

    # Break down by prediction type
    rise_preds = db.execute_query("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN prediction_correct = 1 THEN 1 ELSE 0 END) as correct
        FROM price_predictions
        WHERE prediction_for_date >= ?
        AND predicted_change = 1
        AND actual_change IS NOT NULL
    """, (yesterday,))

    fall_preds = db.execute_query("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN prediction_correct = 1 THEN 1 ELSE 0 END) as correct
        FROM price_predictions
        WHERE prediction_for_date >= ?
        AND predicted_change = -1
        AND actual_change IS NOT NULL
    """, (yesterday,))

    if rise_preds and rise_preds[0]['total'] > 0:
        rise_acc = rise_preds[0]['correct'] / rise_preds[0]['total'] * 100
        print(f"\nRise predictions:")
        print(f"  Accuracy: {rise_acc:.1f}% ({rise_preds[0]['correct']}/{rise_preds[0]['total']})")

    if fall_preds and fall_preds[0]['total'] > 0:
        fall_acc = fall_preds[0]['correct'] / fall_preds[0]['total'] * 100
        print(f"\nFall predictions:")
        print(f"  Accuracy: {fall_acc:.1f}% ({fall_preds[0]['correct']}/{fall_preds[0]['total']})")

    # Show some examples
    print("\n" + "-" * 80)
    print("SAMPLE PREDICTIONS")
    print("-" * 80)

    correct_examples = db.execute_query("""
        SELECT
            pp.predicted_change,
            pp.actual_change,
            pp.confidence,
            p.web_name,
            p.team_name
        FROM price_predictions pp
        JOIN players p ON pp.player_id = p.id
        WHERE pp.prediction_for_date >= ?
        AND pp.prediction_correct = 1
        ORDER BY pp.confidence DESC
        LIMIT 5
    """, (yesterday,))

    if correct_examples:
        print("\n✅ Correct Predictions (Top 5 by confidence):")
        for ex in correct_examples:
            change_str = "RISE" if ex['predicted_change'] == 1 else "FALL" if ex['predicted_change'] == -1 else "HOLD"
            print(f"  • {ex['web_name']:20s} {change_str:5s} {ex['confidence']:.0%}")

    incorrect_examples = db.execute_query("""
        SELECT
            pp.predicted_change,
            pp.actual_change,
            pp.confidence,
            p.web_name,
            p.team_name
        FROM price_predictions pp
        JOIN players p ON pp.player_id = p.id
        WHERE pp.prediction_for_date >= ?
        AND pp.prediction_correct = 0
        ORDER BY pp.confidence DESC
        LIMIT 5
    """, (yesterday,))

    if incorrect_examples:
        print("\n❌ Incorrect Predictions (Top 5 by confidence):")
        for ex in incorrect_examples:
            pred_str = "RISE" if ex['predicted_change'] == 1 else "FALL" if ex['predicted_change'] == -1 else "HOLD"
            actual_str = "RISE" if ex['actual_change'] == 1 else "FALL" if ex['actual_change'] == -1 else "HOLD"
            print(f"  • {ex['web_name']:20s} Predicted: {pred_str:5s} | Actual: {actual_str:5s} | Conf: {ex['confidence']:.0%}")

    # Assessment
    print("\n" + "-" * 80)
    print("MODEL ASSESSMENT")
    print("-" * 80)

    if accuracy >= 70:
        print("\n✅ GOOD - Model meeting 70% target")
    elif accuracy >= 60:
        print("\n⚠️  ACCEPTABLE - Model above 60% but below target")
    else:
        print("\n❌ NEEDS IMPROVEMENT - Model below 60%")

    if total_verified < 50:
        print("⚠️  Small sample size - need more predictions to assess properly")

    print("\n" + "=" * 80)
    print("VERIFICATION COMPLETE")
    print("=" * 80)

    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\nVerification cancelled.")
        sys.exit(0)

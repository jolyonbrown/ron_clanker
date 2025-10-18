#!/usr/bin/env python3
"""
Post-Gameweek Performance Review

Runs after each gameweek completes to:
- Compare predictions vs actual results
- Analyze captain performance
- Track systematic biases
- Generate performance metrics
- Store learnings for future improvement

Usage:
    python post_gameweek_review.py --gw 8
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime
import logging

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from data.database import Database
from learning.performance_tracker import PerformanceTracker

logger = logging.getLogger('ron_clanker.post_gw_review')


def main():
    parser = argparse.ArgumentParser(description='Post-gameweek performance review')
    parser.add_argument('--gw', type=int, required=True, help='Completed gameweek number')
    parser.add_argument('--save-report', action='store_true', help='Save report to file')

    args = parser.parse_args()

    start_time = datetime.now()

    print("\n" + "=" * 80)
    print(f"POST-GAMEWEEK {args.gw} PERFORMANCE REVIEW")
    print("=" * 80)
    print(f"Started: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")

    logger.info(f"PostGWReview: Starting review for GW{args.gw}")

    # Initialize
    db = Database()
    tracker = PerformanceTracker(db)

    report_lines = []

    # 1. Prediction Accuracy
    print("\n" + "-" * 80)
    print("PREDICTION ACCURACY")
    print("-" * 80)

    metrics = tracker.compare_predictions_vs_actuals(args.gw)

    if 'error' not in metrics:
        print(f"\nOverall Performance:")
        print(f"  Predictions made: {metrics['total_predictions']}")
        print(f"  RMSE: {metrics['rmse']:.2f} points")
        print(f"  MAE: {metrics['mae']:.2f} points")
        print(f"  Mean Error: {metrics['mean_error']:.2f} points")
        print(f"  Bias: {metrics['bias']}")

        report_lines.extend([
            "\n" + "=" * 80,
            f"GW{args.gw} PERFORMANCE REVIEW",
            "=" * 80,
            "\nPREDICTION ACCURACY:",
            f"  Total predictions: {metrics['total_predictions']}",
            f"  RMSE: {metrics['rmse']:.2f} pts",
            f"  MAE: {metrics['mae']:.2f} pts",
            f"  Bias: {metrics['bias']}"
        ])

        # Position breakdown
        print(f"\nBy Position:")
        for pos, pos_metrics in metrics['accuracy_by_position'].items():
            print(f"  {pos:4s}: RMSE={pos_metrics['rmse']:.2f}, MAE={pos_metrics['mae']:.2f}, Bias={pos_metrics['bias']:.2f}")

            report_lines.append(f"  {pos}: RMSE={pos_metrics['rmse']:.2f}, MAE={pos_metrics['mae']:.2f}")

        # Store metrics
        tracker.store_performance_metrics(args.gw, {
            'prediction_rmse': metrics['rmse'],
            'prediction_mae': metrics['mae'],
            'prediction_bias': metrics['mean_error']
        })

    else:
        print(f"\n⚠️  {metrics['error']}")
        report_lines.append(f"\n⚠️  {metrics['error']}")

    # 2. Captain Performance
    print("\n" + "-" * 80)
    print("CAPTAIN PERFORMANCE")
    print("-" * 80)

    captain_analysis = tracker.analyze_captain_performance(args.gw)

    if 'error' not in captain_analysis:
        print(f"\nCaptain: {captain_analysis['captain_chosen']}")
        print(f"  Predicted: {captain_analysis['expected_points']:.2f} pts")
        print(f"  Actual: {captain_analysis['captain_points']} pts")
        print(f"  Error: {captain_analysis['prediction_error']:.2f} pts")

        report_lines.extend([
            "\nCAPTAIN PERFORMANCE:",
            f"  Chosen: {captain_analysis['captain_chosen']}",
            f"  Predicted: {captain_analysis['expected_points']:.2f} pts",
            f"  Actual: {captain_analysis['captain_points']} pts"
        ])

        if 'best_alternative' in captain_analysis:
            print(f"\nBest Alternative: {captain_analysis['best_alternative']} ({captain_analysis['best_alternative_points']} pts)")
            print(f"  Points left on table: {captain_analysis['points_left_on_table']} pts")

            report_lines.extend([
                f"  Best alternative: {captain_analysis['best_alternative']} ({captain_analysis['best_alternative_points']} pts)",
                f"  Missed opportunity: {captain_analysis['points_left_on_table']} pts"
            ])

    # 3. Systematic Biases
    print("\n" + "-" * 80)
    print("SYSTEMATIC BIAS ANALYSIS")
    print("-" * 80)

    biases = tracker.identify_systematic_biases(last_n_weeks=4)

    if 'error' not in biases:
        print(f"\nPosition-specific biases (last 4 GWs):")
        for pos, bias_data in biases['by_position'].items():
            print(f"  {pos:4s}: {bias_data['bias']:8s} (mean error: {bias_data['mean_error']:+.2f} pts, n={bias_data['sample_size']})")

        report_lines.append("\nSYSTEMATIC BIASES:")
        for pos, bias_data in biases['by_position'].items():
            report_lines.append(f"  {pos}: {bias_data['bias']} ({bias_data['mean_error']:+.2f} pts)")

        if biases['recommendations']:
            print(f"\n💡 Recommendations:")
            report_lines.append("\nRECOMMENDATIONS:")
            for rec in biases['recommendations']:
                print(f"  • {rec}")
                report_lines.append(f"  • {rec}")

    # 4. Performance Trends
    print("\n" + "-" * 80)
    print("PERFORMANCE TRENDS")
    print("-" * 80)

    rmse_trend = tracker.get_performance_trend('prediction_rmse', last_n_weeks=5)
    if rmse_trend:
        print(f"\nRMSE over last {len(rmse_trend)} gameweeks:")
        for gw_data in reversed(rmse_trend):
            print(f"  GW{gw_data['gameweek']}: {gw_data['value']:.2f}")

    duration = (datetime.now() - start_time).total_seconds()

    print("\n" + "=" * 80)
    print("REVIEW COMPLETE")
    print("=" * 80)
    print(f"Duration: {duration:.1f}s")

    # Save report if requested
    if args.save_report:
        output_dir = project_root / 'reports' / 'performance'
        output_dir.mkdir(parents=True, exist_ok=True)

        report_file = output_dir / f'gw{args.gw}_review_{start_time.strftime("%Y%m%d_%H%M%S")}.txt'
        with open(report_file, 'w') as f:
            f.write('\n'.join(report_lines))

        print(f"\n📄 Report saved to: {report_file}")

    logger.info(f"PostGWReview: Complete - Duration: {duration:.1f}s, GW: {args.gw}")

    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\nReview cancelled.")
        sys.exit(1)
    except Exception as e:
        logger.error(f"PostGWReview: Fatal error: {e}", exc_info=True)
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

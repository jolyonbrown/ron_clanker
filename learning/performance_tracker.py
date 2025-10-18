#!/usr/bin/env python3
"""
Performance Tracking and Learning Engine

Compares predictions vs actual outcomes to improve Ron's decision-making.
Tracks:
- Player point predictions vs actuals
- Captain choices (predicted vs actual)
- Transfer decisions (expected gain vs actual)
- Agent recommendations (which agents perform best)
"""

import logging
from typing import Dict, List, Optional
from datetime import datetime
import json

logger = logging.getLogger('ron_clanker.learning')


class PerformanceTracker:
    """
    Tracks Ron's decisions and learns from outcomes.
    """

    def __init__(self, database):
        """Initialize with database connection."""
        self.db = database
        logger.info("PerformanceTracker: Initialized")

    def record_prediction(self, player_id: int, gameweek: int, predicted_points: float):
        """
        Store a prediction for later comparison.

        Args:
            player_id: Player ID
            gameweek: Gameweek number
            predicted_points: ML model predicted points
        """
        try:
            self.db.execute_update("""
                INSERT OR REPLACE INTO player_predictions
                (player_id, gameweek, predicted_points, created_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            """, (player_id, gameweek, predicted_points))

            logger.debug(f"Recorded prediction: Player {player_id} GW{gameweek} = {predicted_points:.2f} xPts")

        except Exception as e:
            logger.error(f"Failed to record prediction: {e}")

    def record_decision(self, gameweek: int, decision_type: str,
                       decision_data: Dict, expected_value: float, reasoning: str):
        """
        Record a decision made by Ron.

        Args:
            gameweek: Gameweek number
            decision_type: 'captain', 'transfer', 'chip', 'formation'
            decision_data: JSON-serializable dict with decision details
            expected_value: Expected points/value from this decision
            reasoning: Why this decision was made
        """
        try:
            self.db.execute_update("""
                INSERT INTO decisions
                (gameweek, decision_type, decision_data, expected_value, reasoning, created_at)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (gameweek, decision_type, json.dumps(decision_data), expected_value, reasoning))

            logger.info(f"Recorded {decision_type} decision for GW{gameweek}: {expected_value:.2f} xPts")

        except Exception as e:
            logger.error(f"Failed to record decision: {e}")

    def compare_predictions_vs_actuals(self, gameweek: int) -> Dict:
        """
        Compare predicted vs actual points for a completed gameweek.

        Returns:
            Dict with performance metrics:
                - total_predictions: number of predictions made
                - mean_error: average prediction error
                - rmse: root mean squared error
                - mae: mean absolute error
                - bias: systematic over/under prediction
                - accuracy_by_position: breakdown by GK/DEF/MID/FWD
        """
        logger.info(f"Comparing predictions vs actuals for GW{gameweek}")

        # Get predictions with actual results
        results = self.db.execute_query("""
            SELECT
                pp.player_id,
                pp.predicted_points,
                pgh.total_points as actual_points,
                p.element_type as position,
                p.web_name
            FROM player_predictions pp
            JOIN player_gameweek_history pgh
                ON pp.player_id = pgh.player_id
                AND pp.gameweek = pgh.gameweek
            JOIN players p ON pp.player_id = p.id
            WHERE pp.gameweek = ?
        """, (gameweek,))

        if not results:
            logger.warning(f"No predictions found for GW{gameweek}")
            return {'error': 'No predictions available'}

        # Calculate errors
        errors = []
        absolute_errors = []
        squared_errors = []
        by_position = {1: [], 2: [], 3: [], 4: []}  # GK, DEF, MID, FWD

        for row in results:
            predicted = row['predicted_points']
            actual = row['actual_points']
            error = predicted - actual

            errors.append(error)
            absolute_errors.append(abs(error))
            squared_errors.append(error ** 2)

            by_position[row['position']].append({
                'predicted': predicted,
                'actual': actual,
                'error': error
            })

        import numpy as np

        metrics = {
            'gameweek': gameweek,
            'total_predictions': len(results),
            'mean_error': np.mean(errors),
            'rmse': np.sqrt(np.mean(squared_errors)),
            'mae': np.mean(absolute_errors),
            'bias': 'over' if np.mean(errors) > 0.5 else ('under' if np.mean(errors) < -0.5 else 'neutral'),
            'accuracy_by_position': {}
        }

        # Position-specific metrics
        pos_names = {1: 'GK', 2: 'DEF', 3: 'MID', 4: 'FWD'}
        for pos, pos_errors in by_position.items():
            if pos_errors:
                metrics['accuracy_by_position'][pos_names[pos]] = {
                    'count': len(pos_errors),
                    'rmse': np.sqrt(np.mean([e['error']**2 for e in pos_errors])),
                    'mae': np.mean([abs(e['error']) for e in pos_errors]),
                    'bias': np.mean([e['error'] for e in pos_errors])
                }

        logger.info(
            f"GW{gameweek} Performance: "
            f"RMSE={metrics['rmse']:.2f}, "
            f"MAE={metrics['mae']:.2f}, "
            f"Bias={metrics['bias']}"
        )

        return metrics

    def analyze_captain_performance(self, gameweek: int) -> Dict:
        """
        Analyze captain choice performance.

        Returns:
            Dict with:
                - captain_chosen: who was captained
                - captain_points: actual points scored
                - expected_points: what was predicted
                - best_alternative: who should have been captained
                - points_left_on_table: difference
        """
        # Get captain decision
        captain_decision = self.db.execute_query("""
            SELECT decision_data, expected_value
            FROM decisions
            WHERE gameweek = ? AND decision_type = 'captain'
            ORDER BY created_at DESC
            LIMIT 1
        """, (gameweek,))

        if not captain_decision:
            return {'error': 'No captain decision recorded'}

        decision_data = json.loads(captain_decision[0]['decision_data'])
        captain_id = decision_data.get('player_id')

        # Get captain's actual performance
        captain_actual = self.db.execute_query("""
            SELECT p.web_name, pgh.total_points
            FROM player_gameweek_history pgh
            JOIN players p ON pgh.player_id = p.id
            WHERE pgh.player_id = ? AND pgh.gameweek = ?
        """, (captain_id, gameweek))

        if not captain_actual:
            return {'error': 'Captain actual points not available'}

        # Find best alternative from Ron's team
        rons_team = self.db.execute_query("""
            SELECT p.id, p.web_name, pgh.total_points
            FROM my_team mt
            JOIN players p ON mt.player_id = p.id
            JOIN player_gameweek_history pgh ON p.id = pgh.player_id AND pgh.gameweek = ?
            WHERE mt.gameweek = ?
            ORDER BY pgh.total_points DESC
            LIMIT 1
        """, (gameweek, gameweek))

        result = {
            'gameweek': gameweek,
            'captain_chosen': captain_actual[0]['web_name'],
            'captain_points': captain_actual[0]['total_points'],
            'expected_points': captain_decision[0]['expected_value'],
            'prediction_error': captain_decision[0]['expected_value'] - captain_actual[0]['total_points']
        }

        if rons_team:
            best_alternative = rons_team[0]
            result['best_alternative'] = best_alternative['web_name']
            result['best_alternative_points'] = best_alternative['total_points']
            result['points_left_on_table'] = best_alternative['total_points'] - captain_actual[0]['total_points']

        return result

    def store_performance_metrics(self, gameweek: int, metrics: Dict):
        """
        Store performance metrics for tracking over time.

        Args:
            gameweek: Gameweek number
            metrics: Dict of metrics to store
        """
        for metric_name, value in metrics.items():
            if isinstance(value, (int, float)):
                try:
                    self.db.execute_update("""
                        INSERT INTO learning_metrics
                        (metric_name, gameweek, value, recorded_at)
                        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                    """, (metric_name, gameweek, value))
                except Exception as e:
                    logger.error(f"Failed to store metric {metric_name}: {e}")

        logger.info(f"Stored {len(metrics)} performance metrics for GW{gameweek}")

    def get_performance_trend(self, metric_name: str, last_n_weeks: int = 5) -> List[Dict]:
        """
        Get trend for a specific metric over recent gameweeks.

        Args:
            metric_name: Name of metric to track
            last_n_weeks: Number of recent gameweeks to include

        Returns:
            List of {gameweek, value} dicts
        """
        trend = self.db.execute_query("""
            SELECT gameweek, value
            FROM learning_metrics
            WHERE metric_name = ?
            ORDER BY gameweek DESC
            LIMIT ?
        """, (metric_name, last_n_weeks))

        return trend or []

    def identify_systematic_biases(self, last_n_weeks: int = 4) -> Dict:
        """
        Identify systematic prediction biases.

        Returns:
            Dict with identified biases:
                - overestimates: positions/situations we consistently overpredict
                - underestimates: positions/situations we consistently underpredict
                - recommendations: suggested corrections
        """
        logger.info(f"Analyzing systematic biases over last {last_n_weeks} gameweeks")

        # Get recent gameweeks
        recent_gws = self.db.execute_query("""
            SELECT DISTINCT gameweek
            FROM player_predictions
            WHERE gameweek >= (SELECT MAX(gameweek) - ? FROM player_predictions)
            ORDER BY gameweek DESC
        """, (last_n_weeks,))

        if not recent_gws:
            return {'error': 'Insufficient data for bias analysis'}

        gws = [row['gameweek'] for row in recent_gws]

        # Analyze by position
        biases = {'by_position': {}, 'by_price_range': {}, 'recommendations': []}

        pos_names = {1: 'GK', 2: 'DEF', 3: 'MID', 4: 'FWD'}

        for pos, pos_name in pos_names.items():
            errors = self.db.execute_query(f"""
                SELECT
                    pp.predicted_points - pgh.total_points as error
                FROM player_predictions pp
                JOIN player_gameweek_history pgh
                    ON pp.player_id = pgh.player_id AND pp.gameweek = pgh.gameweek
                JOIN players p ON pp.player_id = p.id
                WHERE pp.gameweek IN ({','.join('?' * len(gws))})
                AND p.element_type = ?
            """, (*gws, pos))

            if errors:
                import numpy as np
                mean_error = np.mean([e['error'] for e in errors])

                biases['by_position'][pos_name] = {
                    'mean_error': mean_error,
                    'sample_size': len(errors),
                    'bias': 'over' if mean_error > 0.5 else ('under' if mean_error < -0.5 else 'neutral')
                }

                if abs(mean_error) > 0.5:
                    direction = 'overestimating' if mean_error > 0 else 'underestimating'
                    biases['recommendations'].append(
                        f"{pos_name}: Consistently {direction} by {abs(mean_error):.2f} pts"
                    )

        return biases

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

    def analyze_by_price_bracket(self, last_n_weeks: int = 4) -> Dict:
        """
        Analyze prediction accuracy by player price bracket.

        Price brackets:
            - Premium: >= 10.0m
            - Mid-price: 6.0m - 9.9m
            - Budget: < 6.0m

        Returns:
            Dict with accuracy metrics by price bracket
        """
        logger.info(f"Analyzing prediction accuracy by price bracket over last {last_n_weeks} gameweeks")

        # Get recent gameweeks
        recent_gws = self.db.execute_query("""
            SELECT DISTINCT gameweek
            FROM player_predictions
            WHERE gameweek >= (SELECT MAX(gameweek) - ? FROM player_predictions)
            ORDER BY gameweek DESC
        """, (last_n_weeks,))

        if not recent_gws:
            return {'error': 'Insufficient data for price bracket analysis'}

        gws = [row['gameweek'] for row in recent_gws]

        # Get predictions with player prices
        results = self.db.execute_query(f"""
            SELECT
                pp.predicted_points - pgh.total_points as error,
                p.now_cost as price,
                p.element_type as position
            FROM player_predictions pp
            JOIN player_gameweek_history pgh
                ON pp.player_id = pgh.player_id AND pp.gameweek = pgh.gameweek
            JOIN players p ON pp.player_id = p.id
            WHERE pp.gameweek IN ({','.join('?' * len(gws))})
        """, tuple(gws))

        if not results:
            return {'error': 'No prediction data found'}

        import numpy as np

        # Categorize by price bracket
        brackets = {
            'premium': {'min': 100, 'max': float('inf'), 'errors': []},  # >= 10.0m (prices in 0.1m units)
            'mid_price': {'min': 60, 'max': 99, 'errors': []},           # 6.0m - 9.9m
            'budget': {'min': 0, 'max': 59, 'errors': []}                # < 6.0m
        }

        for row in results:
            price = row['price']
            error = row['error']

            for bracket_name, bracket in brackets.items():
                if bracket['min'] <= price <= bracket['max']:
                    bracket['errors'].append(error)
                    break

        analysis = {'by_bracket': {}, 'recommendations': []}

        for bracket_name, bracket in brackets.items():
            if bracket['errors']:
                errors = bracket['errors']
                mean_error = np.mean(errors)
                rmse = np.sqrt(np.mean([e**2 for e in errors]))
                mae = np.mean([abs(e) for e in errors])

                analysis['by_bracket'][bracket_name] = {
                    'sample_size': len(errors),
                    'mean_error': mean_error,
                    'rmse': rmse,
                    'mae': mae,
                    'bias': 'over' if mean_error > 0.5 else ('under' if mean_error < -0.5 else 'neutral')
                }

                if abs(mean_error) > 0.5:
                    direction = 'overestimating' if mean_error > 0 else 'underestimating'
                    analysis['recommendations'].append(
                        f"{bracket_name.replace('_', ' ').title()} players: Consistently {direction} by {abs(mean_error):.2f} pts"
                    )

        return analysis

    def get_learning_adjustments(self, last_n_weeks: int = 4) -> Dict:
        """
        Generate recommended adjustments based on accumulated learnings.

        Returns adjustments that can be applied to model predictions:
            - Position bias corrections
            - Price bracket corrections
            - Overall calibration factor

        These can be used by prediction models to adjust their outputs.
        """
        logger.info("Generating learning adjustments from recent performance")

        # Get position biases
        position_biases = self.identify_systematic_biases(last_n_weeks)
        price_biases = self.analyze_by_price_bracket(last_n_weeks)

        adjustments = {
            'position_corrections': {},
            'price_bracket_corrections': {},
            'applied_from_gw': None,
            'generated_at': datetime.now().isoformat()
        }

        # Position corrections (subtract bias from predictions)
        if 'by_position' in position_biases:
            for pos, data in position_biases['by_position'].items():
                if data['sample_size'] >= 20:  # Only apply with sufficient data
                    adjustments['position_corrections'][pos] = -data['mean_error']

        # Price bracket corrections
        if 'by_bracket' in price_biases:
            for bracket, data in price_biases['by_bracket'].items():
                if data['sample_size'] >= 30:  # Only apply with sufficient data
                    adjustments['price_bracket_corrections'][bracket] = -data['mean_error']

        return adjustments

    def save_learning_adjustments(self, adjustments: Dict, gameweek: int):
        """
        Save learning adjustments to database for use by prediction models.

        Args:
            adjustments: Dict from get_learning_adjustments()
            gameweek: Gameweek these adjustments should apply from
        """
        import json

        adjustments['applied_from_gw'] = gameweek

        try:
            self.db.execute_update("""
                INSERT INTO learning_metrics
                (metric_name, gameweek, value, recorded_at)
                VALUES ('learning_adjustments', ?, ?, CURRENT_TIMESTAMP)
            """, (gameweek, json.dumps(adjustments)))

            logger.info(f"Saved learning adjustments for GW{gameweek}")

        except Exception as e:
            logger.error(f"Failed to save learning adjustments: {e}")

    def get_active_adjustments(self) -> Dict:
        """
        Get the most recent learning adjustments for use in predictions.

        Returns:
            Dict with position and price bracket corrections
        """
        import json

        result = self.db.execute_query("""
            SELECT value
            FROM learning_metrics
            WHERE metric_name = 'learning_adjustments'
            ORDER BY gameweek DESC
            LIMIT 1
        """)

        if result:
            return json.loads(result[0]['value'])

        return {'position_corrections': {}, 'price_bracket_corrections': {}}

    # ==========================================
    # TRANSFER THRESHOLD LEARNING
    # ==========================================

    def analyze_transfer_performance(self, min_sample_size: int = 5) -> Dict:
        """
        Analyze historical transfer decisions to determine if thresholds need adjustment.

        Returns:
            Dict with analysis per position and recommended threshold adjustments
        """
        logger.info("Analyzing transfer performance for threshold learning")

        # Get all transfers with recorded expected and actual gains
        transfers = self.db.execute_query("""
            SELECT
                t.gameweek,
                t.player_in_id,
                t.expected_gain,
                t.actual_gain,
                p.element_type as position
            FROM transfers t
            JOIN players p ON t.player_in_id = p.id
            WHERE t.expected_gain IS NOT NULL
            AND t.actual_gain IS NOT NULL
        """)

        if not transfers:
            return {'error': 'No transfer data with expected/actual gains'}

        import numpy as np

        # Analyze overall and by position
        pos_names = {0: 'ALL', 1: 'GK', 2: 'DEF', 3: 'MID', 4: 'FWD'}
        analysis = {
            'total_transfers': len(transfers),
            'by_position': {},
            'recommendations': []
        }

        # Overall analysis
        all_errors = [t['actual_gain'] - t['expected_gain'] for t in transfers]
        analysis['overall'] = {
            'sample_size': len(transfers),
            'mean_error': np.mean(all_errors),
            'actual_avg': np.mean([t['actual_gain'] for t in transfers]),
            'expected_avg': np.mean([t['expected_gain'] for t in transfers])
        }

        # By position
        for pos in [1, 2, 3, 4]:
            pos_transfers = [t for t in transfers if t['position'] == pos]

            if len(pos_transfers) >= min_sample_size:
                errors = [t['actual_gain'] - t['expected_gain'] for t in pos_transfers]
                actual_gains = [t['actual_gain'] for t in pos_transfers]
                expected_gains = [t['expected_gain'] for t in pos_transfers]

                analysis['by_position'][pos_names[pos]] = {
                    'sample_size': len(pos_transfers),
                    'mean_error': np.mean(errors),
                    'actual_avg': np.mean(actual_gains),
                    'expected_avg': np.mean(expected_gains),
                    'position_id': pos
                }

                # Generate recommendations
                mean_error = np.mean(errors)
                if mean_error > 1.5:
                    # Consistently beating threshold - can lower it
                    analysis['recommendations'].append({
                        'position': pos_names[pos],
                        'position_id': pos,
                        'action': 'lower_threshold',
                        'adjustment': -0.25,
                        'reason': f'Transfers consistently outperform by {mean_error:.2f} pts'
                    })
                elif mean_error < -1.0:
                    # Consistently missing threshold - raise it
                    analysis['recommendations'].append({
                        'position': pos_names[pos],
                        'position_id': pos,
                        'action': 'raise_threshold',
                        'adjustment': 0.25,
                        'reason': f'Transfers consistently underperform by {abs(mean_error):.2f} pts'
                    })

        return analysis

    def update_learned_thresholds(self, analysis: Dict, current_thresholds: Dict = None):
        """
        Update learned_thresholds table based on transfer performance analysis.

        Args:
            analysis: Output from analyze_transfer_performance()
            current_thresholds: Current thresholds (defaults to 2.0 for all)
        """
        if current_thresholds is None:
            current_thresholds = {0: 2.0, 1: 2.0, 2: 2.0, 3: 2.0, 4: 2.0}

        pos_names = {0: 'ALL', 1: 'GK', 2: 'DEF', 3: 'MID', 4: 'FWD'}

        for rec in analysis.get('recommendations', []):
            pos_id = rec['position_id']
            adjustment = rec['adjustment']

            current = current_thresholds.get(pos_id, 2.0)
            new_threshold = max(1.0, min(4.0, current + adjustment))  # Clamp between 1.0 and 4.0

            # Get position analysis for sample size and mean error
            pos_name = pos_names[pos_id]
            pos_data = analysis.get('by_position', {}).get(pos_name, {})
            sample_size = pos_data.get('sample_size', 0)
            mean_error = pos_data.get('mean_error', 0)

            try:
                self.db.execute_update("""
                    INSERT OR REPLACE INTO learned_thresholds
                    (position, threshold_type, threshold_value, sample_size, mean_error, updated_at)
                    VALUES (?, 'min_gain_per_gw', ?, ?, ?, CURRENT_TIMESTAMP)
                """, (pos_id, new_threshold, sample_size, mean_error))

                logger.info(f"Updated {pos_name} threshold: {current:.2f} -> {new_threshold:.2f} "
                           f"(adjustment: {adjustment:+.2f})")

            except Exception as e:
                logger.error(f"Failed to update threshold for {pos_name}: {e}")

    def get_learned_thresholds(self) -> Dict[int, float]:
        """
        Get current learned thresholds for each position.

        Returns:
            Dict mapping position_id -> threshold value
            Defaults to 2.0 if no learned threshold exists
        """
        thresholds = self.db.execute_query("""
            SELECT position, threshold_value
            FROM learned_thresholds
            WHERE threshold_type = 'min_gain_per_gw'
        """)

        result = {0: 2.0, 1: 2.0, 2: 2.0, 3: 2.0, 4: 2.0}  # Defaults

        for row in thresholds or []:
            result[row['position']] = row['threshold_value']

        return result

    def run_threshold_learning(self, min_sample_size: int = 5) -> Dict:
        """
        Complete threshold learning cycle.

        1. Analyze transfer performance
        2. Generate recommendations
        3. Update learned thresholds
        4. Return summary

        Returns:
            Dict with learning results
        """
        logger.info("Running threshold learning cycle")

        # Get current thresholds
        current = self.get_learned_thresholds()

        # Analyze performance
        analysis = self.analyze_transfer_performance(min_sample_size)

        if 'error' in analysis:
            logger.warning(f"Threshold learning skipped: {analysis['error']}")
            return analysis

        # Update thresholds
        if analysis.get('recommendations'):
            self.update_learned_thresholds(analysis, current)
            logger.info(f"Applied {len(analysis['recommendations'])} threshold adjustments")
        else:
            logger.info("No threshold adjustments needed")

        # Get new thresholds
        new = self.get_learned_thresholds()

        return {
            'previous_thresholds': current,
            'new_thresholds': new,
            'analysis': analysis,
            'adjustments_made': len(analysis.get('recommendations', []))
        }

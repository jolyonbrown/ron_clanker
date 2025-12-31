#!/usr/bin/env python3
"""
Learning-Based Prediction Adjustments

Adjusts ML predictions based on historical prediction accuracy.

This applies learned corrections to reduce systematic biases:
1. Position-specific adjustments (e.g., if we over-predict GKs)
2. Price bracket adjustments (e.g., if we over-predict premiums)
3. Form-based corrections

These corrections are calculated by the learning/performance_tracker.py
and stored in learning_metrics after each gameweek review.
"""

import logging
import json
from typing import Dict, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class LearningAdjuster:
    """
    Adjust ML predictions based on historical bias analysis.

    Applies corrections learned from comparing predictions vs actuals.
    """

    POSITION_MAP = {1: 'GK', 2: 'DEF', 3: 'MID', 4: 'FWD'}

    def __init__(self, database):
        """
        Initialize adjuster.

        Args:
            database: Database instance for fetching learning data
        """
        self.db = database
        self._cached_adjustments = None
        self._cache_time = None
        logger.info("LearningAdjuster initialized")

    def get_active_adjustments(self, max_age_hours: int = 168) -> Dict:
        """
        Get the most recent learning adjustments.

        Args:
            max_age_hours: Max age of adjustments to use (default 1 week)

        Returns:
            Dict with position_corrections and price_bracket_corrections
        """
        # Use cache if recent
        if self._cached_adjustments and self._cache_time:
            cache_age = (datetime.now() - self._cache_time).total_seconds() / 3600
            if cache_age < 1:  # Refresh every hour
                return self._cached_adjustments

        # Fetch most recent adjustments from learning_metrics
        result = self.db.execute_query("""
            SELECT value, recorded_at, gameweek
            FROM learning_metrics
            WHERE metric_name = 'learning_adjustments'
            ORDER BY gameweek DESC, recorded_at DESC
            LIMIT 1
        """)

        if not result:
            logger.debug("No learning adjustments found in database")
            return self._default_adjustments()

        try:
            adjustments = json.loads(result[0]['value'])
            self._cached_adjustments = adjustments
            self._cache_time = datetime.now()

            logger.info(f"Loaded learning adjustments from GW{result[0]['gameweek']}")
            return adjustments

        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"Failed to parse learning adjustments: {e}")
            return self._default_adjustments()

    def _default_adjustments(self) -> Dict:
        """Return default (no adjustment) structure."""
        return {
            'position_corrections': {},
            'price_bracket_corrections': {}
        }

    def _get_price_bracket(self, price: float) -> str:
        """Categorize player into price bracket."""
        if price >= 10.0:
            return 'premium'
        elif price >= 6.0:
            return 'mid_price'
        else:
            return 'budget'

    def adjust_prediction(
        self,
        player_id: int,
        base_prediction: float,
        position: int = None,
        price: float = None
    ) -> float:
        """
        Adjust a single prediction based on learned biases.

        Args:
            player_id: Player ID
            base_prediction: Raw ML prediction
            position: Player position (1-4) if known
            price: Player price in millions if known

        Returns:
            Adjusted prediction
        """
        # Get player info if not provided
        if position is None or price is None:
            player = self.db.execute_query("""
                SELECT element_type, now_cost
                FROM players WHERE id = ?
            """, (player_id,))

            if player:
                position = player[0]['element_type']
                price = player[0]['now_cost'] / 10.0
            else:
                return base_prediction

        adjustments = self.get_active_adjustments()
        total_correction = 0.0

        # Apply position correction
        pos_name = self.POSITION_MAP.get(position)
        if pos_name and pos_name in adjustments.get('position_corrections', {}):
            pos_correction = adjustments['position_corrections'][pos_name]
            total_correction += pos_correction
            logger.debug(f"Position correction for {pos_name}: {pos_correction:+.2f}")

        # Apply price bracket correction
        bracket = self._get_price_bracket(price)
        if bracket in adjustments.get('price_bracket_corrections', {}):
            bracket_correction = adjustments['price_bracket_corrections'][bracket]
            total_correction += bracket_correction
            logger.debug(f"Price bracket correction for {bracket}: {bracket_correction:+.2f}")

        # Apply correction (subtract because positive bias means we over-predict)
        adjusted = base_prediction - total_correction

        # Ensure non-negative
        adjusted = max(0.0, adjusted)

        return adjusted

    def adjust_predictions(
        self,
        predictions: Dict[int, float],
        gameweek: int = None
    ) -> Dict[int, float]:
        """
        Adjust multiple predictions based on learned biases.

        Args:
            predictions: Dict mapping player_id -> predicted_points
            gameweek: Target gameweek (for logging)

        Returns:
            Adjusted predictions dict
        """
        adjustments = self.get_active_adjustments()

        if not adjustments.get('position_corrections') and not adjustments.get('price_bracket_corrections'):
            logger.info("No learning adjustments to apply")
            return predictions

        logger.info(f"Applying learning adjustments to {len(predictions)} predictions")

        adjusted = {}
        adjustments_applied = 0

        for player_id, base_pred in predictions.items():
            adj_pred = self.adjust_prediction(player_id, base_pred)
            adjusted[player_id] = adj_pred

            if adj_pred != base_pred:
                adjustments_applied += 1

        if adjustments_applied > 0:
            logger.info(f"Applied learning corrections to {adjustments_applied} predictions")

        return adjusted

    def get_adjustment_summary(self) -> str:
        """Get human-readable summary of active adjustments."""
        adjustments = self.get_active_adjustments()

        lines = ["Current Learning Adjustments:"]

        pos_corrections = adjustments.get('position_corrections', {})
        if pos_corrections:
            lines.append("  Position corrections:")
            for pos, correction in pos_corrections.items():
                direction = "subtract" if correction > 0 else "add"
                lines.append(f"    {pos}: {direction} {abs(correction):.2f} pts")

        bracket_corrections = adjustments.get('price_bracket_corrections', {})
        if bracket_corrections:
            lines.append("  Price bracket corrections:")
            for bracket, correction in bracket_corrections.items():
                direction = "subtract" if correction > 0 else "add"
                lines.append(f"    {bracket}: {direction} {abs(correction):.2f} pts")

        if not pos_corrections and not bracket_corrections:
            lines.append("  No corrections active")

        return "\n".join(lines)

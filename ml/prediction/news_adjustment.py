#!/usr/bin/env python3
"""
News-Aware Prediction Adjustments

Adjusts ML predictions based on news intelligence from Claude-processed sources.

This adds "football common sense" to pure statistical predictions by:
1. Penalizing injured/doubtful players
2. Boosting players with positive news
3. Preventing obviously bad decisions (like benching Haaland!)
4. Incorporating expert recommendations
"""

import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class NewsAwarePredictionAdjuster:
    """
    Adjust ML predictions based on news intelligence.

    Applies contextual adjustments to raw ML predictions.
    """

    def __init__(self, database):
        """
        Initialize adjuster.

        Args:
            database: Database instance for fetching news intelligence
        """
        self.db = database
        logger.info("NewsAwarePredictionAdjuster initialized")

    def adjust_predictions(
        self,
        predictions: Dict[int, float],
        gameweek: int
    ) -> Dict[int, float]:
        """
        Adjust ML predictions based on recent news intelligence.

        Args:
            predictions: Dict mapping player_id -> predicted_points
            gameweek: Target gameweek

        Returns:
            Adjusted predictions dict
        """
        logger.info(f"Adjusting predictions for GW{gameweek} based on news intelligence")

        # Fetch recent news intelligence from database
        news_intel = self._fetch_news_intelligence(hours=48)

        if not news_intel:
            logger.warning("No recent news intelligence found - returning unadjusted predictions")
            return predictions

        adjusted = predictions.copy()
        adjustments_made = []

        for player_id, base_prediction in predictions.items():
            # Get player details including FPL API availability
            player = self.db.execute_query("""
                SELECT id, web_name, now_cost, selected_by_percent, form,
                       status, chance_of_playing_next_round
                FROM players WHERE id = ?
            """, (player_id,))

            if not player:
                continue

            player_name = player[0]['web_name']
            price = player[0]['now_cost'] / 10.0
            form = float(player[0].get('form', 0) or 0)
            fpl_status = player[0].get('status', 'a')  # 'a' = available, 'u' = unavailable, 'i' = injured, 's' = suspended
            chance_of_playing = player[0].get('chance_of_playing_next_round')  # 0-100 or None

            # Check if we have news intelligence on this player
            # Try exact match first, then fuzzy match (surname)
            player_intel = news_intel.get(player_name)

            if not player_intel:
                # Try matching by surname in the intelligence
                for intel_name, intel_data in news_intel.items():
                    if player_name.lower() in intel_name.lower() or intel_name.lower() in player_name.lower():
                        player_intel = intel_data
                        break

            # PRIORITY 1: FPL API status (source of truth for availability)
            adjustment_factor = 1.0
            reason = []

            if fpl_status == 'u' or fpl_status == 's':
                # FPL says unavailable or suspended - override everything
                adjustment_factor *= 0.0
                reason.append(f"FPL API: {fpl_status.upper()} (unavailable)")

            elif fpl_status == 'i' and chance_of_playing is not None:
                # FPL says injured with percentage chance
                if chance_of_playing == 0:
                    adjustment_factor *= 0.1  # 90% penalty
                    reason.append(f"FPL API: 0% chance of playing")
                elif chance_of_playing <= 25:
                    adjustment_factor *= 0.3  # 70% penalty
                    reason.append(f"FPL API: {chance_of_playing}% chance")
                elif chance_of_playing <= 50:
                    adjustment_factor *= 0.6  # 40% penalty
                    reason.append(f"FPL API: {chance_of_playing}% chance")
                elif chance_of_playing <= 75:
                    adjustment_factor *= 0.8  # 20% penalty
                    reason.append(f"FPL API: {chance_of_playing}% chance")

            # PRIORITY 2: News intelligence (only if FPL API doesn't say unavailable)
            if player_intel and fpl_status not in ['u', 's']:
                # Only apply news adjustments if player is technically available per FPL

                if player_intel['status'] == 'INJURED' and fpl_status != 'i':
                    # News says injured but FPL doesn't - be cautious
                    confidence = player_intel['confidence']
                    adjustment_factor *= (1.0 - (0.3 * confidence))  # Up to 30% penalty
                    reason.append(f"News: INJURED (conf: {confidence:.0%}, FPL unconfirmed)")

                elif player_intel['status'] == 'DOUBT':
                    confidence = player_intel['confidence']
                    adjustment_factor *= (1.0 - (0.2 * confidence))  # Up to 20% penalty (less than before)
                    reason.append(f"News: DOUBT (conf: {confidence:.0%})")

                elif player_intel['status'] == 'SUSPENDED' and fpl_status != 's':
                    # News says suspended but FPL doesn't - probably wrong, ignore
                    logger.warning(f"News intel says {player_name} suspended but FPL API status={fpl_status} - ignoring news")
                    pass  # Don't apply suspension penalty if FPL doesn't confirm

                # Apply sentiment adjustments (only if available)
                if fpl_status == 'a':
                    if player_intel['sentiment'] == 'POSITIVE':
                        confidence = player_intel['confidence']
                        adjustment_factor *= (1.0 + (0.2 * confidence))  # Up to 20% boost
                        reason.append(f"POSITIVE news (conf: {confidence:.0%})")

                    elif player_intel['sentiment'] == 'NEGATIVE':
                        confidence = player_intel['confidence']
                        adjustment_factor *= (1.0 - (0.15 * confidence))  # Up to 15% penalty
                        reason.append(f"NEGATIVE news (conf: {confidence:.0%})")

            # Apply adjustment
            if adjustment_factor != 1.0:
                new_prediction = base_prediction * adjustment_factor
                adjusted[player_id] = new_prediction

                adjustments_made.append({
                    'player': player_name,
                    'base': round(base_prediction, 2),
                    'adjusted': round(new_prediction, 2),
                    'reason': ', '.join(reason)
                })

            # PREMIUM PLAYER FLOOR: Never predict too low for players > £12m with good form
            # This prevents benching Haaland-type disasters
            if price >= 12.0 and form >= 5.0:
                # Minimum prediction for premium players = 60% of form (e.g., form 12 → min 7.2 xP)
                premium_floor = form * 0.6

                if adjusted[player_id] < premium_floor:
                    old_prediction = adjusted[player_id]
                    adjusted[player_id] = premium_floor

                    adjustments_made.append({
                        'player': player_name,
                        'base': round(old_prediction, 2),
                        'adjusted': round(adjusted[player_id], 2),
                        'reason': f'PREMIUM FLOOR (£{price}m, form: {form})'
                    })

        # Log adjustments
        if adjustments_made:
            logger.info(f"Made {len(adjustments_made)} news-based adjustments:")
            for adj in adjustments_made[:10]:  # Log first 10
                logger.info(f"  {adj['player']}: {adj['base']} → {adj['adjusted']} ({adj['reason']})")

        return adjusted

    def _fetch_news_intelligence(self, hours: int = 48) -> Dict[str, Dict]:
        """
        Fetch recent news intelligence from database.

        Args:
            hours: Look back this many hours

        Returns:
            Dict mapping player names to intelligence dicts
        """
        cutoff = datetime.now() - timedelta(hours=hours)

        # Fetch news intelligence from decisions table
        intel_rows = self.db.execute_query("""
            SELECT decision_data, reasoning, created_at
            FROM decisions
            WHERE decision_type = 'news_intelligence'
              AND created_at > ?
            ORDER BY created_at DESC
        """, (cutoff.isoformat(),))

        if not intel_rows:
            return {}

        # Parse intelligence into dict
        intelligence = {}

        for row in intel_rows:
            try:
                # Parse decision_data: "Player: X, Status: Y, Sentiment: Z"
                data = row['decision_data']
                reasoning = row['reasoning']

                # Extract player name
                if 'Player: ' in data:
                    player_start = data.index('Player: ') + 8
                    player_end = data.index(',', player_start)
                    player_name = data[player_start:player_end].strip()
                else:
                    continue

                # Extract status
                if 'Status: ' in data:
                    status_start = data.index('Status: ') + 8
                    status_end = data.index(',', status_start)
                    status = data[status_start:status_end].strip()
                else:
                    status = 'NEUTRAL'

                # Extract sentiment
                if 'Sentiment: ' in data:
                    sentiment_start = data.index('Sentiment: ') + 11
                    sentiment = data[sentiment_start:].strip()
                else:
                    sentiment = 'NEUTRAL'

                # Extract confidence from reasoning
                confidence = 0.5
                if 'Confidence: ' in reasoning:
                    conf_start = reasoning.index('Confidence: ') + 12
                    conf_end = reasoning.index('%', conf_start)
                    confidence = float(reasoning[conf_start:conf_end]) / 100.0

                # Store intelligence (take most recent if multiple)
                if player_name not in intelligence:
                    intelligence[player_name] = {
                        'status': status,
                        'sentiment': sentiment,
                        'confidence': confidence,
                        'source': 'news_processor'
                    }

            except Exception as e:
                logger.warning(f"Error parsing news intelligence row: {e}")
                continue

        logger.info(f"Fetched news intelligence on {len(intelligence)} players from last {hours}h")
        return intelligence


def apply_news_adjustments(
    predictions: Dict[int, float],
    gameweek: int,
    database
) -> Dict[int, float]:
    """
    Convenience function to apply news adjustments to predictions.

    Args:
        predictions: Raw ML predictions
        gameweek: Target gameweek
        database: Database instance

    Returns:
        Adjusted predictions
    """
    adjuster = NewsAwarePredictionAdjuster(database)
    return adjuster.adjust_predictions(predictions, gameweek)

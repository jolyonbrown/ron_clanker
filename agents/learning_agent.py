"""
Learning Agent - "Ellie"

Tracks all decisions, compares predictions vs actual results, and improves
the system over time.

Ellie's Responsibilities:
- Log every decision to database
- Track prediction accuracy (expected vs actual points)
- Measure agent performance
- Identify systematic biases
- Calculate learning metrics
- Feed insights back to improve decision-making

This is how Ron gets smarter over time.
"""

import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
import json

from agents.base_agent import BaseAgent
from data.database import Database
from infrastructure.events import Event, EventType, EventPriority

logger = logging.getLogger(__name__)


class LearningAgent(BaseAgent):
    """
    Ellie - The Learning Agent

    Tracks Ron's decisions and learns from outcomes:

    Decision Tracking:
    - Team selections (squad, captain, formation)
    - Transfer decisions (who out, who in, cost)
    - Chip usage timing
    - Captain selections

    Performance Metrics:
    - Prediction accuracy (expected vs actual points)
    - Captain effectiveness (% of weeks captain scores well)
    - Transfer ROI (points gained vs cost)
    - Agent performance (which agents give best advice)

    Learning Outputs:
    - Weekly performance reports
    - Agent accuracy rankings
    - Systematic bias detection
    - Improvement recommendations

    Subscribes to:
    - TEAM_SELECTED: Log squad decisions
    - TRANSFER_EXECUTED: Log transfers
    - CAPTAIN_SELECTED: Log captain choices
    - CHIP_USED: Log chip timing
    - GAMEWEEK_COMPLETE: Calculate actual vs expected

    Publishes:
    - LEARNING_METRICS: Weekly performance insights
    """

    def __init__(self, database: Database = None):
        """
        Initialize Ellie.

        Args:
            database: Optional database instance
        """
        super().__init__(agent_name="ellie")
        self.db = database or Database()

        logger.info("Ellie (Learning Agent) initialized")

    async def setup_subscriptions(self) -> None:
        """Subscribe to relevant events."""
        await self.subscribe_to(EventType.TEAM_SELECTED)
        await self.subscribe_to(EventType.TRANSFER_EXECUTED)
        await self.subscribe_to(EventType.CAPTAIN_SELECTED)
        await self.subscribe_to(EventType.CHIP_USED)
        await self.subscribe_to(EventType.GAMEWEEK_COMPLETE)
        await self.subscribe_to(EventType.TRANSFER_RECOMMENDED)
        await self.subscribe_to(EventType.CHIP_RECOMMENDATION)

    async def handle_event(self, event: Event) -> None:
        """
        Handle incoming events.

        Args:
            event: The event to process
        """
        try:
            if event.event_type == EventType.TEAM_SELECTED:
                await self._log_team_selection(event)
            elif event.event_type == EventType.TRANSFER_EXECUTED:
                await self._log_transfer(event)
            elif event.event_type == EventType.CAPTAIN_SELECTED:
                await self._log_captain_selection(event)
            elif event.event_type == EventType.CHIP_USED:
                await self._log_chip_usage(event)
            elif event.event_type == EventType.GAMEWEEK_COMPLETE:
                await self._analyze_gameweek_performance(event)
            elif event.event_type == EventType.TRANSFER_RECOMMENDED:
                await self._log_agent_recommendation(event, 'hugo')
            elif event.event_type == EventType.CHIP_RECOMMENDATION:
                await self._log_agent_recommendation(event, 'terry')
        except Exception as e:
            logger.error(f"Ellie: Error handling event {event.event_type}: {e}")

    async def _log_team_selection(self, event: Event) -> None:
        """
        Log team selection decision.

        Args:
            event: TEAM_SELECTED event
        """
        gameweek = event.payload.get('gameweek')
        squad = event.payload.get('squad', [])
        reasoning = event.payload.get('reasoning', '')

        logger.info(f"Ellie: Logging team selection for GW{gameweek}")

        try:
            # Log decision to database
            self.db.execute_update(
                """
                INSERT INTO decisions (
                    gameweek, decision_type, decision_data, reasoning,
                    agent_source, created_at
                ) VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (
                    gameweek,
                    'team_selection',
                    json.dumps({'squad': squad}),
                    reasoning,
                    'ron'
                )
            )

            # Log individual player selections with expected points
            for player in squad:
                player_id = player.get('id')
                expected_points = player.get('predicted_points', 0)

                # Store prediction
                self.db.execute_update(
                    """
                    INSERT OR REPLACE INTO player_predictions (
                        player_id, gameweek, predicted_points,
                        prediction_confidence, created_at
                    ) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                    """,
                    (player_id, gameweek, expected_points, 0.7)
                )

            logger.info(f"Ellie: Logged {len(squad)} player selections")

        except Exception as e:
            logger.error(f"Ellie: Error logging team selection: {e}")

    async def _log_transfer(self, event: Event) -> None:
        """
        Log transfer decision.

        Args:
            event: TRANSFER_EXECUTED event
        """
        gameweek = event.payload.get('gameweek')
        player_out_id = event.payload.get('player_out_id')
        player_in_id = event.payload.get('player_in_id')
        cost = event.payload.get('cost', 0)
        reasoning = event.payload.get('reasoning', '')

        logger.info(f"Ellie: Logging transfer for GW{gameweek}")

        try:
            self.db.execute_update(
                """
                INSERT INTO transfers (
                    gameweek, player_out_id, player_in_id, transfer_cost,
                    is_free_transfer, reasoning, executed_at
                ) VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (
                    gameweek,
                    player_out_id,
                    player_in_id,
                    cost,
                    cost == 0,
                    reasoning
                )
            )

            logger.info("Ellie: Transfer logged to database")

        except Exception as e:
            logger.error(f"Ellie: Error logging transfer: {e}")

    async def _log_captain_selection(self, event: Event) -> None:
        """
        Log captain choice.

        Args:
            event: CAPTAIN_SELECTED event
        """
        gameweek = event.payload.get('gameweek')
        captain_id = event.payload.get('captain_id')
        reasoning = event.payload.get('reasoning', '')

        logger.info(f"Ellie: Logging captain selection for GW{gameweek}")

        try:
            self.db.execute_update(
                """
                INSERT INTO decisions (
                    gameweek, decision_type, decision_data, reasoning,
                    agent_source, created_at
                ) VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (
                    gameweek,
                    'captain_selection',
                    json.dumps({'captain_id': captain_id}),
                    reasoning,
                    'ron'
                )
            )

            logger.info("Ellie: Captain selection logged")

        except Exception as e:
            logger.error(f"Ellie: Error logging captain: {e}")

    async def _log_chip_usage(self, event: Event) -> None:
        """
        Log chip usage.

        Args:
            event: CHIP_USED event
        """
        gameweek = event.payload.get('gameweek')
        chip_name = event.payload.get('chip_name')
        reasoning = event.payload.get('reasoning', '')

        logger.info(f"Ellie: Logging chip usage: {chip_name} in GW{gameweek}")

        try:
            # Log to chips_used table
            self.db.execute_update(
                """
                INSERT INTO chips_used (
                    chip_name, gameweek, chip_half, used_at
                ) VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (
                    chip_name,
                    gameweek,
                    1 if gameweek <= 19 else 2
                )
            )

            # Also log as decision
            self.db.execute_update(
                """
                INSERT INTO decisions (
                    gameweek, decision_type, decision_data, reasoning,
                    agent_source, created_at
                ) VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (
                    gameweek,
                    'chip_used',
                    json.dumps({'chip_name': chip_name}),
                    reasoning,
                    'terry'
                )
            )

            logger.info("Ellie: Chip usage logged")

        except Exception as e:
            logger.error(f"Ellie: Error logging chip usage: {e}")

    async def _log_agent_recommendation(
        self,
        event: Event,
        agent_name: str
    ) -> None:
        """
        Log agent recommendation for later performance tracking.

        Args:
            event: Recommendation event
            agent_name: Name of agent making recommendation
        """
        gameweek = event.payload.get('gameweek')

        logger.debug(f"Ellie: Logging {agent_name} recommendation for GW{gameweek}")

        try:
            self.db.execute_update(
                """
                INSERT INTO agent_performance (
                    agent_name, gameweek, recommendation_type,
                    recommendation_data, was_followed, recorded_at
                ) VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (
                    agent_name,
                    gameweek,
                    event.event_type.value,
                    json.dumps(event.payload),
                    None  # Will be determined later
                )
            )

        except Exception as e:
            logger.error(f"Ellie: Error logging agent recommendation: {e}")

    async def _analyze_gameweek_performance(self, event: Event) -> None:
        """
        Analyze completed gameweek performance.

        Compare predicted vs actual points, calculate metrics.

        Args:
            event: GAMEWEEK_COMPLETE event
        """
        gameweek = event.payload.get('gameweek')

        logger.info(f"Ellie: Analyzing GW{gameweek} performance")

        try:
            # Get all predictions for this gameweek
            predictions = self.db.execute_query(
                """
                SELECT p.player_id, p.predicted_points, pl.web_name, pl.total_points
                FROM player_predictions p
                JOIN players pl ON p.player_id = pl.id
                WHERE p.gameweek = ?
                """,
                (gameweek,)
            )

            # Calculate prediction errors
            total_error = 0.0
            count = 0

            for pred in predictions:
                predicted = pred['predicted_points']
                # Would get actual points from gameweek history
                # For now, use placeholder
                actual = 0  # TODO: Get from player_gameweek_history

                error = abs(predicted - actual)
                total_error += error
                count += 1

                # Update prediction with actual result
                self.db.execute_update(
                    """
                    UPDATE player_predictions
                    SET actual_points = ?, prediction_error = ?
                    WHERE player_id = ? AND gameweek = ?
                    """,
                    (actual, error, pred['player_id'], gameweek)
                )

            # Calculate average prediction error
            if count > 0:
                avg_error = total_error / count

                # Store learning metric
                self.db.execute_update(
                    """
                    INSERT INTO learning_metrics (
                        metric_name, gameweek, value, recorded_at
                    ) VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                    """,
                    ('prediction_error', gameweek, avg_error)
                )

                logger.info(f"Ellie: GW{gameweek} avg prediction error: {avg_error:.2f} pts")

            # Publish learning metrics event
            await self.publish_event(
                EventType.ANALYSIS_COMPLETED,
                payload={
                    'gameweek': gameweek,
                    'agent': 'ellie',
                    'metrics': {
                        'avg_prediction_error': avg_error if count > 0 else 0,
                        'predictions_tracked': count
                    },
                    'timestamp': datetime.now().isoformat()
                },
                priority=EventPriority.LOW
            )

        except Exception as e:
            logger.error(f"Ellie: Error analyzing gameweek performance: {e}")

    def get_agent_performance_summary(self) -> Dict[str, Any]:
        """
        Get performance summary for all agents.

        Returns:
            Dict with agent performance metrics
        """
        try:
            results = self.db.execute_query(
                """
                SELECT agent_name,
                       COUNT(*) as total_recommendations,
                       SUM(CASE WHEN was_followed = 1 THEN 1 ELSE 0 END) as followed,
                       AVG(accuracy_score) as avg_accuracy
                FROM agent_performance
                GROUP BY agent_name
                ORDER BY avg_accuracy DESC
                """
            )

            summary = {}
            for row in results:
                summary[row['agent_name']] = {
                    'total_recommendations': row['total_recommendations'],
                    'followed': row['followed'],
                    'avg_accuracy': row['avg_accuracy']
                }

            return summary

        except Exception as e:
            logger.error(f"Ellie: Error getting agent summary: {e}")
            return {}

    def get_weekly_learning_report(self, gameweek: int) -> str:
        """
        Generate weekly learning report.

        Args:
            gameweek: Gameweek to report on

        Returns:
            Formatted report text
        """
        try:
            # Get metrics for this gameweek
            metrics = self.db.execute_query(
                """
                SELECT metric_name, value
                FROM learning_metrics
                WHERE gameweek = ?
                ORDER BY recorded_at DESC
                """,
                (gameweek,)
            )

            report = f"Ellie's Learning Report - Gameweek {gameweek}\n"
            report += "=" * 50 + "\n\n"

            for metric in metrics:
                report += f"{metric['metric_name']}: {metric['value']:.2f}\n"

            # Get agent performance
            agent_summary = self.get_agent_performance_summary()

            if agent_summary:
                report += "\nAgent Performance:\n"
                for agent, stats in agent_summary.items():
                    report += f"  {agent}: {stats['total_recommendations']} recommendations\n"

            return report

        except Exception as e:
            logger.error(f"Ellie: Error generating report: {e}")
            return f"Error generating report: {e}"

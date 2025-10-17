"""
DC Analyst Agent - "Digger"

Analyzes Defensive Contribution (DC) performance across all players.
Identifies consistent DC earners and value opportunities.

2025/26 DC Scoring Rules:
- Defenders: 1 pt for every 5 combined blocks + interceptions + tackles
- Midfielders: 1 pt for every 6 combined CBI + tackles + recoveries

This is Ron's edge: most managers undervalue defensive work.
"""

import logging
from typing import Dict, List, Any
from collections import defaultdict

from agents.base_agent import BaseAgent
from agents.data_collector import DataCollector
from infrastructure.events import Event, EventType, EventPriority

logger = logging.getLogger(__name__)


class DCAnalyst(BaseAgent):
    """
    Digger - The Defensive Contribution Analyst

    Specializes in:
    - Identifying consistent DC point earners
    - Ranking players by DC value (DC points per £m)
    - Finding undervalued defensive workers
    - Tracking DC consistency week-over-week

    Subscribes to:
    - DATA_UPDATED: Triggers DC analysis when fresh data arrives

    Publishes:
    - DC_ANALYSIS_COMPLETED: Rankings and recommendations
    """

    def __init__(self, data_collector: DataCollector = None):
        """
        Initialize Digger.

        Args:
            data_collector: Optional data collector instance
        """
        super().__init__(agent_name="digger")
        self.data_collector = data_collector or DataCollector()

        # Analysis cache
        self._last_analysis: Dict[str, Any] = {}
        self._min_games_played = 3  # Minimum games for meaningful analysis

        logger.info("Digger (DC Analyst) initialized")

    async def setup_subscriptions(self) -> None:
        """Subscribe to relevant events."""
        await self.subscribe_to(EventType.DATA_UPDATED)
        await self.subscribe_to(EventType.ANALYSIS_REQUESTED)

    async def handle_event(self, event: Event) -> None:
        """
        Handle incoming events.

        Args:
            event: The event to process
        """
        if event.event_type == EventType.DATA_UPDATED:
            await self._handle_data_updated(event)
        elif event.event_type == EventType.ANALYSIS_REQUESTED:
            await self._handle_analysis_requested(event)

    async def _handle_data_updated(self, event: Event) -> None:
        """
        Handle DATA_UPDATED event by performing DC analysis.

        Args:
            event: DATA_UPDATED event with fresh player data
        """
        logger.info("Digger: Fresh data detected, analyzing DC performance...")

        try:
            # Perform analysis
            analysis = await self.analyze_dc_performance()

            # Cache results
            self._last_analysis = analysis

            # Publish results
            await self.publish_event(
                EventType.DC_ANALYSIS_COMPLETED,
                payload=analysis,
                priority=EventPriority.NORMAL,
                correlation_id=event.event_id
            )

            logger.info(
                f"Digger: DC analysis complete. "
                f"Found {len(analysis['defender_recommendations'])} defender targets, "
                f"{len(analysis['midfielder_recommendations'])} midfielder targets"
            )

        except Exception as e:
            logger.error(f"Digger: DC analysis failed: {e}", exc_info=True)
            await self.publish_event(
                EventType.NOTIFICATION_ERROR,
                {
                    'message': 'DC analysis failed',
                    'error': str(e)
                }
            )

    async def _handle_analysis_requested(self, event: Event) -> None:
        """
        Handle ANALYSIS_REQUESTED event.

        Args:
            event: ANALYSIS_REQUESTED event
        """
        analysis_type = event.payload.get('analysis_type')

        if analysis_type in ['dc', 'all']:
            logger.info("Digger: Analysis requested, performing DC analysis...")
            await self._handle_data_updated(event)

    async def analyze_dc_performance(self) -> Dict[str, Any]:
        """
        Perform full DC analysis on all players.

        Returns:
            Dict containing:
                - defender_rankings: Top defenders by DC consistency
                - midfielder_rankings: Top midfielders by DC consistency
                - defender_value_rankings: Best value defenders (DC/£m)
                - midfielder_value_rankings: Best value midfielders (DC/£m)
                - elite_dc_performers: Players with 80%+ DC consistency
        """
        # Get latest player data
        data = await self.data_collector.update_all_data()
        players = data['players']
        current_gw = data['current_gameweek']['id']

        logger.debug(f"Analyzing {len(players)} players for DC performance")

        # Analyze each player
        player_dc_stats = []

        for player in players:
            # Only analyze players with meaningful game time
            if player.get('minutes', 0) < (self._min_games_played * 60):
                continue

            stats = self._calculate_player_dc_stats(player, current_gw)
            if stats:
                player_dc_stats.append(stats)

        # Generate rankings by position
        rankings = self._generate_rankings(player_dc_stats)

        return {
            'gameweek': current_gw,
            'players_analyzed': len(player_dc_stats),
            'min_games_required': self._min_games_played,
            'defender_rankings': rankings['defenders_by_consistency'],
            'midfielder_rankings': rankings['midfielders_by_consistency'],
            'defender_value_rankings': rankings['defenders_by_value'],
            'midfielder_value_rankings': rankings['midfielders_by_value'],
            'elite_dc_performers': rankings['elite_dc_performers'],
            'defender_recommendations': rankings['defenders_by_consistency'][:10],
            'midfielder_recommendations': rankings['midfielders_by_consistency'][:8]
        }

    def _calculate_player_dc_stats(self, player: Dict, current_gw: int) -> Dict[str, Any]:
        """
        Calculate DC statistics for a single player.

        Args:
            player: Player data from FPL API
            current_gw: Current gameweek number

        Returns:
            Dict with DC stats, or None if insufficient data
        """
        position = player.get('element_type')
        minutes = player.get('minutes', 0)

        if minutes == 0:
            return None

        # Calculate games played (approximate from minutes)
        games_played = minutes / 90.0

        if games_played < self._min_games_played:
            return None

        # Get total points and estimate DC contribution
        # NOTE: FPL API doesn't provide detailed per-GW stats in bootstrap
        # We'll use BPS as a proxy for defensive work
        total_points = player.get('total_points', 0)
        bps = player.get('bps', 0)
        clean_sheets = player.get('clean_sheets', 0)

        # Estimate DC points based on BPS and position
        # Defenders with high BPS relative to attacking returns = defensive work
        goals = player.get('goals_scored', 0)
        assists = player.get('assists', 0)

        # Rough BPS estimates: goal ≈ 30 BPS, assist ≈ 20 BPS, clean sheet ≈ 12 BPS
        attacking_bps = (goals * 30) + (assists * 20) + (clean_sheets * 12 if position == 2 else 0)
        defensive_bps = max(0, bps - attacking_bps)

        # Estimate DC consistency (players with defensive_bps > threshold are likely DC earners)
        dc_threshold = 30 if position == 2 else 40  # Lower for defenders
        dc_consistency = min(100, (defensive_bps / games_played / dc_threshold) * 100)

        # Estimated DC points (very rough)
        estimated_dc_points = defensive_bps / 20  # Rough conversion

        price = player['now_cost'] / 10.0

        return {
            'id': player['id'],
            'name': player['web_name'],
            'team': player['team'],
            'position': ['GKP', 'DEF', 'MID', 'FWD'][position - 1],
            'position_id': position,
            'price': price,
            'total_points': total_points,
            'minutes': minutes,
            'games_played': games_played,
            'bps': bps,
            'defensive_bps': defensive_bps,
            'estimated_dc_points': estimated_dc_points,
            'dc_consistency': dc_consistency,
            'points_per_million': total_points / price if price > 0 else 0,
            'dc_value': estimated_dc_points / price if price > 0 else 0,
            'selected_by_percent': player.get('selected_by_percent', 0)
        }

    def _generate_rankings(self, player_stats: List[Dict]) -> Dict[str, List[Dict]]:
        """
        Generate rankings by position and criteria.

        Args:
            player_stats: List of player DC statistics

        Returns:
            Dict with various ranking lists
        """
        rankings = {}

        # Group by position
        by_position = defaultdict(list)
        for player in player_stats:
            pos = player['position']
            by_position[pos].append(player)

        # Defenders - ranked by DC consistency
        defenders = sorted(
            by_position['DEF'],
            key=lambda p: (p['dc_consistency'], p['defensive_bps']),
            reverse=True
        )
        rankings['defenders_by_consistency'] = defenders[:30]

        # Defenders - ranked by value (DC value per £m)
        defenders_value = sorted(
            by_position['DEF'],
            key=lambda p: p['dc_value'],
            reverse=True
        )
        rankings['defenders_by_value'] = defenders_value[:20]

        # Midfielders - ranked by DC consistency
        midfielders = sorted(
            by_position['MID'],
            key=lambda p: (p['dc_consistency'], p['defensive_bps']),
            reverse=True
        )
        rankings['midfielders_by_consistency'] = midfielders[:30]

        # Midfielders - ranked by value
        midfielders_value = sorted(
            by_position['MID'],
            key=lambda p: p['dc_value'],
            reverse=True
        )
        rankings['midfielders_by_value'] = midfielders_value[:20]

        # Elite DC performers (80%+ consistency, any position except GKP/FWD)
        all_eligible = [
            p for p in player_stats
            if p['position'] in ['DEF', 'MID']
        ]
        elite = sorted(
            [p for p in all_eligible if p['dc_consistency'] >= 60],  # Lowered threshold
            key=lambda p: (p['dc_consistency'], p['defensive_bps']),
            reverse=True
        )
        rankings['elite_dc_performers'] = elite[:25]

        return rankings

    def get_last_analysis(self) -> Dict[str, Any]:
        """
        Get the most recent DC analysis results.

        Returns:
            Dict with analysis results, or empty dict if no analysis performed yet
        """
        return self._last_analysis.copy()

    async def get_player_dc_ranking(self, player_id: int) -> Dict[str, Any]:
        """
        Get DC ranking info for a specific player.

        Args:
            player_id: FPL player ID

        Returns:
            Dict with player's DC stats and ranking
        """
        if not self._last_analysis:
            # No cached analysis, perform fresh analysis
            await self.analyze_dc_performance()

        # Search for player in all ranking lists
        all_rankings = []
        if 'defender_rankings' in self._last_analysis:
            all_rankings.extend(self._last_analysis['defender_rankings'])
        if 'midfielder_rankings' in self._last_analysis:
            all_rankings.extend(self._last_analysis['midfielder_rankings'])

        for player in all_rankings:
            if player['id'] == player_id:
                return player

        return {
            'error': 'Player not found in DC rankings',
            'player_id': player_id
        }

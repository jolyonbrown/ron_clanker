"""
xG Analyst Agent - "Sophia"

Analyzes expected goals (xG) and expected assists (xA) to identify:
- Players with high attacking threat
- Overperformers (goals > xG = hot streak)
- Underperformers (goals < xG = due a goal)

This data helps identify value attackers and predict future performance.
"""

import logging
from typing import Dict, List, Any
from collections import defaultdict

from agents.base_agent import BaseAgent
from agents.data_collector import DataCollector
from infrastructure.events import Event, EventType, EventPriority

logger = logging.getLogger(__name__)


class XGAnalyst(BaseAgent):
    """
    Sophia - The Expected Goals Analyst

    Specializes in:
    - Identifying high xG/xA players (best attacking threats)
    - Finding overperformers (goals > xG = lucky/hot streak)
    - Finding underperformers (goals < xG = due to score)
    - Ranking players by expected goal involvement per 90

    Subscribes to:
    - DATA_UPDATED: Triggers xG analysis when data refreshes

    Publishes:
    - XG_ANALYSIS_COMPLETED: Player rankings and recommendations
    """

    def __init__(self, data_collector: DataCollector = None):
        """
        Initialize Sophia.

        Args:
            data_collector: Optional data collector instance
        """
        super().__init__(agent_name="sophia")
        self.data_collector = data_collector or DataCollector()

        # Analysis parameters
        self._min_minutes = 270  # Minimum 3 full games (270 minutes)
        self._last_analysis: Dict[str, Any] = {}

        # Thresholds
        self.HIGH_XGI_THRESHOLD = 0.5  # xGI per 90 ≥ 0.5 = good attacking threat
        self.OVERPERFORMANCE_THRESHOLD = 0.05  # 5% over xG = overperforming
        self.UNDERPERFORMANCE_THRESHOLD = 0.05  # 5% under xG = underperforming

        logger.info("Sophia (xG Analyst) initialized")

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
        Handle DATA_UPDATED event by performing xG analysis.

        Args:
            event: DATA_UPDATED event
        """
        logger.info("Sophia: Fresh data detected, analyzing xG performance...")

        try:
            analysis = await self.analyze_xg()

            # Cache results
            self._last_analysis = analysis

            # Publish results
            await self.publish_event(
                EventType.XG_ANALYSIS_COMPLETED,
                payload=analysis,
                priority=EventPriority.NORMAL,
                correlation_id=event.event_id
            )

            logger.info(
                f"Sophia: xG analysis complete. "
                f"Found {len(analysis['high_xgi_players'])} high-threat players, "
                f"{len(analysis['overperformers'])} overperformers"
            )

        except Exception as e:
            logger.error(f"Sophia: xG analysis failed: {e}", exc_info=True)
            await self.publish_event(
                EventType.NOTIFICATION_ERROR,
                {
                    'message': 'xG analysis failed',
                    'error': str(e)
                }
            )

    async def _handle_analysis_requested(self, event: Event) -> None:
        """Handle ANALYSIS_REQUESTED event."""
        analysis_type = event.payload.get('analysis_type')

        if analysis_type in ['xg', 'all']:
            logger.info("Sophia: xG analysis requested...")
            await self._handle_data_updated(event)

    async def analyze_xg(self) -> Dict[str, Any]:
        """
        Perform comprehensive xG analysis.

        Returns:
            Dict containing:
                - high_xgi_players: Players with high xGI per 90
                - overperformers: Players scoring above xG
                - underperformers: Players scoring below xG
                - rankings_by_position: Top players by position
        """
        # Get latest data
        data = await self.data_collector.update_all_data()
        players = data['players']
        current_gw = data['current_gameweek']['id']

        logger.debug(f"Analyzing xG for {len(players)} players")

        # Analyze each player
        player_xg_stats = []

        for player in players:
            # Only analyze players with meaningful minutes
            if player.get('minutes', 0) < self._min_minutes:
                continue

            # Only analyze attacking positions (MID, FWD)
            if player['element_type'] not in [3, 4]:
                continue

            stats = self._calculate_player_xg_stats(player)
            if stats:
                player_xg_stats.append(stats)

        # Generate rankings
        rankings = self._generate_rankings(player_xg_stats)

        return {
            'gameweek': current_gw,
            'players_analyzed': len(player_xg_stats),
            'min_minutes_required': self._min_minutes,
            'high_xgi_players': rankings['high_xgi_players'],
            'overperformers': rankings['overperformers'],
            'underperformers': rankings['underperformers'],
            'midfielder_rankings': rankings['midfielder_rankings'],
            'forward_rankings': rankings['forward_rankings'],
            'top_recommendations': rankings['high_xgi_players'][:15]
        }

    def _calculate_player_xg_stats(self, player: Dict) -> Dict[str, Any]:
        """
        Calculate xG statistics for a single player.

        Args:
            player: Player data from FPL API

        Returns:
            Dict with xG stats, or None if insufficient data
        """
        minutes = player.get('minutes', 0)

        if minutes < self._min_minutes:
            return None

        # Get xG data (convert to float in case API returns strings)
        xg = float(player.get('expected_goals', 0))
        xa = float(player.get('expected_assists', 0))
        xgi = float(player.get('expected_goal_involvements', 0))

        # Per 90 metrics
        xg_per_90 = float(player.get('expected_goals_per_90', 0))
        xa_per_90 = float(player.get('expected_assists_per_90', 0))
        xgi_per_90 = float(player.get('expected_goal_involvements_per_90', 0))

        # Actual output
        goals = int(player.get('goals_scored', 0))
        assists = int(player.get('assists', 0))
        goal_involvements = goals + assists

        # Calculate over/underperformance
        xg_diff = goals - xg
        xa_diff = assists - xa
        xgi_diff = goal_involvements - xgi

        # Performance percentage (avoid division by zero)
        xg_performance_pct = ((goals / xg) - 1) * 100 if xg > 0 else 0
        xa_performance_pct = ((assists / xa) - 1) * 100 if xa > 0 else 0

        price = player['now_cost'] / 10.0
        position = ['GKP', 'DEF', 'MID', 'FWD'][player['element_type'] - 1]

        return {
            'id': player['id'],
            'name': player['web_name'],
            'team': player['team'],
            'position': position,
            'position_id': player['element_type'],
            'price': price,
            'minutes': minutes,
            'games_played': round(minutes / 90, 1),
            # Actual output
            'goals': goals,
            'assists': assists,
            'goal_involvements': goal_involvements,
            # Expected metrics (total)
            'xg': round(xg, 2),
            'xa': round(xa, 2),
            'xgi': round(xgi, 2),
            # Per 90 metrics
            'xg_per_90': round(xg_per_90, 2),
            'xa_per_90': round(xa_per_90, 2),
            'xgi_per_90': round(xgi_per_90, 2),
            # Performance vs expected
            'xg_diff': round(xg_diff, 2),
            'xa_diff': round(xa_diff, 2),
            'xgi_diff': round(xgi_diff, 2),
            'xg_performance_pct': round(xg_performance_pct, 1),
            'xa_performance_pct': round(xa_performance_pct, 1),
            # Value metrics
            'xgi_per_million': round(xgi / price, 2) if price > 0 else 0,
            'total_points': player['total_points'],
            'points_per_million': round(player['total_points'] / price, 2) if price > 0 else 0,
            'selected_by_percent': player.get('selected_by_percent', 0)
        }

    def _generate_rankings(self, player_stats: List[Dict]) -> Dict[str, List[Dict]]:
        """
        Generate rankings by various xG criteria.

        Args:
            player_stats: List of player xG statistics

        Returns:
            Dict with various ranking lists
        """
        rankings = {}

        # Group by position
        by_position = defaultdict(list)
        for player in player_stats:
            pos = player['position']
            by_position[pos].append(player)

        # High xGI players (best attacking threats)
        high_xgi = sorted(
            [p for p in player_stats if p['xgi_per_90'] >= self.HIGH_XGI_THRESHOLD],
            key=lambda p: p['xgi_per_90'],
            reverse=True
        )
        rankings['high_xgi_players'] = high_xgi[:30]

        # Overperformers (goals > xG = on hot streak, but may regress)
        overperformers = sorted(
            [p for p in player_stats if p['xg_diff'] > 0],
            key=lambda p: p['xg_diff'],
            reverse=True
        )
        rankings['overperformers'] = overperformers[:20]

        # Underperformers (goals < xG = due to score)
        underperformers = sorted(
            [p for p in player_stats if p['xg_diff'] < -0.5],  # At least 0.5 goals below xG
            key=lambda p: p['xg_diff']  # Most underperforming first
        )
        rankings['underperformers'] = underperformers[:20]

        # Midfielders ranked by xGI per 90
        midfielders = sorted(
            by_position.get('MID', []),
            key=lambda p: p['xgi_per_90'],
            reverse=True
        )
        rankings['midfielder_rankings'] = midfielders[:30]

        # Forwards ranked by xGI per 90
        forwards = sorted(
            by_position.get('FWD', []),
            key=lambda p: p['xgi_per_90'],
            reverse=True
        )
        rankings['forward_rankings'] = forwards[:30]

        # Value picks (high xGI per £m)
        value_picks = sorted(
            player_stats,
            key=lambda p: p['xgi_per_million'],
            reverse=True
        )
        rankings['value_picks'] = value_picks[:20]

        return rankings

    def get_last_analysis(self) -> Dict[str, Any]:
        """
        Get the most recent xG analysis.

        Returns:
            Dict with analysis results, or empty dict if none available
        """
        return self._last_analysis.copy()

    async def get_player_xg_stats(self, player_id: int) -> Dict[str, Any]:
        """
        Get xG stats for a specific player.

        Args:
            player_id: FPL player ID

        Returns:
            Dict with player's xG stats
        """
        if not self._last_analysis:
            await self.analyze_xg()

        # Search all rankings
        all_rankings = []
        for key in ['high_xgi_players', 'midfielder_rankings', 'forward_rankings']:
            all_rankings.extend(self._last_analysis.get(key, []))

        for player in all_rankings:
            if player['id'] == player_id:
                return player

        return {
            'error': 'Player not found in xG analysis',
            'player_id': player_id
        }

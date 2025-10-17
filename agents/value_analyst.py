"""
Value Analyst Agent - "Jimmy"

Combines insights from all specialist analysts to produce comprehensive
player value rankings. The ultimate arbiter of "who's worth the money."

Jimmy synthesizes:
- DC analysis (Digger): Defensive contribution potential
- Fixture analysis (Priya): Upcoming fixture difficulty
- xG analysis (Sophia): Attacking threat and expected output
- Price: Cost efficiency
- Form: Recent performance trends

Output: Unified value rankings by position.
"""

import logging
from typing import Dict, List, Any, Optional
from collections import defaultdict
from datetime import datetime

from agents.base_agent import BaseAgent
from agents.data_collector import DataCollector
from infrastructure.events import Event, EventType, EventPriority

logger = logging.getLogger(__name__)


class ValueAnalyst(BaseAgent):
    """
    Jimmy - The Value Analyst

    Specializes in:
    - Combining specialist analyses into unified value scores
    - Identifying best value players per position
    - Balancing multiple factors (DC, fixtures, xG, price)
    - Providing actionable player rankings for team selection

    Subscribes to:
    - DC_ANALYSIS_COMPLETED: From Digger
    - FIXTURE_ANALYSIS_COMPLETED: From Priya
    - XG_ANALYSIS_COMPLETED: From Sophia

    Publishes:
    - VALUE_RANKINGS_COMPLETED: Comprehensive player rankings
    """

    def __init__(self, data_collector: DataCollector = None):
        """
        Initialize Jimmy.

        Args:
            data_collector: Optional data collector instance
        """
        super().__init__(agent_name="jimmy")
        self.data_collector = data_collector or DataCollector()

        # Cache for specialist analyses
        self._dc_analysis: Optional[Dict] = None
        self._fixture_analysis: Optional[Dict] = None
        self._xg_analysis: Optional[Dict] = None
        self._last_value_rankings: Optional[Dict] = None

        # Scoring weights (sum to 1.0)
        self.WEIGHTS = {
            'base_points': 0.35,      # 35% - Current points per million
            'dc_potential': 0.25,      # 25% - Defensive contribution value
            'fixture_quality': 0.20,   # 20% - Fixture difficulty
            'xg_threat': 0.20          # 20% - Expected goal involvement
        }

        logger.info("Jimmy (Value Analyst) initialized")

    async def setup_subscriptions(self) -> None:
        """Subscribe to all specialist analysis events."""
        await self.subscribe_to(EventType.DC_ANALYSIS_COMPLETED)
        await self.subscribe_to(EventType.FIXTURE_ANALYSIS_COMPLETED)
        await self.subscribe_to(EventType.XG_ANALYSIS_COMPLETED)
        await self.subscribe_to(EventType.ANALYSIS_REQUESTED)

    async def handle_event(self, event: Event) -> None:
        """
        Handle incoming events.

        Args:
            event: The event to process
        """
        if event.event_type == EventType.DC_ANALYSIS_COMPLETED:
            await self._handle_dc_analysis(event)
        elif event.event_type == EventType.FIXTURE_ANALYSIS_COMPLETED:
            await self._handle_fixture_analysis(event)
        elif event.event_type == EventType.XG_ANALYSIS_COMPLETED:
            await self._handle_xg_analysis(event)
        elif event.event_type == EventType.ANALYSIS_REQUESTED:
            await self._handle_analysis_requested(event)

    async def _handle_dc_analysis(self, event: Event) -> None:
        """
        Handle DC analysis from Digger.

        Args:
            event: DC_ANALYSIS_COMPLETED event
        """
        logger.info("Jimmy: Received DC analysis from Digger")
        self._dc_analysis = event.payload
        await self._check_and_combine()

    async def _handle_fixture_analysis(self, event: Event) -> None:
        """
        Handle fixture analysis from Priya.

        Args:
            event: FIXTURE_ANALYSIS_COMPLETED event
        """
        logger.info("Jimmy: Received fixture analysis from Priya")
        self._fixture_analysis = event.payload
        await self._check_and_combine()

    async def _handle_xg_analysis(self, event: Event) -> None:
        """
        Handle xG analysis from Sophia.

        Args:
            event: XG_ANALYSIS_COMPLETED event
        """
        logger.info("Jimmy: Received xG analysis from Sophia")
        self._xg_analysis = event.payload
        await self._check_and_combine()

    async def _handle_analysis_requested(self, event: Event) -> None:
        """Handle explicit analysis request."""
        analysis_type = event.payload.get('analysis_type')

        if analysis_type in ['value', 'all']:
            logger.info("Jimmy: Value analysis requested, triggering combination...")
            await self._check_and_combine(force=True)

    async def _check_and_combine(self, force: bool = False) -> None:
        """
        Check if all specialist analyses are available and combine them.

        Args:
            force: Force combination even if some analyses are missing
        """
        # Check if we have all required analyses
        has_all = all([
            self._dc_analysis is not None,
            self._fixture_analysis is not None,
            self._xg_analysis is not None
        ])

        if not has_all and not force:
            logger.debug(
                f"Jimmy: Waiting for all analyses. "
                f"DC: {self._dc_analysis is not None}, "
                f"Fixture: {self._fixture_analysis is not None}, "
                f"xG: {self._xg_analysis is not None}"
            )
            return

        try:
            logger.info("Jimmy: All analyses available, combining...")
            value_rankings = await self.combine_analyses()

            # Cache results
            self._last_value_rankings = value_rankings

            # Publish results
            await self.publish_event(
                EventType.VALUE_RANKINGS_COMPLETED,
                payload=value_rankings,
                priority=EventPriority.HIGH
            )

            logger.info(
                f"Jimmy: Value rankings published. "
                f"Total players ranked: {value_rankings['total_players_ranked']}"
            )

        except Exception as e:
            logger.error(f"Jimmy: Failed to combine analyses: {e}", exc_info=True)
            await self.publish_event(
                EventType.NOTIFICATION_ERROR,
                {
                    'message': 'Value analysis failed',
                    'error': str(e)
                }
            )

    async def combine_analyses(self) -> Dict[str, Any]:
        """
        Combine all specialist analyses into unified value rankings.

        Returns:
            Dict with comprehensive value rankings by position
        """
        # Get fresh player data for baseline
        data = await self.data_collector.update_all_data()
        players = data['players']
        current_gw = data['current_gameweek']['id']

        logger.debug(f"Combining analyses for {len(players)} players")

        # Build lookup tables from specialist analyses
        dc_lookup = self._build_dc_lookup()
        fixture_lookup = self._build_fixture_lookup()
        xg_lookup = self._build_xg_lookup()

        # Calculate value score for each player
        player_values = []

        for player in players:
            # Only rank available players
            if player.get('status') != 'a':
                continue

            # Skip players with no game time
            if player.get('minutes', 0) < 90:
                continue

            value_score = self._calculate_value_score(
                player,
                dc_lookup,
                fixture_lookup,
                xg_lookup
            )

            if value_score:
                player_values.append(value_score)

        # Rank by position
        rankings = self._rank_by_position(player_values)

        return {
            'gameweek': current_gw,
            'timestamp': datetime.utcnow().isoformat(),
            'total_players_ranked': len(player_values),
            'scoring_weights': self.WEIGHTS,
            'rankings_by_position': rankings,
            'top_overall': sorted(player_values, key=lambda x: x['value_score'], reverse=True)[:30],
            'best_value_gkp': rankings.get('GKP', [])[:5],
            'best_value_def': rankings.get('DEF', [])[:10],
            'best_value_mid': rankings.get('MID', [])[:10],
            'best_value_fwd': rankings.get('FWD', [])[:10]
        }

    def _build_dc_lookup(self) -> Dict[int, Dict]:
        """Build player ID -> DC stats lookup."""
        lookup = {}

        if not self._dc_analysis:
            return lookup

        # Combine all DC rankings into single lookup
        for ranking_type in ['defender_rankings', 'midfielder_rankings']:
            for player in self._dc_analysis.get(ranking_type, []):
                lookup[player['id']] = player

        return lookup

    def _build_fixture_lookup(self) -> Dict[int, Dict]:
        """Build player ID -> fixture stats lookup."""
        lookup = {}

        if not self._fixture_analysis:
            return lookup

        # Extract player fixture ratings
        for position, players in self._fixture_analysis.get('player_fixture_ratings', {}).items():
            for player in players:
                lookup[player['id']] = player

        return lookup

    def _build_xg_lookup(self) -> Dict[int, Dict]:
        """Build player ID -> xG stats lookup."""
        lookup = {}

        if not self._xg_analysis:
            return lookup

        # Combine all xG rankings
        for ranking_type in ['midfielder_rankings', 'forward_rankings', 'high_xgi_players']:
            for player in self._xg_analysis.get(ranking_type, []):
                lookup[player['id']] = player

        return lookup

    def _calculate_value_score(
        self,
        player: Dict,
        dc_lookup: Dict[int, Dict],
        fixture_lookup: Dict[int, Dict],
        xg_lookup: Dict[int, Dict]
    ) -> Optional[Dict[str, Any]]:
        """
        Calculate comprehensive value score for a player.

        Args:
            player: Base player data
            dc_lookup: DC analysis data
            fixture_lookup: Fixture analysis data
            xg_lookup: xG analysis data

        Returns:
            Dict with value score and breakdown, or None if insufficient data
        """
        player_id = player['id']
        price = player['now_cost'] / 10.0

        if price == 0:
            return None

        # Component 1: Base points per million
        total_points = player.get('total_points', 0)
        base_score = (total_points / price) * 10  # Normalize to 0-100 scale

        # Component 2: DC potential
        dc_data = dc_lookup.get(player_id, {})
        dc_score = 0
        if dc_data:
            # Use DC value (DC points per £m) as score
            dc_score = dc_data.get('dc_value', 0) * 20  # Scale up

        # Component 3: Fixture quality (inverted - lower difficulty = better)
        fixture_data = fixture_lookup.get(player_id, {})
        fixture_score = 0
        if fixture_data:
            avg_difficulty = fixture_data.get('avg_fixture_difficulty', 3.0)
            # Invert: 1=best(100), 5=worst(0)
            fixture_score = (5 - avg_difficulty) / 4 * 100

        # Component 4: xG threat
        xg_data = xg_lookup.get(player_id, {})
        xg_score = 0
        if xg_data:
            xgi_per_90 = xg_data.get('xgi_per_90', 0)
            # Scale xGI to 0-100 (1.0 xGI/90 = 100)
            xg_score = min(xgi_per_90 * 100, 100)

        # Calculate weighted value score
        value_score = (
            base_score * self.WEIGHTS['base_points'] +
            dc_score * self.WEIGHTS['dc_potential'] +
            fixture_score * self.WEIGHTS['fixture_quality'] +
            xg_score * self.WEIGHTS['xg_threat']
        )

        position = ['GKP', 'DEF', 'MID', 'FWD'][player['element_type'] - 1]

        return {
            'id': player_id,
            'name': player['web_name'],
            'team': player['team'],
            'position': position,
            'price': price,
            'value_score': round(value_score, 2),
            # Score breakdown
            'base_score': round(base_score, 2),
            'dc_score': round(dc_score, 2),
            'fixture_score': round(fixture_score, 2),
            'xg_score': round(xg_score, 2),
            # Key stats
            'total_points': total_points,
            'points_per_million': round(total_points / price, 2),
            'selected_by_percent': player.get('selected_by_percent', 0),
            # Specialist insights
            'dc_consistency': dc_data.get('dc_consistency', 0),
            'avg_fixture_difficulty': fixture_data.get('avg_fixture_difficulty'),
            'xgi_per_90': xg_data.get('xgi_per_90', 0)
        }

    def _rank_by_position(self, player_values: List[Dict]) -> Dict[str, List[Dict]]:
        """
        Rank players by position.

        Args:
            player_values: List of player value scores

        Returns:
            Dict mapping position to ranked player lists
        """
        by_position = defaultdict(list)

        for player in player_values:
            by_position[player['position']].append(player)

        # Sort each position by value score
        for position in by_position:
            by_position[position].sort(key=lambda x: x['value_score'], reverse=True)

        return dict(by_position)

    def get_last_rankings(self) -> Optional[Dict[str, Any]]:
        """
        Get the most recent value rankings.

        Returns:
            Dict with rankings, or None if no rankings available
        """
        return self._last_value_rankings

    async def get_player_value(self, player_id: int) -> Dict[str, Any]:
        """
        Get value analysis for a specific player.

        Args:
            player_id: FPL player ID

        Returns:
            Dict with player's value score and breakdown
        """
        if not self._last_value_rankings:
            return {
                'error': 'No value rankings available yet',
                'player_id': player_id
            }

        # Search in rankings
        for position, players in self._last_value_rankings.get('rankings_by_position', {}).items():
            for player in players:
                if player['id'] == player_id:
                    return player

        return {
            'error': 'Player not found in value rankings',
            'player_id': player_id
        }

"""
Fixture Analyst Agent - "Priya"

Analyzes fixture difficulty to identify players with favorable schedules.
Plans 3-6 gameweeks ahead to optimize transfer timing and captain picks.

Ron's philosophy: "Look ahead 3-6 gameweeks for planning"
"""

import logging
from typing import Dict, List, Any, Tuple
from collections import defaultdict

from agents.base_agent import BaseAgent
from agents.data_collector import DataCollector
from infrastructure.events import Event, EventType, EventPriority

logger = logging.getLogger(__name__)


class FixtureAnalyst(BaseAgent):
    """
    Priya - The Fixture Analyst

    Specializes in:
    - Fixture difficulty ratings (6 gameweeks ahead)
    - Identifying teams with easy/hard runs
    - Detecting fixture swings (good → bad or bad → good)
    - Planning optimal transfer windows

    Subscribes to:
    - DATA_UPDATED: Triggers fixture analysis when data refreshes

    Publishes:
    - FIXTURE_ANALYSIS_COMPLETED: Team and player fixture ratings
    """

    def __init__(self, data_collector: DataCollector = None):
        """
        Initialize Priya.

        Args:
            data_collector: Optional data collector instance
        """
        super().__init__(agent_name="priya")
        self.data_collector = data_collector or DataCollector()

        # Analysis parameters
        self._lookahead_gameweeks = 6  # Look 6 GWs ahead
        self._last_analysis: Dict[str, Any] = {}

        # Difficulty thresholds
        self.EASY_THRESHOLD = 2.5  # Avg difficulty ≤ 2.5 = good fixtures
        self.HARD_THRESHOLD = 3.5  # Avg difficulty ≥ 3.5 = tough fixtures

        logger.info("Priya (Fixture Analyst) initialized")

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
        Handle DATA_UPDATED event by performing fixture analysis.

        Args:
            event: DATA_UPDATED event with fresh data
        """
        logger.info("Priya: Fresh data detected, analyzing fixtures...")

        try:
            # Get current gameweek from event payload
            current_gw = event.payload.get('gameweek')

            # Perform analysis
            analysis = await self.analyze_fixtures(current_gw)

            # Cache results
            self._last_analysis = analysis

            # Publish results
            await self.publish_event(
                EventType.FIXTURE_ANALYSIS_COMPLETED,
                payload=analysis,
                priority=EventPriority.NORMAL,
                correlation_id=event.event_id
            )

            logger.info(
                f"Priya: Fixture analysis complete. "
                f"Analyzed {len(analysis['team_analysis'])} teams, "
                f"found {len(analysis['teams_with_easy_fixtures'])} with easy runs"
            )

        except Exception as e:
            logger.error(f"Priya: Fixture analysis failed: {e}", exc_info=True)
            await self.publish_event(
                EventType.NOTIFICATION_ERROR,
                {
                    'message': 'Fixture analysis failed',
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

        if analysis_type in ['fixture', 'all']:
            gameweek = event.payload.get('gameweek')
            logger.info(f"Priya: Fixture analysis requested for GW{gameweek}...")
            await self._handle_data_updated(event)

    async def analyze_fixtures(self, start_gw: int = None) -> Dict[str, Any]:
        """
        Perform comprehensive fixture analysis.

        Args:
            start_gw: Starting gameweek (defaults to current GW)

        Returns:
            Dict containing:
                - team_analysis: All teams ranked by fixture difficulty
                - teams_with_easy_fixtures: Teams with avg difficulty ≤ 2.5
                - teams_with_hard_fixtures: Teams with avg difficulty ≥ 3.5
                - fixture_swings: Teams with major fixture changes
                - player_fixture_ratings: Top players by fixture difficulty
        """
        # Get latest data
        data = await self.data_collector.update_all_data()

        if start_gw is None:
            start_gw = data['current_gameweek']['id']

        teams = {t['id']: t for t in data['teams']}
        fixtures = data['fixtures']
        players = data['players']

        logger.debug(
            f"Analyzing fixtures from GW{start_gw} to GW{start_gw + self._lookahead_gameweeks - 1}"
        )

        # Analyze all teams
        team_analysis = self._analyze_all_teams(teams, fixtures, start_gw)

        # Identify easy/hard fixture runs
        easy_fixtures = [t for t in team_analysis if t['avg_difficulty'] <= self.EASY_THRESHOLD]
        hard_fixtures = [t for t in team_analysis if t['avg_difficulty'] >= self.HARD_THRESHOLD]

        # Detect fixture swings
        fixture_swings = self._detect_fixture_swings(team_analysis)

        # Rank players by fixtures
        player_fixture_ratings = self._rank_players_by_fixtures(players, teams, fixtures, start_gw)

        return {
            'start_gameweek': start_gw,
            'lookahead_gameweeks': self._lookahead_gameweeks,
            'end_gameweek': start_gw + self._lookahead_gameweeks - 1,
            'team_analysis': team_analysis,
            'teams_with_easy_fixtures': easy_fixtures,
            'teams_with_hard_fixtures': hard_fixtures,
            'fixture_swings': fixture_swings,
            'player_fixture_ratings': player_fixture_ratings
        }

    def _analyze_all_teams(
        self,
        teams: Dict[int, Dict],
        fixtures: List[Dict],
        start_gw: int
    ) -> List[Dict[str, Any]]:
        """
        Analyze fixture difficulty for all teams.

        Args:
            teams: Dict of team data
            fixtures: List of all fixtures
            start_gw: Starting gameweek

        Returns:
            List of team analysis dicts, sorted by easiest fixtures first
        """
        team_analysis = []

        for team_id, team in teams.items():
            fixture_run = self._get_team_fixtures(
                team_id,
                fixtures,
                start_gw,
                self._lookahead_gameweeks
            )

            if not fixture_run:
                continue

            avg_difficulty = sum(f['difficulty'] for f in fixture_run) / len(fixture_run)

            team_analysis.append({
                'team_id': team_id,
                'team_name': team['name'],
                'team_short_name': team['short_name'],
                'fixtures': fixture_run,
                'avg_difficulty': round(avg_difficulty, 2),
                'num_fixtures': len(fixture_run)
            })

        # Sort by easiest fixtures (lowest difficulty)
        team_analysis.sort(key=lambda x: x['avg_difficulty'])

        return team_analysis

    def _get_team_fixtures(
        self,
        team_id: int,
        fixtures: List[Dict],
        start_gw: int,
        num_gws: int
    ) -> List[Dict[str, Any]]:
        """
        Get fixture run for a team.

        Args:
            team_id: Team ID
            fixtures: All fixtures
            start_gw: Starting gameweek
            num_gws: Number of gameweeks to look ahead

        Returns:
            List of fixture dicts with opponent and difficulty
        """
        team_fixtures = []

        for gw in range(start_gw, start_gw + num_gws):
            for fixture in fixtures:
                if fixture.get('event') != gw:
                    continue

                if fixture['team_h'] == team_id:
                    team_fixtures.append({
                        'gameweek': gw,
                        'opponent_id': fixture['team_a'],
                        'is_home': True,
                        'difficulty': fixture['team_h_difficulty']
                    })
                elif fixture['team_a'] == team_id:
                    team_fixtures.append({
                        'gameweek': gw,
                        'opponent_id': fixture['team_h'],
                        'is_home': False,
                        'difficulty': fixture['team_a_difficulty']
                    })

        return team_fixtures

    def _detect_fixture_swings(
        self,
        team_analysis: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Detect teams with significant fixture swings.

        A swing is when a team goes from easy → hard or hard → easy fixtures.

        Args:
            team_analysis: List of team analysis dicts

        Returns:
            List of fixture swing opportunities
        """
        swings = []

        for team_data in team_analysis:
            fixtures = team_data['fixtures']

            if len(fixtures) < 4:
                continue

            # Split into first half and second half
            mid_point = len(fixtures) // 2
            first_half = fixtures[:mid_point]
            second_half = fixtures[mid_point:]

            first_half_avg = sum(f['difficulty'] for f in first_half) / len(first_half)
            second_half_avg = sum(f['difficulty'] for f in second_half) / len(second_half)

            # Significant swing = difference of 1.0 or more
            swing_magnitude = second_half_avg - first_half_avg

            if abs(swing_magnitude) >= 1.0:
                swing_type = 'worsening' if swing_magnitude > 0 else 'improving'

                swings.append({
                    'team_id': team_data['team_id'],
                    'team_name': team_data['team_short_name'],
                    'swing_type': swing_type,
                    'first_half_difficulty': round(first_half_avg, 2),
                    'second_half_difficulty': round(second_half_avg, 2),
                    'swing_magnitude': round(abs(swing_magnitude), 2),
                    'recommendation': (
                        'Buy now before fixtures worsen' if swing_type == 'worsening'
                        else 'Buy after fixtures improve'
                    )
                })

        # Sort by swing magnitude
        swings.sort(key=lambda x: x['swing_magnitude'], reverse=True)

        return swings

    def _rank_players_by_fixtures(
        self,
        players: List[Dict],
        teams: Dict[int, Dict],
        fixtures: List[Dict],
        start_gw: int
    ) -> Dict[str, List[Dict]]:
        """
        Rank players by their fixture difficulty.

        Args:
            players: All players
            teams: Team data
            fixtures: All fixtures
            start_gw: Starting gameweek

        Returns:
            Dict with player rankings by position
        """
        player_ratings = defaultdict(list)

        for player in players:
            # Only consider available players
            if player.get('status') != 'a':
                continue

            team_id = player['team']
            fixture_run = self._get_team_fixtures(
                team_id,
                fixtures,
                start_gw,
                self._lookahead_gameweeks
            )

            if not fixture_run:
                continue

            avg_difficulty = sum(f['difficulty'] for f in fixture_run) / len(fixture_run)
            position = ['GKP', 'DEF', 'MID', 'FWD'][player['element_type'] - 1]

            player_ratings[position].append({
                'id': player['id'],
                'name': player['web_name'],
                'team': teams[team_id]['short_name'],
                'price': player['now_cost'] / 10.0,
                'avg_fixture_difficulty': round(avg_difficulty, 2),
                'total_points': player['total_points'],
                'fixtures': fixture_run
            })

        # Sort each position by fixture difficulty (easiest first)
        for position in player_ratings:
            player_ratings[position].sort(key=lambda x: x['avg_fixture_difficulty'])

        return dict(player_ratings)

    def get_last_analysis(self) -> Dict[str, Any]:
        """
        Get the most recent fixture analysis.

        Returns:
            Dict with analysis results, or empty dict if none available
        """
        return self._last_analysis.copy()

    async def get_team_fixtures(
        self,
        team_id: int,
        num_gameweeks: int = 6
    ) -> Dict[str, Any]:
        """
        Get fixture analysis for a specific team.

        Args:
            team_id: FPL team ID
            num_gameweeks: Number of gameweeks to analyze

        Returns:
            Dict with team fixture data
        """
        if not self._last_analysis:
            # No cached analysis, perform fresh analysis
            await self.analyze_fixtures()

        # Find team in analysis
        for team in self._last_analysis.get('team_analysis', []):
            if team['team_id'] == team_id:
                return team

        return {
            'error': 'Team not found in fixture analysis',
            'team_id': team_id
        }

    async def get_player_fixtures(self, player_id: int) -> Dict[str, Any]:
        """
        Get fixture analysis for a specific player.

        Args:
            player_id: FPL player ID

        Returns:
            Dict with player fixture data
        """
        if not self._last_analysis:
            # No cached analysis, perform fresh analysis
            await self.analyze_fixtures()

        # Search in player ratings
        for position, players in self._last_analysis.get('player_fixture_ratings', {}).items():
            for player in players:
                if player['id'] == player_id:
                    return player

        return {
            'error': 'Player not found in fixture analysis',
            'player_id': player_id
        }

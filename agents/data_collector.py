"""
Data Collection Agent

Fetches FPL data via the fantasy-pl-mcp server.
Responsible for keeping all player, team, and fixture data up-to-date.
"""

import json
from typing import Dict, List, Any, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class DataCollector:
    """
    Data Collection Agent for FPL data via MCP.

    In production, this will use the MCP client to fetch data.
    For now, includes methods that will integrate with MCP.
    """

    def __init__(self, mcp_client=None):
        """
        Initialize Data Collector.

        Args:
            mcp_client: MCP client instance (optional, for future integration)
        """
        self.mcp_client = mcp_client
        self.last_updated = None

    # ========================================================================
    # CORE DATA FETCHING (MCP Integration Points)
    # ========================================================================

    async def fetch_bootstrap_data(self) -> Dict[str, Any]:
        """
        Fetch bootstrap-static data from FPL API.

        This contains:
        - All players
        - All teams
        - All gameweeks
        - Current game state

        Returns:
            Dict with keys: players, teams, events, game_settings
        """
        if self.mcp_client:
            # TODO: Use MCP client when available
            # response = await self.mcp_client.call_tool("get_bootstrap_static")
            # return response
            pass

        # Placeholder for development
        logger.warning("MCP client not configured - using placeholder data")
        return {
            'players': [],
            'teams': [],
            'events': [],
            'game_settings': {}
        }

    async def fetch_player_data(self, player_id: int) -> Dict[str, Any]:
        """
        Fetch detailed data for a specific player.

        Includes:
        - Season history
        - Fixture history
        - Upcoming fixtures

        Returns:
            Dict with player details and history
        """
        if self.mcp_client:
            # TODO: Use MCP client
            # response = await self.mcp_client.call_tool("get_player_summary", {"player_id": player_id})
            # return response
            pass

        logger.warning(f"MCP client not configured - cannot fetch player {player_id}")
        return {}

    async def fetch_fixtures(self, gameweek: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Fetch fixture data.

        Args:
            gameweek: Optional gameweek number (None = all fixtures)

        Returns:
            List of fixture dicts
        """
        if self.mcp_client:
            # TODO: Use MCP client
            # params = {"event": gameweek} if gameweek else {}
            # response = await self.mcp_client.call_tool("get_fixtures", params)
            # return response
            pass

        logger.warning("MCP client not configured - cannot fetch fixtures")
        return []

    async def fetch_live_gameweek_data(self, gameweek: int) -> Dict[str, Any]:
        """
        Fetch live data for a gameweek.

        Contains real-time player performance stats during gameweek.

        Returns:
            Dict with live player stats
        """
        if self.mcp_client:
            # TODO: Use MCP client
            # response = await self.mcp_client.call_tool("get_event_live", {"event": gameweek})
            # return response
            pass

        logger.warning(f"MCP client not configured - cannot fetch live GW{gameweek}")
        return {}

    # ========================================================================
    # PROCESSED DATA METHODS
    # ========================================================================

    def get_all_players(self, bootstrap_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract and process player data from bootstrap."""
        players = bootstrap_data.get('elements', [])

        # Add computed fields
        for player in players:
            player['value'] = self._calculate_player_value(player)
            player['form_numeric'] = float(player.get('form', 0) or 0)

        return players

    def get_all_teams(self, bootstrap_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract team data from bootstrap."""
        return bootstrap_data.get('teams', [])

    def get_all_gameweeks(self, bootstrap_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract gameweek data from bootstrap."""
        return bootstrap_data.get('events', [])

    def get_current_gameweek(self, bootstrap_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Get the current active gameweek."""
        events = bootstrap_data.get('events', [])
        for event in events:
            if event.get('is_current'):
                return event
        return None

    def get_next_gameweek(self, bootstrap_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Get the next upcoming gameweek."""
        events = bootstrap_data.get('events', [])
        for event in events:
            if event.get('is_next'):
                return event
        return None

    # ========================================================================
    # FILTERING & ANALYSIS HELPERS
    # ========================================================================

    def filter_players_by_position(
        self,
        players: List[Dict[str, Any]],
        position: int
    ) -> List[Dict[str, Any]]:
        """
        Filter players by position.

        Args:
            position: 1=GK, 2=DEF, 3=MID, 4=FWD
        """
        return [p for p in players if p.get('element_type') == position]

    def filter_players_by_team(
        self,
        players: List[Dict[str, Any]],
        team_id: int
    ) -> List[Dict[str, Any]]:
        """Filter players by team."""
        return [p for p in players if p.get('team') == team_id]

    def filter_available_players(
        self,
        players: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Filter to only available (not injured/suspended) players."""
        return [
            p for p in players
            if p.get('status') == 'a' and
            p.get('chance_of_playing_next_round', 100) == 100
        ]

    def get_price_changers(
        self,
        players: List[Dict[str, Any]],
        min_net_transfers: int = 1000
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Identify players likely to change price.

        Args:
            min_net_transfers: Minimum net transfers to consider

        Returns:
            Dict with 'risers' and 'fallers' lists
        """
        risers = []
        fallers = []

        for player in players:
            transfers_in = player.get('transfers_in_event', 0)
            transfers_out = player.get('transfers_out_event', 0)
            net_transfers = transfers_in - transfers_out

            if abs(net_transfers) >= min_net_transfers:
                if net_transfers > 0:
                    risers.append({
                        **player,
                        'net_transfers': net_transfers
                    })
                else:
                    fallers.append({
                        **player,
                        'net_transfers': net_transfers
                    })

        # Sort by absolute net transfers
        risers.sort(key=lambda x: x['net_transfers'], reverse=True)
        fallers.sort(key=lambda x: x['net_transfers'])

        return {
            'risers': risers[:20],  # Top 20 likely risers
            'fallers': fallers[:20]  # Top 20 likely fallers
        }

    # ========================================================================
    # VALUE CALCULATIONS
    # ========================================================================

    def _calculate_player_value(self, player: Dict[str, Any]) -> float:
        """
        Calculate player value metric (points per million).

        Simple metric: total_points / (now_cost / 10)
        """
        cost = player.get('now_cost', 1) / 10  # Convert to £m
        total_points = player.get('total_points', 0)

        if cost == 0:
            return 0

        return total_points / cost

    def get_best_value_players(
        self,
        players: List[Dict[str, Any]],
        position: Optional[int] = None,
        top_n: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Get best value players by points per million.

        Args:
            position: Optional position filter
            top_n: Number of players to return

        Returns:
            List of best value players
        """
        filtered = players
        if position:
            filtered = self.filter_players_by_position(players, position)

        # Filter to players with meaningful minutes
        filtered = [p for p in filtered if p.get('minutes', 0) > 180]  # 2+ full matches

        # Sort by value
        filtered.sort(key=lambda x: x.get('value', 0), reverse=True)

        return filtered[:top_n]

    # ========================================================================
    # FIXTURE ANALYSIS
    # ========================================================================

    def get_team_fixtures(
        self,
        fixtures: List[Dict[str, Any]],
        team_id: int,
        num_fixtures: int = 6
    ) -> List[Dict[str, Any]]:
        """Get upcoming fixtures for a team."""
        team_fixtures = [
            f for f in fixtures
            if (f.get('team_h') == team_id or f.get('team_a') == team_id)
            and not f.get('finished', False)
        ]

        # Sort by gameweek
        team_fixtures.sort(key=lambda x: x.get('event', 999))

        return team_fixtures[:num_fixtures]

    def calculate_fixture_difficulty(
        self,
        fixtures: List[Dict[str, Any]],
        team_id: int
    ) -> float:
        """
        Calculate average fixture difficulty for a team.

        Returns average FDR over upcoming fixtures (lower is easier).
        """
        if not fixtures:
            return 3.0  # Neutral

        total_difficulty = 0
        for fixture in fixtures:
            if fixture.get('team_h') == team_id:
                total_difficulty += fixture.get('team_h_difficulty', 3)
            else:
                total_difficulty += fixture.get('team_a_difficulty', 3)

        return total_difficulty / len(fixtures)

    # ========================================================================
    # UPDATE METHODS
    # ========================================================================

    async def update_all_data(self) -> Dict[str, Any]:
        """
        Fetch and return all current FPL data.

        This is the main method called by other agents to get fresh data.

        Returns:
            Dict with all FPL data
        """
        logger.info("Fetching all FPL data...")

        bootstrap = await self.fetch_bootstrap_data()
        fixtures = await self.fetch_fixtures()

        players = self.get_all_players(bootstrap)
        teams = self.get_all_teams(bootstrap)
        gameweeks = self.get_all_gameweeks(bootstrap)
        current_gw = self.get_current_gameweek(bootstrap)

        self.last_updated = datetime.now()

        logger.info(
            f"Data updated: {len(players)} players, "
            f"{len(teams)} teams, {len(fixtures)} fixtures"
        )

        return {
            'players': players,
            'teams': teams,
            'gameweeks': gameweeks,
            'fixtures': fixtures,
            'current_gameweek': current_gw,
            'updated_at': self.last_updated
        }

    async def update_player_details(self, player_ids: List[int]) -> Dict[int, Dict[str, Any]]:
        """
        Fetch detailed data for specific players.

        Used when we need in-depth stats for decision-making.

        Returns:
            Dict mapping player_id to detailed data
        """
        player_details = {}

        for player_id in player_ids:
            details = await self.fetch_player_data(player_id)
            player_details[player_id] = details

        return player_details

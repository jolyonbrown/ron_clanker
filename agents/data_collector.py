"""
Data Collection Agent - Maggie

Maggie is Ron Clanker's data specialist. She fetches all FPL data from the API,
caches it appropriately, and publishes events when data is updated.

Responsibilities:
- Fetch player, team, fixture, and gameweek data from FPL API
- Cache data in Redis to minimize API calls
- Publish events when data is refreshed
- Provide clean interface for other agents to access FPL data
"""

import asyncio
import json
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import aiohttp
import redis.asyncio as redis

from infrastructure.events import Event, EventType, EventPriority

logger = logging.getLogger(__name__)

# Import EventBus optionally (for standalone usage)
try:
    from infrastructure.event_bus import EventBus
except ImportError:
    EventBus = None


class DataCollector:
    """
    Maggie - The Data Collection Agent

    Fetches and caches FPL data, providing a single source of truth
    for all other agents.
    """

    FPL_API_BASE = "https://fantasy.premierleague.com/api"

    # Cache TTLs (time to live)
    CACHE_TTL_BOOTSTRAP = 6 * 3600  # 6 hours (data changes max twice daily)
    CACHE_TTL_FIXTURES = 12 * 3600  # 12 hours (fixtures rarely change)
    CACHE_TTL_PLAYER_DETAIL = 24 * 3600  # 24 hours (historical data)
    CACHE_TTL_LIVE = 60  # 1 minute (during matches, data is live)

    def __init__(
        self,
        redis_client: Optional[redis.Redis] = None,
        redis_url: str = "redis://localhost:6379",
        event_bus: Optional['EventBus'] = None
    ):
        """
        Initialize Data Collector.

        Args:
            redis_client: Redis client for caching (optional)
            redis_url: Redis connection URL
            event_bus: Event bus for publishing data updates (optional)
        """
        self.redis_client = redis_client
        self.redis_url = redis_url
        self.event_bus = event_bus
        self.last_updated = None
        self._session: Optional[aiohttp.ClientSession] = None

    async def _ensure_session(self):
        """Ensure aiohttp session exists."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()

    async def _ensure_redis(self):
        """Ensure Redis client is connected."""
        if self.redis_client is None:
            self.redis_client = await redis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True
            )

    async def close(self):
        """Close connections."""
        if self._session and not self._session.closed:
            await self._session.close()
        if self.redis_client:
            await self.redis_client.close()

    # ========================================================================
    # CACHING UTILITIES
    # ========================================================================

    async def _get_cached(self, key: str) -> Optional[Dict[str, Any]]:
        """Get data from Redis cache."""
        try:
            await self._ensure_redis()
            cached = await self.redis_client.get(key)
            if cached:
                logger.debug(f"Cache HIT for {key}")
                return json.loads(cached)
            logger.debug(f"Cache MISS for {key}")
        except Exception as e:
            logger.warning(f"Cache read error for {key}: {e}")
        return None

    async def _set_cached(self, key: str, data: Dict[str, Any], ttl: int):
        """Store data in Redis cache with TTL."""
        try:
            await self._ensure_redis()
            await self.redis_client.setex(
                key,
                ttl,
                json.dumps(data)
            )
            logger.debug(f"Cached {key} for {ttl}s")
        except Exception as e:
            logger.warning(f"Cache write error for {key}: {e}")

    # ========================================================================
    # CORE DATA FETCHING
    # ========================================================================

    async def fetch_bootstrap_data(self, force_refresh: bool = False) -> Dict[str, Any]:
        """
        Fetch bootstrap-static data from FPL API.

        This contains:
        - All players (~600)
        - All teams (20)
        - All gameweeks (38)
        - Current game state

        Args:
            force_refresh: Skip cache and fetch fresh data

        Returns:
            Dict with keys: elements (players), teams, events (gameweeks), etc.
        """
        cache_key = "fpl:bootstrap"

        # Check cache first
        if not force_refresh:
            cached = await self._get_cached(cache_key)
            if cached:
                return cached

        # Fetch from API
        logger.info("Fetching bootstrap data from FPL API...")
        await self._ensure_session()

        url = f"{self.FPL_API_BASE}/bootstrap-static/"

        try:
            async with self._session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status != 200:
                    logger.error(f"FPL API error: HTTP {response.status}")
                    return {}

                data = await response.json()

                # Cache the result
                await self._set_cached(cache_key, data, self.CACHE_TTL_BOOTSTRAP)

                logger.info(
                    f"Bootstrap data fetched: {len(data.get('elements', []))} players, "
                    f"{len(data.get('teams', []))} teams"
                )

                return data

        except asyncio.TimeoutError:
            logger.error("FPL API timeout")
            return {}
        except Exception as e:
            logger.error(f"Error fetching bootstrap data: {e}")
            return {}

    async def fetch_player_data(
        self,
        player_id: int,
        force_refresh: bool = False
    ) -> Dict[str, Any]:
        """
        Fetch detailed data for a specific player.

        Includes:
        - Season history
        - Gameweek-by-gameweek performance
        - Upcoming fixtures

        Args:
            player_id: FPL player ID
            force_refresh: Skip cache and fetch fresh data

        Returns:
            Dict with player details and history
        """
        cache_key = f"fpl:player:{player_id}"

        # Check cache
        if not force_refresh:
            cached = await self._get_cached(cache_key)
            if cached:
                return cached

        # Fetch from API
        logger.info(f"Fetching player {player_id} details from FPL API...")
        await self._ensure_session()

        url = f"{self.FPL_API_BASE}/element-summary/{player_id}/"

        try:
            async with self._session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status != 200:
                    logger.error(f"FPL API error for player {player_id}: HTTP {response.status}")
                    return {}

                data = await response.json()

                # Cache the result
                await self._set_cached(cache_key, data, self.CACHE_TTL_PLAYER_DETAIL)

                logger.info(f"Player {player_id} data fetched: {len(data.get('history', []))} GWs")

                return data

        except asyncio.TimeoutError:
            logger.error(f"FPL API timeout for player {player_id}")
            return {}
        except Exception as e:
            logger.error(f"Error fetching player {player_id}: {e}")
            return {}

    async def fetch_fixtures(
        self,
        gameweek: Optional[int] = None,
        force_refresh: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Fetch fixture data.

        Args:
            gameweek: Optional gameweek number (None = all fixtures)
            force_refresh: Skip cache and fetch fresh data

        Returns:
            List of fixture dicts
        """
        cache_key = f"fpl:fixtures:{gameweek if gameweek else 'all'}"

        # Check cache
        if not force_refresh:
            cached = await self._get_cached(cache_key)
            if cached:
                return cached

        # Fetch from API
        logger.info(f"Fetching fixtures from FPL API (GW: {gameweek or 'all'})...")
        await self._ensure_session()

        url = f"{self.FPL_API_BASE}/fixtures/"
        params = {"event": gameweek} if gameweek else {}

        try:
            async with self._session.get(
                url,
                params=params,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                if response.status != 200:
                    logger.error(f"FPL API error: HTTP {response.status}")
                    return []

                data = await response.json()

                # Cache the result
                await self._set_cached(cache_key, data, self.CACHE_TTL_FIXTURES)

                logger.info(f"Fetched {len(data)} fixtures")

                return data

        except asyncio.TimeoutError:
            logger.error("FPL API timeout")
            return []
        except Exception as e:
            logger.error(f"Error fetching fixtures: {e}")
            return []

    async def fetch_live_gameweek_data(
        self,
        gameweek: int,
        force_refresh: bool = False
    ) -> Dict[str, Any]:
        """
        Fetch live data for a gameweek.

        Contains real-time player performance stats during gameweek.

        Args:
            gameweek: Gameweek number
            force_refresh: Skip cache and fetch fresh data

        Returns:
            Dict with live player stats
        """
        cache_key = f"fpl:live:gw{gameweek}"

        # Check cache (short TTL - data changes frequently during matches)
        if not force_refresh:
            cached = await self._get_cached(cache_key)
            if cached:
                return cached

        # Fetch from API
        logger.info(f"Fetching live GW{gameweek} data from FPL API...")
        await self._ensure_session()

        url = f"{self.FPL_API_BASE}/event/{gameweek}/live/"

        try:
            async with self._session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status != 200:
                    logger.error(f"FPL API error: HTTP {response.status}")
                    return {}

                data = await response.json()

                # Cache with short TTL (1 minute during live matches)
                await self._set_cached(cache_key, data, self.CACHE_TTL_LIVE)

                logger.info(f"Live GW{gameweek} data fetched")

                return data

        except asyncio.TimeoutError:
            logger.error("FPL API timeout")
            return {}
        except Exception as e:
            logger.error(f"Error fetching live GW{gameweek}: {e}")
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
            (p.get('chance_of_playing_next_round') is None or
             p.get('chance_of_playing_next_round', 0) >= 75)
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
    # HIGH-LEVEL UPDATE METHODS
    # ========================================================================

    async def update_all_data(self, force_refresh: bool = False) -> Dict[str, Any]:
        """
        Fetch and return all current FPL data.

        This is the main method called by other agents to get fresh data.

        Args:
            force_refresh: Skip cache and fetch fresh data

        Returns:
            Dict with all FPL data
        """
        logger.info("Updating all FPL data...")

        # Fetch in parallel for speed
        bootstrap_task = self.fetch_bootstrap_data(force_refresh)
        fixtures_task = self.fetch_fixtures(force_refresh=force_refresh)

        bootstrap, fixtures = await asyncio.gather(bootstrap_task, fixtures_task)

        players = self.get_all_players(bootstrap)
        teams = self.get_all_teams(bootstrap)
        gameweeks = self.get_all_gameweeks(bootstrap)
        current_gw = self.get_current_gameweek(bootstrap)

        self.last_updated = datetime.now()

        logger.info(
            f"Data updated: {len(players)} players, "
            f"{len(teams)} teams, {len(fixtures)} fixtures"
        )

        result = {
            'players': players,
            'teams': teams,
            'gameweeks': gameweeks,
            'fixtures': fixtures,
            'current_gameweek': current_gw,
            'updated_at': self.last_updated
        }

        # Publish event if event bus is connected
        if self.event_bus:
            await self._publish_data_updated_event(result)

        return result

    async def _publish_data_updated_event(self, data: Dict[str, Any]):
        """Publish DATA_UPDATED event to notify other agents."""
        try:
            event = Event(
                event_type=EventType.DATA_UPDATED,
                payload={
                    'num_players': len(data['players']),
                    'num_teams': len(data['teams']),
                    'num_fixtures': len(data['fixtures']),
                    'current_gameweek': data['current_gameweek']['id'] if data['current_gameweek'] else None,
                    'updated_at': data['updated_at'].isoformat()
                },
                priority=EventPriority.NORMAL,
                source='maggie'
            )

            await self.event_bus.publish(event)
            logger.info("Published DATA_UPDATED event")

        except Exception as e:
            logger.warning(f"Failed to publish event: {e}")

    async def update_player_details(
        self,
        player_ids: List[int],
        force_refresh: bool = False
    ) -> Dict[int, Dict[str, Any]]:
        """
        Fetch detailed data for specific players.

        Used when we need in-depth stats for decision-making.

        Args:
            player_ids: List of FPL player IDs
            force_refresh: Skip cache and fetch fresh data

        Returns:
            Dict mapping player_id to detailed data
        """
        # Fetch in parallel
        tasks = [
            self.fetch_player_data(player_id, force_refresh)
            for player_id in player_ids
        ]

        results = await asyncio.gather(*tasks)

        return {
            player_id: data
            for player_id, data in zip(player_ids, results)
        }

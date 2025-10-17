"""
Chip Strategist Agent - "Terry"

Optimizes chip timing for maximum points gain.

Chips Available (2 of each per season):
- Bench Boost: Bench players' points count for one GW
- Triple Captain: Captain points tripled (instead of 2x)
- Free Hit: Unlimited free transfers for one GW, team reverts after
- Wildcard: All transfers free for one GW

Rules:
- First set: Available from start until GW19 deadline
- Second set: Available after GW19 deadline
- Cannot use same chip in consecutive GWs (Free Hit)
- Playing Wildcard/Free Hit retains banked FTs
"""

import logging
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime

from agents.base_agent import BaseAgent
from agents.data_collector import DataCollector
from data.database import Database
from infrastructure.events import Event, EventType, EventPriority

logger = logging.getLogger(__name__)


@dataclass
class ChipRecommendation:
    """A chip usage recommendation."""
    chip_name: str  # "bench_boost", "triple_captain", "free_hit", "wildcard"
    gameweek: int
    expected_gain: float
    reasoning: str
    priority: str  # "high", "medium", "low"
    conditions: List[str]  # Conditions that make this ideal


class ChipStrategistAgent(BaseAgent):
    """
    Terry - The Chip Strategist

    Analyzes when to play chips for maximum points gain:

    Bench Boost:
    - Strong bench with good fixtures
    - Double gameweeks (2x points potential)
    - All bench players likely to play

    Triple Captain:
    - Premium player with DGW
    - Excellent fixture(s)
    - High floor (consistent scorer)
    - Not rotation risk

    Free Hit:
    - Blank gameweeks (many teams not playing)
    - Multiple injuries/suspensions
    - Fixture chaos
    - Template disruption opportunity

    Wildcard:
    - Major fixture swing incoming
    - Team value gain opportunity
    - Multiple transfers needed (> 3)
    - International break (time to plan)
    - Post-AFCON (GW16 gives 5 FTs anyway)

    Subscribes to:
    - FIXTURE_ANALYSIS_COMPLETED: Check for DGWs, fixture swings
    - VALUE_RANKINGS_COMPLETED: Identify chip targets
    - GAMEWEEK_PLANNING: Make chip recommendations

    Publishes:
    - CHIP_RECOMMENDATION: Chip suggestions with reasoning
    """

    # Chip names
    BENCH_BOOST = "bench_boost"
    TRIPLE_CAPTAIN = "triple_captain"
    FREE_HIT = "free_hit"
    WILDCARD = "wildcard"

    # Chip timing windows
    FIRST_HALF_END = 19  # GW19 deadline
    AFCON_WINDOW = 16   # GW16 gets 5 FTs

    def __init__(
        self,
        data_collector: DataCollector = None,
        database: Database = None
    ):
        """
        Initialize Terry.

        Args:
            data_collector: Optional data collector instance
            database: Optional database instance
        """
        super().__init__(agent_name="terry")
        self.data_collector = data_collector or DataCollector()
        self.db = database or Database()

        # State
        self._fixture_analysis: Optional[Dict] = None
        self._value_rankings: Optional[Dict] = None

        # Track which chips have been used
        self._chips_used = {
            'first_half': {
                self.BENCH_BOOST: False,
                self.TRIPLE_CAPTAIN: False,
                self.FREE_HIT: False,
                self.WILDCARD: False
            },
            'second_half': {
                self.BENCH_BOOST: False,
                self.TRIPLE_CAPTAIN: False,
                self.FREE_HIT: False,
                self.WILDCARD: False
            }
        }

        logger.info("Terry (Chip Strategist) initialized")

    async def setup_subscriptions(self) -> None:
        """Subscribe to relevant events."""
        await self.subscribe_to(EventType.FIXTURE_ANALYSIS_COMPLETED)
        await self.subscribe_to(EventType.VALUE_RANKINGS_COMPLETED)
        await self.subscribe_to(EventType.GAMEWEEK_PLANNING)
        await self.subscribe_to(EventType.CHIP_USED)

    async def handle_event(self, event: Event) -> None:
        """
        Handle incoming events.

        Args:
            event: The event to process
        """
        if event.event_type == EventType.FIXTURE_ANALYSIS_COMPLETED:
            await self._handle_fixture_analysis(event)
        elif event.event_type == EventType.VALUE_RANKINGS_COMPLETED:
            await self._handle_value_rankings(event)
        elif event.event_type == EventType.GAMEWEEK_PLANNING:
            await self._handle_gameweek_planning(event)
        elif event.event_type == EventType.CHIP_USED:
            await self._handle_chip_used(event)

    async def _handle_fixture_analysis(self, event: Event) -> None:
        """Cache fixture analysis data."""
        self._fixture_analysis = event.payload
        logger.info("Terry: Fixture analysis received")

    async def _handle_value_rankings(self, event: Event) -> None:
        """Cache value rankings data."""
        self._value_rankings = event.payload
        logger.info("Terry: Value rankings received")

    async def _handle_chip_used(self, event: Event) -> None:
        """Track which chips have been used."""
        chip_name = event.payload.get('chip_name')
        gameweek = event.payload.get('gameweek')

        half = 'first_half' if gameweek <= self.FIRST_HALF_END else 'second_half'
        if chip_name in self._chips_used[half]:
            self._chips_used[half][chip_name] = True
            logger.info(f"Terry: Marked {chip_name} as used in {half}")

    async def _handle_gameweek_planning(self, event: Event) -> None:
        """
        Generate chip recommendations.

        Args:
            event: GAMEWEEK_PLANNING event
        """
        gameweek = event.payload.get('gameweek')
        trigger_point = event.payload.get('trigger_point')

        logger.info(f"Terry: Analyzing chip strategy for GW{gameweek}")

        # Only recommend chips at 48h trigger (early planning)
        if trigger_point != '48h':
            return

        try:
            recommendations = await self.analyze_chip_strategy(gameweek)

            if recommendations:
                # Publish chip recommendations
                await self.publish_event(
                    EventType.CHIP_RECOMMENDATION,
                    payload={
                        'gameweek': gameweek,
                        'recommendations': [
                            {
                                'chip_name': r.chip_name,
                                'gameweek': r.gameweek,
                                'expected_gain': r.expected_gain,
                                'reasoning': r.reasoning,
                                'priority': r.priority,
                                'conditions': r.conditions
                            }
                            for r in recommendations
                        ],
                        'timestamp': datetime.now().isoformat()
                    },
                    priority=EventPriority.NORMAL,
                    correlation_id=event.event_id
                )

                logger.info(f"Terry: Published {len(recommendations)} chip recommendations")
            else:
                logger.info("Terry: No chip recommendations for this gameweek")

        except Exception as e:
            logger.error(f"Terry: Error analyzing chips: {e}")

    async def analyze_chip_strategy(self, gameweek: int) -> List[ChipRecommendation]:
        """
        Analyze chip timing strategy.

        Args:
            gameweek: Current gameweek

        Returns:
            List of chip recommendations
        """
        recommendations = []
        half = 'first_half' if gameweek <= self.FIRST_HALF_END else 'second_half'

        # Check each chip type
        if not self._chips_used[half][self.WILDCARD]:
            wc_rec = self._analyze_wildcard(gameweek, half)
            if wc_rec:
                recommendations.append(wc_rec)

        if not self._chips_used[half][self.BENCH_BOOST]:
            bb_rec = self._analyze_bench_boost(gameweek)
            if bb_rec:
                recommendations.append(bb_rec)

        if not self._chips_used[half][self.TRIPLE_CAPTAIN]:
            tc_rec = self._analyze_triple_captain(gameweek)
            if tc_rec:
                recommendations.append(tc_rec)

        if not self._chips_used[half][self.FREE_HIT]:
            fh_rec = self._analyze_free_hit(gameweek)
            if fh_rec:
                recommendations.append(fh_rec)

        # Sort by priority and expected gain
        priority_order = {'high': 3, 'medium': 2, 'low': 1}
        recommendations.sort(
            key=lambda r: (priority_order.get(r.priority, 0), r.expected_gain),
            reverse=True
        )

        return recommendations

    def _analyze_wildcard(self, gameweek: int, half: str) -> Optional[ChipRecommendation]:
        """
        Analyze Wildcard timing.

        Best times:
        - GW3-5: Early adjustments after seeing real data
        - Pre-AFCON (GW15): But GW16 gives 5 FTs anyway, so less urgent
        - GW20-22: Post-AFCON adjustments
        - GW30-32: Final push, fixture swings

        Args:
            gameweek: Current gameweek
            half: 'first_half' or 'second_half'

        Returns:
            ChipRecommendation if Wildcard makes sense now
        """
        conditions = []
        priority = "low"
        expected_gain = 5.0  # Default moderate gain

        # Early wildcard (GW3-5) - see real data
        if 3 <= gameweek <= 5 and half == 'first_half':
            conditions.append("Early WC: React to first gameweeks, fix bad picks")
            priority = "medium"
            expected_gain = 8.0

        # Pre-AFCON (GW14-15)
        elif 14 <= gameweek <= 15 and half == 'first_half':
            conditions.append("Pre-AFCON: But GW16 gets 5 FTs, may not need WC")
            priority = "low"
            expected_gain = 4.0

        # Post-AFCON (GW20-22)
        elif 20 <= gameweek <= 22 and half == 'second_half':
            conditions.append("Post-AFCON: Major squad overhaul after tournament")
            priority = "high"
            expected_gain = 12.0

        # Final push (GW30-32)
        elif 30 <= gameweek <= 32 and half == 'second_half':
            conditions.append("Final push: Fixture swings, doubles coming")
            priority = "medium"
            expected_gain = 10.0

        # Don't recommend unless we hit a good window
        if not conditions:
            return None

        reasoning = (
            f"Terry: Wildcard timing for GW{gameweek}. "
            f"Allows unlimited free transfers to reshape squad. "
            f"{' '.join(conditions)}"
        )

        return ChipRecommendation(
            chip_name=self.WILDCARD,
            gameweek=gameweek,
            expected_gain=expected_gain,
            reasoning=reasoning,
            priority=priority,
            conditions=conditions
        )

    def _analyze_bench_boost(self, gameweek: int) -> Optional[ChipRecommendation]:
        """
        Analyze Bench Boost timing.

        Best for:
        - Double gameweeks (DGW) - bench gets 2x games
        - Strong bench with good fixtures
        - All bench players expected to play

        Args:
            gameweek: Current gameweek

        Returns:
            ChipRecommendation if BB makes sense now
        """
        conditions = []
        priority = "low"
        expected_gain = 4.0

        # Check for DGW (would need fixture data)
        # For now, generic logic

        # DGWs typically happen GW24-26, GW32-34
        if 24 <= gameweek <= 26 or 32 <= gameweek <= 34:
            conditions.append("Potential DGW window: Bench players get double games")
            priority = "high"
            expected_gain = 15.0

        # Otherwise, need strong bench + good fixtures
        else:
            conditions.append("Strong bench needed: All 4 bench players must start")
            priority = "low"
            expected_gain = 6.0

        reasoning = (
            f"Terry: Bench Boost for GW{gameweek}. "
            f"Bench points count towards total. "
            f"{' '.join(conditions)}"
        )

        # Only recommend in DGW windows or if specifically good
        if priority == "low":
            return None

        return ChipRecommendation(
            chip_name=self.BENCH_BOOST,
            gameweek=gameweek,
            expected_gain=expected_gain,
            reasoning=reasoning,
            priority=priority,
            conditions=conditions
        )

    def _analyze_triple_captain(self, gameweek: int) -> Optional[ChipRecommendation]:
        """
        Analyze Triple Captain timing.

        Best for:
        - Premium player in DGW (Haaland, Salah)
        - Excellent fixture(s)
        - High floor player (consistent)
        - Not rotation risk

        Args:
            gameweek: Current gameweek

        Returns:
            ChipRecommendation if TC makes sense now
        """
        conditions = []
        priority = "low"
        expected_gain = 8.0

        # DGW windows for premiums
        if 24 <= gameweek <= 26 or 32 <= gameweek <= 34:
            conditions.append("DGW window: Premium captain gets 2x games with 3x multiplier = 6x potential")
            priority = "high"
            expected_gain = 20.0

        # Otherwise wait for perfect fixture
        else:
            conditions.append("Need: Premium vs weak opponent(s) at home")
            priority = "low"
            expected_gain = 10.0

        reasoning = (
            f"Terry: Triple Captain for GW{gameweek}. "
            f"Captain points tripled instead of doubled. "
            f"{' '.join(conditions)}"
        )

        # Only recommend in DGW windows
        if priority == "low":
            return None

        return ChipRecommendation(
            chip_name=self.TRIPLE_CAPTAIN,
            gameweek=gameweek,
            expected_gain=expected_gain,
            reasoning=reasoning,
            priority=priority,
            conditions=conditions
        )

    def _analyze_free_hit(self, gameweek: int) -> Optional[ChipRecommendation]:
        """
        Analyze Free Hit timing.

        Best for:
        - Blank gameweeks (BGW) - many teams not playing
        - Multiple injuries/suspensions
        - One-week fixture exploit

        Args:
            gameweek: Current gameweek

        Returns:
            ChipRecommendation if FH makes sense now
        """
        conditions = []
        priority = "low"
        expected_gain = 5.0

        # BGWs typically GW18, GW29, GW33
        if gameweek in [18, 29, 33]:
            conditions.append(f"Potential BGW{gameweek}: Many teams blank, FH to field full 11")
            priority = "high"
            expected_gain = 20.0

        # Otherwise only for emergencies
        else:
            conditions.append("Emergency use: Multiple injuries/poor fixtures")
            priority = "low"
            expected_gain = 8.0

        reasoning = (
            f"Terry: Free Hit for GW{gameweek}. "
            f"Unlimited transfers for one GW, team reverts after. "
            f"{' '.join(conditions)}"
        )

        # Only recommend for BGWs
        if priority == "low":
            return None

        return ChipRecommendation(
            chip_name=self.FREE_HIT,
            gameweek=gameweek,
            expected_gain=expected_gain,
            reasoning=reasoning,
            priority=priority,
            conditions=conditions
        )

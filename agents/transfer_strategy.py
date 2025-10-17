"""
Transfer Strategy Agent - "Hugo"

Plans multi-week transfer strategy for Ron Clanker's FPL team.

Hugo's Responsibilities:
- Track free transfer bank (max 5)
- Decide when to roll vs use free transfers
- Plan 3-week rolling transfer strategy
- Calculate -4 point hit value (only if EV > 4pts over 3 GWs)
- Identify transfer targets based on fixture swings
- Sequence transfers optimally (urgent first)

FPL Transfer Rules:
- 1 free transfer per gameweek
- Max 5 free transfers can be banked
- Each additional transfer = -4 points
- Special: GW15→GW16 everyone gets 5 FTs (AFCON)
- Wildcard/Free Hit preserves banked transfers
"""

import logging
from typing import Dict, List, Any, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime

from agents.base_agent import BaseAgent
from agents.data_collector import DataCollector
from data.database import Database
from infrastructure.events import Event, EventType, EventPriority

logger = logging.getLogger(__name__)


@dataclass
class TransferRecommendation:
    """A single transfer recommendation."""
    player_out_id: int
    player_out_name: str
    player_in_id: int
    player_in_name: str
    priority: str  # "urgent", "planned", "optional"
    reasoning: str
    expected_gain: float  # Expected points over next 3 GWs
    cost: int  # 0 = free, 4 = -4 hit
    target_gameweek: int


@dataclass
class TransferPlan:
    """Multi-week transfer plan."""
    gameweek: int
    available_free_transfers: int
    recommended_action: str  # "roll", "use_one", "use_multiple", "take_hit"
    transfers: List[TransferRecommendation]
    reasoning: str


class TransferStrategyAgent(BaseAgent):
    """
    Hugo - The Transfer Strategist

    Plans optimal transfer sequence considering:
    - Free transfer banking (up to 5)
    - Fixture swings (next 3-6 GWs)
    - Player form and value
    - Price change timing
    - Hit calculation (-4 points)

    Subscribes to:
    - FIXTURE_ANALYSIS_COMPLETED: Get fixture difficulty data
    - VALUE_RANKINGS_COMPLETED: Get player value rankings
    - GAMEWEEK_PLANNING: Triggers transfer planning

    Publishes:
    - TRANSFER_RECOMMENDED: Transfer recommendations with reasoning
    """

    # Constants
    MAX_BANKED_TRANSFERS = 5
    HIT_COST = 4
    PLANNING_HORIZON = 3  # Look 3 GWs ahead for planning

    def __init__(
        self,
        data_collector: DataCollector = None,
        database: Database = None
    ):
        """
        Initialize Hugo.

        Args:
            data_collector: Optional data collector instance
            database: Optional database instance
        """
        super().__init__(agent_name="hugo")
        self.data_collector = data_collector or DataCollector()
        self.db = database or Database()

        # State
        self._fixture_analysis: Optional[Dict] = None
        self._value_rankings: Optional[Dict] = None
        self._current_squad: Optional[List[Dict]] = None
        self._free_transfers_available: int = 1  # Default starting value

        logger.info("Hugo (Transfer Strategist) initialized")

    async def setup_subscriptions(self) -> None:
        """Subscribe to relevant events."""
        await self.subscribe_to(EventType.FIXTURE_ANALYSIS_COMPLETED)
        await self.subscribe_to(EventType.VALUE_RANKINGS_COMPLETED)
        await self.subscribe_to(EventType.GAMEWEEK_PLANNING)
        await self.subscribe_to(EventType.TEAM_SELECTED)

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
        elif event.event_type == EventType.TEAM_SELECTED:
            await self._handle_team_selected(event)

    async def _handle_fixture_analysis(self, event: Event) -> None:
        """Cache fixture analysis data."""
        self._fixture_analysis = event.payload
        logger.info("Hugo: Fixture analysis received")

    async def _handle_value_rankings(self, event: Event) -> None:
        """Cache value rankings data."""
        self._value_rankings = event.payload
        logger.info("Hugo: Value rankings received")

    async def _handle_team_selected(self, event: Event) -> None:
        """Update current squad when team is selected."""
        self._current_squad = event.payload.get('squad', [])
        logger.info(f"Hugo: Current squad updated ({len(self._current_squad)} players)")

    async def _handle_gameweek_planning(self, event: Event) -> None:
        """
        Main planning trigger - generate transfer strategy.

        Args:
            event: GAMEWEEK_PLANNING event with deadline info
        """
        gameweek = event.payload.get('gameweek')
        trigger_point = event.payload.get('trigger_point')  # 48h, 24h, or 6h

        logger.info(f"Hugo: Planning transfers for GW{gameweek} ({trigger_point} trigger)")

        # Only plan at 24h trigger (final planning window)
        if trigger_point != '24h':
            logger.info("Hugo: Waiting for 24h trigger for final transfer plan")
            return

        # Check if we have necessary data
        if not self._fixture_analysis or not self._value_rankings:
            logger.warning("Hugo: Missing fixture or value data, cannot plan")
            return

        # Generate transfer plan
        try:
            plan = await self.generate_transfer_plan(gameweek)

            # Publish transfer recommendations
            await self.publish_event(
                EventType.TRANSFER_RECOMMENDED,
                payload={
                    'gameweek': gameweek,
                    'available_free_transfers': plan.available_free_transfers,
                    'recommended_action': plan.recommended_action,
                    'transfers': [
                        {
                            'player_out_id': t.player_out_id,
                            'player_out_name': t.player_out_name,
                            'player_in_id': t.player_in_id,
                            'player_in_name': t.player_in_name,
                            'priority': t.priority,
                            'reasoning': t.reasoning,
                            'expected_gain': t.expected_gain,
                            'cost': t.cost,
                            'target_gameweek': t.target_gameweek
                        }
                        for t in plan.transfers
                    ],
                    'reasoning': plan.reasoning,
                    'timestamp': datetime.now().isoformat()
                },
                priority=EventPriority.HIGH,
                correlation_id=event.event_id
            )

            logger.info(f"Hugo: Published {len(plan.transfers)} transfer recommendations")

        except Exception as e:
            logger.error(f"Hugo: Error generating transfer plan: {e}")

    async def generate_transfer_plan(self, gameweek: int) -> TransferPlan:
        """
        Generate comprehensive transfer plan.

        Args:
            gameweek: Current gameweek number

        Returns:
            TransferPlan with recommendations
        """
        # Get current free transfers (would query DB/API in real implementation)
        free_transfers = self._get_available_free_transfers(gameweek)

        # Identify players to transfer out
        players_out = self._identify_transfer_targets_out(gameweek)

        # Identify players to transfer in
        players_in = self._identify_transfer_targets_in(gameweek)

        # Generate transfer recommendations
        transfers = self._match_transfers(players_out, players_in, gameweek)

        # Decide: roll or use transfers?
        action = self._decide_transfer_strategy(
            free_transfers=free_transfers,
            potential_transfers=transfers,
            gameweek=gameweek
        )

        # Filter transfers based on strategy
        final_transfers = self._filter_transfers_by_strategy(
            transfers=transfers,
            action=action,
            free_transfers=free_transfers
        )

        # Generate reasoning
        reasoning = self._generate_plan_reasoning(
            action=action,
            free_transfers=free_transfers,
            transfers=final_transfers,
            gameweek=gameweek
        )

        return TransferPlan(
            gameweek=gameweek,
            available_free_transfers=free_transfers,
            recommended_action=action,
            transfers=final_transfers,
            reasoning=reasoning
        )

    def _get_available_free_transfers(self, gameweek: int) -> int:
        """
        Get number of free transfers available.

        In real implementation, query database for current FT count.
        For now, return default logic.

        Args:
            gameweek: Current gameweek

        Returns:
            Number of free transfers (1-5)
        """
        # TODO: Query database for actual FT count
        # For now, assume 1 FT per week (standard case)

        # Special case: GW16 gets topped up to 5 (AFCON)
        if gameweek == 16:
            return self.MAX_BANKED_TRANSFERS

        return self._free_transfers_available

    def _identify_transfer_targets_out(self, gameweek: int) -> List[Dict]:
        """
        Identify players to consider transferring OUT.

        Consider:
        - Fixtures turning bad (next 3 GWs)
        - Poor recent form
        - Injury concerns
        - Price falling
        - Better alternatives available

        Args:
            gameweek: Current gameweek

        Returns:
            List of players to consider selling
        """
        if not self._current_squad or not self._fixture_analysis:
            return []

        targets_out = []

        for player in self._current_squad:
            player_id = player.get('id')
            team_id = player.get('team_id')

            # Get fixture difficulty for this player's team
            fixture_score = self._get_fixture_difficulty_score(
                team_id=team_id,
                gameweeks_ahead=self.PLANNING_HORIZON
            )

            # Flag players with bad fixtures coming
            if fixture_score > 3.5:  # Hard fixtures
                targets_out.append({
                    'player': player,
                    'reason': 'bad_fixtures',
                    'urgency': 'high',
                    'fixture_score': fixture_score
                })

        return targets_out

    def _identify_transfer_targets_in(self, gameweek: int) -> List[Dict]:
        """
        Identify players to consider transferring IN.

        Consider:
        - Fixtures improving (next 3 GWs)
        - High value score (from Jimmy)
        - Price about to rise
        - Undervalued/underowned

        Args:
            gameweek: Current gameweek

        Returns:
            List of potential transfer targets
        """
        if not self._value_rankings:
            return []

        # Get top value picks from Jimmy
        top_picks = self._value_rankings.get('top_value_picks', [])[:20]

        targets_in = []

        for player in top_picks:
            player_id = player.get('id')
            team_id = player.get('team_id')

            # Get fixture difficulty
            fixture_score = self._get_fixture_difficulty_score(
                team_id=team_id,
                gameweeks_ahead=self.PLANNING_HORIZON
            )

            # Prioritize players with good fixtures
            if fixture_score < 2.5:  # Easy fixtures
                targets_in.append({
                    'player': player,
                    'reason': 'good_fixtures_high_value',
                    'value_score': player.get('value_score', 0),
                    'fixture_score': fixture_score
                })

        # Sort by value score
        targets_in.sort(key=lambda x: x['value_score'], reverse=True)

        return targets_in

    def _match_transfers(
        self,
        players_out: List[Dict],
        players_in: List[Dict],
        gameweek: int
    ) -> List[TransferRecommendation]:
        """
        Match players OUT with players IN.

        Args:
            players_out: Players to consider selling
            players_in: Players to consider buying
            gameweek: Current gameweek

        Returns:
            List of transfer recommendations
        """
        transfers = []

        for target_out in players_out[:5]:  # Top 5 sellable players
            player_out = target_out['player']

            # Find suitable replacement (same position, affordable)
            for target_in in players_in:
                player_in = target_in['player']

                # Check position match
                if player_out.get('element_type') != player_in.get('element_type'):
                    continue

                # Calculate expected gain
                expected_gain = self._calculate_expected_gain(
                    player_out=player_out,
                    player_in=player_in,
                    gameweeks=self.PLANNING_HORIZON
                )

                # Create recommendation
                transfer = TransferRecommendation(
                    player_out_id=player_out.get('id'),
                    player_out_name=player_out.get('web_name', 'Unknown'),
                    player_in_id=player_in.get('id'),
                    player_in_name=player_in.get('web_name', 'Unknown'),
                    priority=target_out.get('urgency', 'planned'),
                    reasoning=f"OUT: {target_out['reason']}. IN: {target_in['reason']}",
                    expected_gain=expected_gain,
                    cost=0,  # Will be set later based on FT availability
                    target_gameweek=gameweek
                )

                transfers.append(transfer)
                break  # One replacement per player out

        # Sort by expected gain
        transfers.sort(key=lambda t: t.expected_gain, reverse=True)

        return transfers

    def _decide_transfer_strategy(
        self,
        free_transfers: int,
        potential_transfers: List[TransferRecommendation],
        gameweek: int
    ) -> str:
        """
        Decide: roll FTs, use them, or take a hit?

        Strategy:
        - Roll if: No urgent needs, banking towards 5, squad is strong
        - Use one: Standard case, one clear upgrade
        - Use multiple: Multiple urgent issues, have banked FTs
        - Take hit: Only if EV > 4pts over next 3 GWs

        Args:
            free_transfers: Available free transfers
            potential_transfers: List of potential transfers
            gameweek: Current gameweek

        Returns:
            Strategy: "roll", "use_one", "use_multiple", "take_hit"
        """
        if not potential_transfers:
            return "roll"

        # Count urgent transfers
        urgent = [t for t in potential_transfers if t.priority == "urgent"]

        # If we have urgent needs and FTs, use them
        if urgent and free_transfers > 0:
            if len(urgent) > 1 and free_transfers > 1:
                return "use_multiple"
            return "use_one"

        # Check if taking a hit is worth it
        if urgent:
            best_transfer = potential_transfers[0]
            if best_transfer.expected_gain > self.HIT_COST:
                return "take_hit"

        # If we're at max FTs, must use at least one
        if free_transfers >= self.MAX_BANKED_TRANSFERS:
            return "use_one"

        # Default: roll if no urgent needs
        if free_transfers < self.MAX_BANKED_TRANSFERS:
            return "roll"

        return "use_one"

    def _filter_transfers_by_strategy(
        self,
        transfers: List[TransferRecommendation],
        action: str,
        free_transfers: int
    ) -> List[TransferRecommendation]:
        """
        Filter and cost transfers based on strategy.

        Args:
            transfers: All potential transfers
            action: Strategy chosen
            free_transfers: Available FTs

        Returns:
            Final list of recommended transfers with costs assigned
        """
        if action == "roll":
            return []

        if action == "use_one":
            if transfers:
                transfers[0].cost = 0  # Free transfer
                return [transfers[0]]
            return []

        if action == "use_multiple":
            result = []
            for i, transfer in enumerate(transfers[:free_transfers]):
                transfer.cost = 0  # All are free
                result.append(transfer)
            return result

        if action == "take_hit":
            if transfers:
                # First FT is free, rest are -4
                result = []
                for i, transfer in enumerate(transfers[:free_transfers + 1]):
                    transfer.cost = 0 if i < free_transfers else self.HIT_COST
                    result.append(transfer)
                return result
            return []

        return []

    def _generate_plan_reasoning(
        self,
        action: str,
        free_transfers: int,
        transfers: List[TransferRecommendation],
        gameweek: int
    ) -> str:
        """
        Generate human-readable reasoning for the transfer plan.

        Args:
            action: Strategy chosen
            free_transfers: Available FTs
            transfers: Recommended transfers
            gameweek: Current gameweek

        Returns:
            Reasoning text
        """
        if action == "roll":
            return (
                f"Hugo: Banking the free transfer (now {free_transfers + 1}/{self.MAX_BANKED_TRANSFERS}). "
                f"Squad is solid, no urgent needs. Building towards multiple transfers "
                f"when fixtures swing or better targets emerge."
            )

        if action == "use_one":
            if transfers:
                t = transfers[0]
                return (
                    f"Hugo: Using 1 free transfer. {t.player_out_name} → {t.player_in_name}. "
                    f"Reasoning: {t.reasoning}. Expected gain: +{t.expected_gain:.1f} pts over next 3 GWs."
                )
            return "Hugo: No transfers recommended despite available FT."

        if action == "use_multiple":
            count = len(transfers)
            return (
                f"Hugo: Using {count} free transfers. Multiple improvements available. "
                f"Fixture swings justify using banked FTs now rather than waiting."
            )

        if action == "take_hit":
            if transfers:
                t = transfers[0]
                return (
                    f"Hugo: Recommending -4 hit. {t.player_out_name} → {t.player_in_name}. "
                    f"Expected gain: +{t.expected_gain:.1f} pts over next 3 GWs (> -4 cost). "
                    f"Urgent: {t.reasoning}"
                )
            return "Hugo: No hit recommended."

        return "Hugo: No transfer plan generated."

    def _get_fixture_difficulty_score(
        self,
        team_id: int,
        gameweeks_ahead: int
    ) -> float:
        """
        Get average fixture difficulty for a team over next N gameweeks.

        Args:
            team_id: Team ID
            gameweeks_ahead: Number of gameweeks to look ahead

        Returns:
            Average difficulty (1-5, lower is easier)
        """
        if not self._fixture_analysis:
            return 3.0  # Neutral default

        # TODO: Extract fixture difficulty from Priya's analysis
        # For now, return neutral score
        return 3.0

    def _calculate_expected_gain(
        self,
        player_out: Dict,
        player_in: Dict,
        gameweeks: int
    ) -> float:
        """
        Calculate expected points gain over N gameweeks.

        Args:
            player_out: Player being sold
            player_in: Player being bought
            gameweeks: Number of gameweeks to project

        Returns:
            Expected points gain
        """
        # Get expected points per game for each player
        ppg_out = player_out.get('points_per_game', 0) or 0
        ppg_in = player_in.get('points_per_game', 0) or 0

        # Simple projection: PPG * number of gameweeks
        expected_out = ppg_out * gameweeks
        expected_in = ppg_in * gameweeks

        # Could add fixture difficulty adjustments here
        # For now, simple difference
        return expected_in - expected_out

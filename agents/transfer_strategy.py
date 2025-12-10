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
- Respond to intelligence alerts (injuries, rotation, suspensions)
- Generate urgent transfers when squad players affected

FPL Transfer Rules:
- 1 free transfer per gameweek
- Max 5 free transfers can be banked
- Each additional transfer = -4 points
- Special events may grant additional FTs (fetched from API)
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
from services.free_transfer_tracker import FreeTransferTracker

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
    - INJURY_INTELLIGENCE: Urgent injury alerts from Scout
    - ROTATION_RISK: Rotation warnings from Scout
    - SUSPENSION_INTELLIGENCE: Suspension alerts from Scout

    Publishes:
    - TRANSFER_RECOMMENDED: Transfer recommendations with reasoning

    Autonomous Injury Response:
    When Scout detects injury/rotation/suspension for squad player:
    - CRITICAL/HIGH severity: Generate urgent transfer recommendation
    - Identify replacement candidates from same position
    - Calculate hit EV (expected gain vs -4 cost)
    - Publish urgent transfer with detailed reasoning
    - MEDIUM severity: Monitor and log for future planning
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
        self.ft_tracker = FreeTransferTracker()

        # State
        self._fixture_analysis: Optional[Dict] = None
        self._value_rankings: Optional[Dict] = None
        self._current_squad: Optional[List[Dict]] = None
        self._ft_data: Optional[Dict] = None  # Cached FT data from API

        logger.info("Hugo (Transfer Strategist) initialized")

    async def setup_subscriptions(self) -> None:
        """Subscribe to relevant events."""
        await self.subscribe_to(EventType.FIXTURE_ANALYSIS_COMPLETED)
        await self.subscribe_to(EventType.VALUE_RANKINGS_COMPLETED)
        await self.subscribe_to(EventType.GAMEWEEK_PLANNING)
        await self.subscribe_to(EventType.TEAM_SELECTED)

        # Intelligence events (from Scout)
        await self.subscribe_to(EventType.INJURY_INTELLIGENCE)
        await self.subscribe_to(EventType.ROTATION_RISK)
        await self.subscribe_to(EventType.SUSPENSION_INTELLIGENCE)

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
        elif event.event_type in [EventType.INJURY_INTELLIGENCE, EventType.ROTATION_RISK, EventType.SUSPENSION_INTELLIGENCE]:
            await self._handle_intelligence_alert(event)

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

    async def _handle_intelligence_alert(self, event: Event) -> None:
        """
        Handle intelligence alerts from Scout (injuries, rotation, suspensions).

        Checks if affected player is in our squad. If yes:
        - CRITICAL severity: Immediate urgent transfer
        - HIGH severity: Urgent transfer, calculate hit EV
        - MEDIUM severity: Monitor for now

        Args:
            event: Intelligence event from Scout
        """
        intelligence_type = event.payload.get('type')
        player_id = event.payload.get('player_id')
        player_name = event.payload.get('player_name')
        severity = event.payload.get('severity')
        confidence = event.payload.get('confidence')
        details = event.payload.get('details')

        logger.info(
            f"Hugo: Intelligence alert received - {player_name} ({intelligence_type}, "
            f"{severity} severity, {confidence:.0%} confidence)"
        )

        # Check if player is in our squad
        if not self._current_squad:
            logger.debug("Hugo: No squad loaded yet, skipping intelligence alert")
            return

        # Find player in squad
        affected_player = None
        for player in self._current_squad:
            if player.get('id') == player_id or player.get('web_name') == player_name:
                affected_player = player
                break

        if not affected_player:
            logger.debug(f"Hugo: {player_name} not in current squad, no action needed")
            return

        # Player is in our squad - assess urgency
        logger.warning(
            f"Hugo: SQUAD PLAYER AFFECTED - {player_name} ({intelligence_type})\n"
            f"  Severity: {severity}\n"
            f"  Details: {details}"
        )

        # Determine action based on severity
        if severity == 'CRITICAL':
            # Immediate urgent transfer needed
            await self._generate_urgent_transfer(
                affected_player,
                intelligence_type,
                details,
                severity,
                confidence
            )

        elif severity == 'HIGH':
            # Urgent transfer - calculate if hit is worth it
            await self._generate_urgent_transfer(
                affected_player,
                intelligence_type,
                details,
                severity,
                confidence
            )

        elif severity == 'MEDIUM':
            # Monitor situation - log but don't transfer yet
            logger.info(
                f"Hugo: Monitoring {player_name} - {intelligence_type} ({severity}). "
                f"Not urgent enough for immediate action."
            )

            # Log for future consideration in regular planning
            await self._log_intelligence_to_db(
                player_id,
                player_name,
                intelligence_type,
                severity,
                details
            )

        else:
            logger.debug(f"Hugo: {severity} severity - no immediate action required")

    async def _generate_urgent_transfer(
        self,
        affected_player: Dict,
        intel_type: str,
        details: str,
        severity: str,
        confidence: float
    ) -> None:
        """
        Generate urgent transfer recommendation for affected squad player.

        Args:
            affected_player: Player dict from squad
            intel_type: Type of intelligence (INJURY, ROTATION, SUSPENSION)
            details: Intelligence details
            severity: Severity level
            confidence: Confidence score
        """
        player_id = affected_player.get('id')
        player_name = affected_player.get('web_name', 'Unknown')
        position = affected_player.get('element_type', 0)
        price = affected_player.get('now_cost', 0) / 10  # Convert to £

        logger.info(f"Hugo: Generating urgent transfer for {player_name} (£{price}m)")

        # Get current gameweek
        current_gw = self._get_current_gameweek()

        # Find replacement candidates
        # For now, use simple logic - in production would use value rankings
        replacements = await self._find_replacement_candidates(
            position,
            price,
            max_candidates=3
        )

        if not replacements:
            logger.warning(f"Hugo: No suitable replacements found for {player_name}")
            return

        best_replacement = replacements[0]

        # Calculate expected gain
        # Simplified: assume injured player = 0 pts, replacement = 5 pts/week
        expected_gain = 5.0 * self.PLANNING_HORIZON  # Conservative estimate

        # Determine if hit is needed
        cost = 0 if self._free_transfers_available > 0 else self.HIT_COST

        # Build transfer recommendation
        transfer = TransferRecommendation(
            player_out_id=player_id,
            player_out_name=player_name,
            player_in_id=best_replacement['id'],
            player_in_name=best_replacement['web_name'],
            priority="urgent",
            reasoning=(
                f"URGENT: {player_name} {intel_type.lower()} ({severity} severity, {confidence:.0%} confidence). "
                f"{details}. Replacing with {best_replacement['web_name']} (£{best_replacement['now_cost']/10}m). "
                f"Expected gain: {expected_gain:.1f} pts over {self.PLANNING_HORIZON} GWs."
            ),
            expected_gain=expected_gain,
            cost=cost,
            target_gameweek=current_gw
        )

        # Publish urgent transfer recommendation
        await self.publish_event(
            EventType.TRANSFER_RECOMMENDED,
            payload={
                'gameweek': current_gw,
                'urgent': True,
                'intelligence_triggered': True,
                'intelligence_type': intel_type,
                'severity': severity,
                'confidence': confidence,
                'available_free_transfers': self._free_transfers_available,
                'transfers': [
                    {
                        'player_out_id': transfer.player_out_id,
                        'player_out_name': transfer.player_out_name,
                        'player_in_id': transfer.player_in_id,
                        'player_in_name': transfer.player_in_name,
                        'priority': transfer.priority,
                        'reasoning': transfer.reasoning,
                        'expected_gain': transfer.expected_gain,
                        'cost': transfer.cost,
                        'target_gameweek': transfer.target_gameweek
                    }
                ],
                'reasoning': (
                    f"Urgent transfer triggered by Scout intelligence. "
                    f"{player_name} affected by {intel_type}. "
                    f"Immediate action recommended."
                ),
                'timestamp': datetime.now().isoformat()
            },
            priority=EventPriority.CRITICAL,  # Urgent intelligence-triggered transfer
        )

        logger.warning(
            f"Hugo: URGENT TRANSFER RECOMMENDED\n"
            f"  OUT: {player_name} (£{price}m) - {intel_type}\n"
            f"  IN: {best_replacement['web_name']} (£{best_replacement['now_cost']/10}m)\n"
            f"  Cost: {cost} points\n"
            f"  Expected gain: {expected_gain:.1f} pts over {self.PLANNING_HORIZON} GWs"
        )

    async def _find_replacement_candidates(
        self,
        position: int,
        max_price: float,
        max_candidates: int = 3
    ) -> List[Dict]:
        """
        Find replacement candidates for a position.

        Args:
            position: Player position (1=GK, 2=DEF, 3=MID, 4=FWD)
            max_price: Maximum price (usually slightly above current player)
            max_candidates: Number of candidates to return

        Returns:
            List of candidate player dicts
        """
        try:
            # Query database for players in same position
            # Filter by price (allow up to £0.5m more)
            query = """
                SELECT id, web_name, element_type, now_cost,
                       total_points, form, minutes
                FROM players
                WHERE element_type = ?
                  AND now_cost <= ?
                  AND minutes > 0
                ORDER BY total_points DESC, form DESC
                LIMIT ?
            """

            max_price_tenths = int((max_price + 0.5) * 10)  # Allow £0.5m buffer

            candidates = self.db.execute_query(
                query,
                (position, max_price_tenths, max_candidates)
            )

            return candidates if candidates else []

        except Exception as e:
            logger.error(f"Hugo: Error finding replacements: {e}")
            return []

    async def _log_intelligence_to_db(
        self,
        player_id: int,
        player_name: str,
        intel_type: str,
        severity: str,
        details: str
    ) -> None:
        """
        Log intelligence to database for future consideration.

        Args:
            player_id: FPL player ID
            player_name: Player name
            intel_type: Intelligence type
            severity: Severity level
            details: Intelligence details
        """
        try:
            self.db.execute_update(
                """
                INSERT INTO decisions (
                    gameweek, decision_type, decision_data, reasoning,
                    agent_source, created_at
                ) VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (
                    self._get_current_gameweek(),
                    'intelligence_monitored',
                    f"{player_name} ({intel_type})",
                    f"Severity: {severity}. {details}",
                    'hugo'
                )
            )
        except Exception as e:
            logger.error(f"Hugo: Error logging intelligence: {e}")

    def _get_current_gameweek(self) -> int:
        """
        Get current gameweek number.

        Returns:
            Current gameweek number
        """
        try:
            # Query bootstrap data for current gameweek
            result = self.db.execute_query(
                "SELECT MAX(id) as current_gw FROM gameweeks WHERE finished = 0"
            )
            if result and result[0].get('current_gw'):
                return result[0]['current_gw']

            # Fallback: use max finished + 1
            result = self.db.execute_query(
                "SELECT MAX(id) as last_gw FROM gameweeks WHERE finished = 1"
            )
            if result and result[0].get('last_gw'):
                return result[0]['last_gw'] + 1

            return 8  # Default for Ron's entry

        except Exception as e:
            logger.error(f"Hugo: Error getting current gameweek: {e}")
            return 8

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

    def _get_available_free_transfers(
        self,
        gameweek: int,
        team_id: Optional[int] = None,
        override_ft: Optional[int] = None
    ) -> int:
        """
        Get number of free transfers available from FPL API.

        Fetches actual FT count by calculating from transfer history.
        Special events (like AFCON) are reflected in the API data.

        Args:
            gameweek: Target gameweek
            team_id: FPL entry team ID (optional, uses config if not provided)
            override_ft: Manual override for special cases

        Returns:
            Number of free transfers (1-5)
        """
        from utils.config import get_team_id

        # Get team_id from config if not provided
        if team_id is None:
            team_id = get_team_id()

        if team_id is None:
            logger.warning("No team_id available, defaulting to 1 FT")
            return 1

        try:
            # Fetch FT data from API (use cached if available for same GW)
            if self._ft_data is None or self._ft_data.get('target_gw') != gameweek:
                self._ft_data = self.ft_tracker.get_available_free_transfers(
                    team_id=team_id,
                    target_gw=gameweek,
                    override_ft=override_ft
                )

            free_transfers = self._ft_data['free_transfers']
            logger.info(
                f"FT check GW{gameweek}: {free_transfers} available "
                f"({self._ft_data['calculation']})"
            )
            return free_transfers

        except Exception as e:
            logger.error(f"Error fetching FT data: {e}, defaulting to 1")
            return 1

    def get_transfer_budget_info(
        self,
        gameweek: int,
        team_id: Optional[int] = None,
        override_ft: Optional[int] = None
    ) -> Dict:
        """
        Get full transfer budget info including FTs, bank, and team value.

        Public method for use by other modules (e.g., pre_deadline_selection).

        Args:
            gameweek: Target gameweek
            team_id: FPL entry team ID (optional, uses config if not provided)
            override_ft: Manual override for special cases

        Returns:
            {
                'free_transfers': int,
                'bank': float,
                'team_value': float,
                'banked_before': int,
                'last_gw_transfers': int,
                'calculation': str,
                'is_override': bool,
            }
        """
        from utils.config import get_team_id

        if team_id is None:
            team_id = get_team_id()

        if team_id is None:
            logger.warning("No team_id available, returning defaults")
            return {
                'free_transfers': 1,
                'bank': 0.0,
                'team_value': 100.0,
                'banked_before': 0,
                'last_gw_transfers': 0,
                'calculation': 'No team_id - using defaults',
                'is_override': False,
            }

        return self.ft_tracker.get_available_free_transfers(
            team_id=team_id,
            target_gw=gameweek,
            override_ft=override_ft
        )

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

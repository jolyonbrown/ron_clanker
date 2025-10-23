"""
Manager Agent V2 - Ron Clanker (Event-Driven)

The Gaffer. Makes final team selection decisions by synthesizing
recommendations from all specialist analysts via event-driven architecture.

Ron's Philosophy:
- Foundation first, fancy stuff second
- Prioritize high floors (DC specialists)
- Plan 3-6 gameweeks ahead
- Conservative with transfers and chips
- Trust the specialists, but Ron has final say
"""

import logging
from typing import Dict, List, Any, Optional
from datetime import datetime

from agents.base_agent import BaseAgent
from agents.data_collector import DataCollector
from rules.rules_engine import RulesEngine
from ron_clanker.persona import RonClanker
from data.database import Database
from infrastructure.events import Event, EventType, EventPriority

# ML/Intelligence imports for decision making
from agents.synthesis.engine import DecisionSynthesisEngine
from agents.transfer_optimizer import TransferOptimizer
from intelligence.chip_strategy import ChipStrategyAnalyzer

logger = logging.getLogger(__name__)


class RonManager(BaseAgent):
    """
    Ron Clanker - The Gaffer (Event-Driven)

    The boss. Makes final autonomous decisions on:
    - Team selection (15 players)
    - Formation (starting XI)
    - Captain/vice-captain
    - Transfers
    - Chip usage

    Subscribes to:
    - VALUE_RANKINGS_COMPLETED: From Jimmy

    Publishes:
    - TEAM_SELECTED: Final squad selected
    - TRANSFER_EXECUTED: Transfers made
    - CAPTAIN_SELECTED: Captaincy decision
    """

    def __init__(
        self,
        database: Optional[Database] = None,
        data_collector: Optional[DataCollector] = None,
        use_ml: bool = True
    ):
        """
        Initialize Ron.

        Args:
            database: Optional database instance
            data_collector: Optional data collector
            use_ml: Whether to use ML-powered decision making (default: True)
        """
        super().__init__(agent_name="ron")

        self.db = database or Database()
        self.data_collector = data_collector or DataCollector()
        self.rules_engine = RulesEngine()
        self.ron = RonClanker()

        # ML-powered Decision Making
        self.use_ml = use_ml
        if use_ml:
            try:
                self.synthesis_engine = DecisionSynthesisEngine(database=self.db)
                self.chip_strategy = ChipStrategyAnalyzer(
                    database=self.db,
                    league_intel_service=None  # Will be added when available
                )
                self.transfer_optimizer = TransferOptimizer(
                    database=self.db,
                    chip_strategy=self.chip_strategy
                )
                logger.info("Ron: ML decision systems loaded (synthesis, transfers, chips)")
            except Exception as e:
                logger.warning(f"Ron: Could not load ML systems: {e}. Falling back to basic valuation.")
                self.synthesis_engine = None
                self.chip_strategy = None
                self.transfer_optimizer = None
                self.use_ml = False
        else:
            self.synthesis_engine = None
            self.chip_strategy = None
            self.transfer_optimizer = None

        # Cache latest analyses
        self._value_rankings: Optional[Dict] = None
        self._current_team: Optional[List[Dict]] = None
        self._current_gameweek: Optional[int] = None

        # Team state
        self.available_budget = 1000  # £100m
        self.free_transfers = 1
        self.chips_used = []

        # Ron's tactical preferences
        self.FORMATION = {
            1: 1,  # 1 GK
            2: 3,  # 3 DEF (minimum)
            3: 5,  # 5 MID
            4: 2   # 2 FWD
        }

        # Position budgets
        self.POSITION_BUDGETS = {
            1: 90,   # £9.0m for 2 GKs
            2: 250,  # £25.0m for 5 DEFs (Ron invests here)
            3: 400,  # £40.0m for 5 MIDs
            4: 260   # £26.0m for 3 FWDs
        }

        logger.info("Ron Clanker (Event-Driven Manager) initialized")

    async def setup_subscriptions(self) -> None:
        """Subscribe to specialist analyses."""
        await self.subscribe_to(EventType.VALUE_RANKINGS_COMPLETED)
        await self.subscribe_to(EventType.TEAM_SELECTION_REQUESTED)

    async def handle_event(self, event: Event) -> None:
        """
        Handle incoming events.

        Args:
            event: The event to process
        """
        if event.event_type == EventType.VALUE_RANKINGS_COMPLETED:
            await self._handle_value_rankings(event)
        elif event.event_type == EventType.TEAM_SELECTION_REQUESTED:
            await self._handle_team_selection_request(event)

    async def _handle_value_rankings(self, event: Event) -> None:
        """
        Handle VALUE_RANKINGS_COMPLETED from Jimmy.

        Args:
            event: Value rankings event
        """
        logger.info("Ron: Value rankings received from Jimmy. Analyzing...")

        # Cache rankings
        self._value_rankings = event.payload
        self._current_gameweek = event.payload.get('gameweek')

        logger.info(
            f"Ron: Rankings cached for GW{self._current_gameweek}. "
            f"{event.payload['total_players_ranked']} players analyzed."
        )

    async def _handle_team_selection_request(self, event: Event) -> None:
        """
        Handle explicit team selection request.

        Args:
            event: Team selection request
        """
        gameweek = event.payload.get('gameweek')
        logger.info(f"Ron: Team selection requested for GW{gameweek}")

        # Make sure we have value rankings
        if not self._value_rankings:
            logger.warning("Ron: No value rankings available yet. Waiting...")
            return

        # Select team
        await self.select_team(gameweek)

    async def select_team(
        self,
        gameweek: int,
        budget: int = 1000
    ) -> Dict[str, Any]:
        """
        Autonomously select a team for the given gameweek.

        Args:
            gameweek: Gameweek number
            budget: Available budget (default £100m)

        Returns:
            Dict with team and announcement
        """
        logger.info(f"Ron: Selecting team for GW{gameweek}...")

        if not self._value_rankings:
            raise ValueError("No value rankings available. Run analysts first.")

        # Get player data
        data = await self.data_collector.update_all_data()
        players = data['players']

        # Build player lookup
        player_lookup = {p['id']: p for p in players}

        # Build squad from value rankings
        squad = self._build_squad_from_rankings(
            self._value_rankings,
            player_lookup,
            budget
        )

        # Assign positions (starting XI + bench)
        squad = self._assign_squad_positions(squad)

        # Select captain (must happen before validation)
        squad = self._select_captain(squad)

        # Validate squad (must happen AFTER position and captain assignment)
        is_valid, message = self.rules_engine.validate_team(squad)
        if not is_valid:
            logger.error(f"Ron: Team validation failed: {message}")
            raise ValueError(f"Invalid team: {message}")

        # Save to database
        self.db.set_team(gameweek, squad)
        self._current_team = squad

        # Generate announcement
        announcement = self._generate_team_announcement(squad, gameweek)

        # Publish event
        await self.publish_event(
            EventType.TEAM_SELECTED,
            {
                'gameweek': gameweek,
                'squad': [{'id': p['id'], 'name': p['web_name']} for p in squad],
                'total_cost': sum(p['now_cost'] for p in squad) / 10,
                'announcement': announcement
            },
            priority=EventPriority.HIGH
        )

        logger.info(f"Ron: Team selected for GW{gameweek}. Total cost: £{sum(p['now_cost'] for p in squad)/10:.1f}m")

        return {
            'squad': squad,
            'announcement': announcement
        }

    def _build_squad_from_rankings(
        self,
        value_rankings: Dict,
        player_lookup: Dict[int, Dict],
        budget: int
    ) -> List[Dict]:
        """
        Build 15-player squad from Jimmy's value rankings.

        Ron's approach:
        - Use value rankings as primary guide
        - Apply position budgets flexibly
        - Prioritize high DC players for defensive positions
        - Mix of value picks and premium attackers

        Args:
            value_rankings: Jimmy's rankings
            player_lookup: Player data by ID
            budget: Available budget

        Returns:
            List of 15 players
        """
        squad = []
        spent = 0

        rankings_by_pos = value_rankings['rankings_by_position']

        # Squad composition: 2 GKP, 5 DEF, 5 MID, 3 FWD
        position_targets = {
            'GKP': 2,
            'DEF': 5,
            'MID': 5,
            'FWD': 3
        }

        # More flexible budget allocation
        remaining_budget = budget

        # Select by position using value rankings
        for position, target_count in position_targets.items():
            pos_rankings = rankings_by_pos.get(position, [])

            if not pos_rankings:
                logger.warning(f"Ron: No rankings available for {position}!")
                continue

            selected_count = 0
            pos_spent = 0

            # Try to select target number of players
            attempts = 0
            max_attempts = min(len(pos_rankings), 100)  # Don't loop forever

            for ranked_player in pos_rankings:
                if selected_count >= target_count:
                    break

                attempts += 1
                if attempts > max_attempts:
                    break

                player_id = ranked_player['id']
                player = player_lookup.get(player_id)

                if not player:
                    logger.debug(f"  Player {player_id} not found in lookup")
                    continue

                # Only check if player is available
                if player.get('status') != 'a':
                    logger.debug(f"  {player.get('web_name', 'Unknown')} not available (status: {player.get('status')})")
                    continue

                # Check budget (more flexible now)
                player_cost = player['now_cost']
                if spent + player_cost > budget:
                    logger.debug(f"  {player['web_name']} too expensive (£{player_cost/10:.1f}m, would exceed budget)")
                    continue

                # Check team constraint (max 3 from same team)
                team_count = sum(1 for p in squad if p.get('team') == player.get('team'))
                if team_count >= 3:
                    logger.debug(f"  {player['web_name']} blocked by team constraint (already have {team_count} from team {player.get('team')})")
                    continue

                # Add player
                player_copy = player.copy()
                player_copy['purchase_price'] = player_cost
                player_copy['selling_price'] = player_cost
                player_copy['value_score'] = ranked_player['value_score']

                squad.append(player_copy)
                pos_spent += player_cost
                spent += player_cost
                selected_count += 1
                logger.debug(f"  ✅ Selected {player['web_name']} £{player_cost/10:.1f}m")

            logger.debug(
                f"Ron: Selected {selected_count}/{target_count} {position}s, "
                f"spent £{pos_spent/10:.1f}m (target: {target_count})"
            )

            # Warning if we couldn't fill the position
            if selected_count < target_count:
                logger.warning(
                    f"Ron: Only selected {selected_count}/{target_count} {position}s! "
                    f"May need to adjust strategy."
                )

        logger.info(f"Ron: Squad built. {len(squad)} players, £{spent/10:.1f}m spent")

        # If we don't have 15 players, we have a problem
        if len(squad) != 15:
            logger.error(f"Ron: Squad incomplete! Only {len(squad)}/15 players selected")
            # Log what we're missing
            actual_counts = {}
            for player in squad:
                pos = ['GKP', 'DEF', 'MID', 'FWD'][player['element_type'] - 1]
                actual_counts[pos] = actual_counts.get(pos, 0) + 1

            for pos, target in position_targets.items():
                actual = actual_counts.get(pos, 0)
                if actual < target:
                    logger.error(f"  Missing {target - actual} {pos}s")

        return squad

    def _assign_squad_positions(self, squad: List[Dict]) -> List[Dict]:
        """
        Assign positions 1-15 (1-11 starting, 12-15 bench).

        Uses formation optimizer to test all valid formations and select
        the one that maximizes total expected points.

        Args:
            squad: 15 players

        Returns:
            Squad with positions assigned
        """
        # Group by position
        by_position = {
            'GKP': [],
            'DEF': [],
            'MID': [],
            'FWD': []
        }

        for player in squad:
            pos_name = ['GKP', 'DEF', 'MID', 'FWD'][player['element_type'] - 1]
            by_position[pos_name].append(player)

        # Sort each position by value score (proxy for expected points)
        for pos in by_position:
            by_position[pos].sort(
                key=lambda x: x.get('value_score', 0),
                reverse=True
            )

        # Valid formations: (GK, DEF, MID, FWD) - all sum to 11
        valid_formations = [
            (1, 3, 4, 3),
            (1, 3, 5, 2),
            (1, 4, 3, 3),
            (1, 4, 4, 2),
            (1, 4, 5, 1),
            (1, 5, 3, 2),
            (1, 5, 4, 1)
        ]

        # Find formation that maximizes total value score
        best_formation = None
        best_total_score = 0

        for gk_count, def_count, mid_count, fwd_count in valid_formations:
            # Check if we have enough players for this formation
            if (len(by_position['GKP']) < gk_count or
                len(by_position['DEF']) < def_count or
                len(by_position['MID']) < mid_count or
                len(by_position['FWD']) < fwd_count):
                continue

            # Calculate total score for this formation
            total_score = (
                sum(p.get('value_score', 0) for p in by_position['GKP'][:gk_count]) +
                sum(p.get('value_score', 0) for p in by_position['DEF'][:def_count]) +
                sum(p.get('value_score', 0) for p in by_position['MID'][:mid_count]) +
                sum(p.get('value_score', 0) for p in by_position['FWD'][:fwd_count])
            )

            if total_score > best_total_score:
                best_total_score = total_score
                best_formation = (gk_count, def_count, mid_count, fwd_count)

        if not best_formation:
            logger.error("Ron: No valid formation found! Falling back to 3-5-2")
            best_formation = (1, 3, 5, 2)

        gk_count, def_count, mid_count, fwd_count = best_formation
        formation_str = f"{def_count}-{mid_count}-{fwd_count}"
        logger.info(f"Ron: Optimal formation: {formation_str} (total score: {best_total_score:.2f})")

        # Assign positions based on best formation
        position_number = 1

        # Starting XI (positions 1-11)
        for i in range(gk_count):
            by_position['GKP'][i]['position'] = position_number
            position_number += 1

        for i in range(def_count):
            by_position['DEF'][i]['position'] = position_number
            position_number += 1

        for i in range(mid_count):
            by_position['MID'][i]['position'] = position_number
            position_number += 1

        for i in range(fwd_count):
            by_position['FWD'][i]['position'] = position_number
            position_number += 1

        # Bench (positions 12-15)
        for i in range(gk_count, len(by_position['GKP'])):
            by_position['GKP'][i]['position'] = position_number
            position_number += 1

        for i in range(def_count, len(by_position['DEF'])):
            by_position['DEF'][i]['position'] = position_number
            position_number += 1

        for i in range(mid_count, len(by_position['MID'])):
            by_position['MID'][i]['position'] = position_number
            position_number += 1

        for i in range(fwd_count, len(by_position['FWD'])):
            by_position['FWD'][i]['position'] = position_number
            position_number += 1

        return squad

    def _select_captain(
        self,
        squad: List[Dict],
        gameweek: Optional[int] = None
    ) -> List[Dict]:
        """
        Select captain and vice-captain using ML predictions.

        Uses DecisionSynthesisEngine if available, otherwise falls back to
        basic value_score sorting.

        Args:
            squad: Squad with positions assigned
            gameweek: Gameweek number (for ML predictions)

        Returns:
            Squad with captaincy assigned
        """
        # Get starting XI only
        starting_xi = [p for p in squad if p.get('position', 16) <= 11]

        if not starting_xi:
            logger.warning("Ron: No starting XI found for captain selection")
            return squad

        # Try ML-powered captain selection
        if self.use_ml and self.synthesis_engine and gameweek:
            try:
                logger.info("Ron: Using ML predictions for captain selection...")
                recommendations = self.synthesis_engine.synthesize_recommendations(gameweek)
                captain_rec = recommendations.get('captain_recommendation', {})

                if captain_rec:
                    return self._assign_captain_ml(squad, captain_rec, recommendations)
                else:
                    logger.warning("Ron: No captain recommendation from ML, using fallback")
            except Exception as e:
                logger.error(f"Ron: ML captain selection failed: {e}. Using fallback.", exc_info=True)

        # Fallback: Use value_score
        logger.info("Ron: Using basic value_score for captain selection")
        return self._assign_captain_fallback(squad)

    def _assign_captain_ml(
        self,
        squad: List[Dict],
        captain_rec: Dict[str, Any],
        recommendations: Dict[str, Any]
    ) -> List[Dict]:
        """
        Assign captain using ML recommendation.

        Args:
            squad: Full squad
            captain_rec: Captain recommendation from synthesis engine
            recommendations: Full recommendations for fallback vice captain logic

        Returns:
            Squad with captaincy assigned
        """
        primary = captain_rec.get('primary', {})
        differential = captain_rec.get('differential_option', {})

        captain_id = primary.get('player_id') if primary else None
        vice_captain_id = differential.get('player_id') if differential else None

        # Reset all captaincy flags
        for player in squad:
            player['is_captain'] = False
            player['is_vice_captain'] = False
            player['multiplier'] = 1

        # Assign captain and vice
        for player in squad:
            player_fpl_id = player.get('player_id', player.get('id'))

            if player_fpl_id == captain_id:
                player['is_captain'] = True
                player['multiplier'] = 2
                logger.info(f"Ron: Captain (ML): {player['web_name']} ({primary.get('xp', 0):.2f} xP)")
            elif player_fpl_id == vice_captain_id:
                player['is_vice_captain'] = True
                logger.info(f"Ron: Vice Captain (ML): {player['web_name']} ({differential.get('xp', 0):.2f} xP)")

        # If captain not in team, fallback
        if not any(p.get('is_captain') for p in squad):
            logger.warning(f"Ron: ML captain {primary.get('name', 'N/A')} not in team, using fallback")
            return self._assign_captain_fallback(squad)

        # If vice captain not in team, assign to second-best by ML xP
        if not any(p.get('is_vice_captain') for p in squad):
            logger.info(f"Ron: ML vice captain {differential.get('name', 'N/A')} not in team, finding second-best")
            starting_xi = [p for p in squad if p.get('position', 16) <= 11 and not p.get('is_captain')]

            # Get ML xP for each player
            all_players_xp = {}
            if recommendations and recommendations.get('top_players'):
                for player_pred in recommendations['top_players']:
                    all_players_xp[player_pred['player_id']] = player_pred.get('xp', 0)

            # Build list with xP values
            candidates = []
            for player in starting_xi:
                player_fpl_id = player.get('player_id', player.get('id'))
                xp = all_players_xp.get(player_fpl_id, 0)
                candidates.append((player, xp))

            # Sort by xP and assign vice to top
            candidates.sort(key=lambda x: x[1], reverse=True)
            if candidates:
                candidates[0][0]['is_vice_captain'] = True
                logger.info(f"Ron: Vice Captain (fallback): {candidates[0][0]['web_name']} ({candidates[0][1]:.2f} xP)")

        return squad

    def _assign_captain_fallback(self, squad: List[Dict]) -> List[Dict]:
        """
        Basic fallback captain selection by value_score.

        Args:
            squad: Full squad

        Returns:
            Squad with captaincy assigned
        """
        starting_xi = [p for p in squad if p.get('position', 16) <= 11]

        # Sort by value score
        candidates = sorted(
            starting_xi,
            key=lambda x: x.get('value_score', 0),
            reverse=True
        )

        # Reset all flags
        for player in squad:
            player['is_captain'] = False
            player['is_vice_captain'] = False
            player['multiplier'] = 1

        # Assign captain
        if candidates:
            candidates[0]['is_captain'] = True
            candidates[0]['multiplier'] = 2
            logger.info(f"Ron: Captain (basic): {candidates[0]['web_name']} (value: {candidates[0].get('value_score', 0):.2f})")

        # Assign vice
        if len(candidates) > 1:
            candidates[1]['is_vice_captain'] = True
            logger.info(f"Ron: Vice Captain (basic): {candidates[1]['web_name']} (value: {candidates[1].get('value_score', 0):.2f})")

        return squad

    def _generate_team_announcement(
        self,
        squad: List[Dict],
        gameweek: int
    ) -> str:
        """
        Generate Ron's team announcement.

        Args:
            squad: Final squad
            gameweek: Gameweek number

        Returns:
            Announcement text in Ron's voice
        """
        # Group players by position
        by_position = {'GKP': [], 'DEF': [], 'MID': [], 'FWD': []}

        for player in squad:
            pos = ['GKP', 'DEF', 'MID', 'FWD'][player['element_type'] - 1]
            by_position[pos].append(player)

        # Get starting XI
        starting_xi = sorted(
            [p for p in squad if p.get('position', 16) <= 11],
            key=lambda x: x['position']
        )

        # Find captain
        captain = next((p for p in squad if p.get('is_captain')), None)

        # Generate Ron's announcement
        announcement = f"""GAMEWEEK {gameweek} - RON'S TEAM SELECTION

Right lads, here's how we're lining up for Gameweek {gameweek}...

BETWEEN THE STICKS: {by_position['GKP'][0]['web_name']}
Solid keeper. £{by_position['GKP'][0]['now_cost']/10:.1f}m well spent.

THE BACK LINE: {', '.join(p['web_name'] for p in starting_xi if p['element_type'] == 2)}
This is where we're different. These lads do the dirty work - tackles,
blocks, clearances. Defensive contribution points every week. That's a
high floor. Foundation first.

MIDFIELD ENGINE ROOM: {', '.join(p['web_name'] for p in starting_xi if p['element_type'] == 3)}
Mix of defensive graft and attacking threat. Some of these will earn DC
points, others are there for goals and assists. Balanced.

UP FRONT: {', '.join(p['web_name'] for p in starting_xi if p['element_type'] == 4)}
{captain['web_name'] if captain else 'The main striker'} gets the armband.

THE GAFFER'S LOGIC:
Jimmy's given me the rankings. Digger's found the DC specialists. Priya's
checked the fixtures. Sophia's identified the threats. I've weighed it all
up and made the call.

We're building for the long haul. High floors, smart picks, within budget.

Squad value: £{sum(p['now_cost'] for p in squad)/10:.1f}m

- Ron
"""

        return announcement

    # ========================================================================
    # CHIP DECISIONS
    # ========================================================================

    async def decide_chip_usage(
        self,
        gameweek: int,
        squad: List[Dict[str, Any]],
        chips_used: List[str]
    ) -> Optional[str]:
        """
        Decide whether to use a chip this gameweek.

        Uses ChipStrategyAnalyzer if ML is enabled, otherwise no chips.

        Args:
            gameweek: Target gameweek
            squad: Current squad
            chips_used: List of chips already used this season

        Returns:
            Chip name to use (e.g., 'wildcard', 'bench_boost') or None
        """
        if self.use_ml and self.chip_strategy:
            try:
                logger.info("Ron: Using ChipStrategyAnalyzer for chip decision...")
                result = self.chip_strategy.analyze_all_chips(gameweek, chips_used)

                recommended_chip = result.get('recommended_chip')
                reasoning = result.get('reasoning', 'No reasoning provided')

                if recommended_chip and recommended_chip != 'none':
                    logger.info(f"Ron: Chip recommended: {recommended_chip}")
                    logger.info(f"Ron: Reasoning: {reasoning}")

                    # Ron is conservative - only use chip if confidence is high
                    confidence = result.get('confidence', 0.5)
                    if confidence >= 0.7:
                        logger.info(f"Ron: Using {recommended_chip} (confidence: {confidence:.0%})")
                        return recommended_chip
                    else:
                        logger.info(f"Ron: Confidence {confidence:.0%} < 70%, saving chip")
                        return None
                else:
                    logger.info("Ron: No chip recommended this gameweek")
                    return None

            except Exception as e:
                logger.error(f"Ron: ChipStrategyAnalyzer failed: {e}. No chip will be used.", exc_info=True)
                return None
        else:
            logger.info("Ron: Chip analysis not available (ML disabled), no chip will be used")
            return None

    # ========================================================================
    # WEEKLY DECISION ORCHESTRATION
    # ========================================================================

    async def make_weekly_decision(
        self,
        gameweek: int,
        free_transfers: int = 1
    ) -> Dict[str, Any]:
        """
        Master orchestration method for weekly team decisions.

        Coordinates all decision-making:
        1. Load current team
        2. Decide transfers (using TransferOptimizer)
        3. Execute transfers
        4. Assign positions (formation optimizer)
        5. Select captain (ML-powered)
        6. Decide chip usage (ChipStrategyAnalyzer)
        7. Generate team announcement
        8. Save to draft_team
        9. Log all decisions
        10. Publish TEAM_SELECTED event

        Args:
            gameweek: Target gameweek
            free_transfers: Number of free transfers available

        Returns:
            Dict with keys: squad, transfers, chip_used, announcement
        """
        logger.info(f"Ron: Planning for GW{gameweek}...")

        # 1. Load current team
        current_team = self.db.get_actual_current_team()
        if not current_team:
            logger.error("Ron: No current team found in database!")
            raise ValueError("Current team not found - cannot make weekly decision")

        logger.info(f"Ron: Current team loaded ({len(current_team)} players)")

        # 2. Decide transfers
        logger.info("Ron: Analyzing transfer opportunities...")
        transfers = await self.decide_transfers(
            current_team=current_team,
            gameweek=gameweek,
            free_transfers=free_transfers
        )

        if transfers:
            logger.info(f"Ron: Recommending {len(transfers)} transfer(s)")
            for t in transfers:
                logger.info(f"  OUT: {t['player_out']['web_name']} → IN: {t['player_in']['web_name']}")
        else:
            logger.info("Ron: No transfers recommended - team is solid")

        # 3. Execute transfers
        new_team = self._execute_transfers(current_team, transfers)

        # 4. Assign positions (formation optimizer)
        logger.info("Ron: Optimizing formation...")
        new_team = self._assign_squad_positions(new_team)

        # 5. Select captain
        logger.info("Ron: Selecting captain...")
        new_team = self._select_captain(new_team, gameweek=gameweek)

        # 6. Decide chip usage
        logger.info("Ron: Evaluating chip usage...")
        chip_used = await self.decide_chip_usage(
            gameweek=gameweek,
            squad=new_team,
            chips_used=self.chips_used
        )

        if chip_used:
            logger.info(f"Ron: Using chip: {chip_used}")
            self.chips_used.append(chip_used)
        else:
            logger.info("Ron: No chip used this week")

        # 7. Log decisions to database
        self._log_decisions(gameweek, new_team, transfers, chip_used)

        # 8. Save to draft_team
        logger.info(f"Ron: Saving draft team for GW{gameweek}...")
        self.db.save_draft_team(gameweek, new_team)

        # 9. Generate team announcement
        logger.info("Ron: Generating team announcement...")
        announcement = self._generate_team_announcement(
            squad=new_team,
            gameweek=gameweek,
            transfers=transfers,
            chip_used=chip_used
        )

        # 10. Publish TEAM_SELECTED event
        await self.publish_event(
            EventType.TEAM_SELECTED,
            {
                'gameweek': gameweek,
                'squad': new_team,
                'transfers': transfers,
                'chip_used': chip_used,
                'announcement': announcement
            },
            priority=EventPriority.HIGH
        )

        logger.info(f"Ron: GW{gameweek} planning complete!")

        return {
            'squad': new_team,
            'transfers': transfers,
            'chip_used': chip_used,
            'announcement': announcement
        }

    def _execute_transfers(
        self,
        current_team: List[Dict[str, Any]],
        transfers: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Execute transfers and return new team.

        Args:
            current_team: Current 15-player squad
            transfers: List of transfers to execute

        Returns:
            New team with transfers applied
        """
        new_team = current_team.copy()

        for transfer in transfers:
            player_out = transfer['player_out']
            player_in = transfer['player_in']

            # Remove player out (compare player_id)
            player_out_id = player_out.get('player_id', player_out.get('id'))
            new_team = [
                p for p in new_team
                if p.get('player_id', p.get('id')) != player_out_id
            ]

            # Add player in with same position
            player_in_copy = player_in.copy()
            player_in_copy['position'] = player_out.get('position', 1)
            player_in_copy['purchase_price'] = player_in['now_cost']
            player_in_copy['selling_price'] = player_in['now_cost']

            # Ensure player_id is set
            if 'player_id' not in player_in_copy:
                player_in_copy['player_id'] = player_in_copy['id']

            new_team.append(player_in_copy)

        return new_team

    def _log_decisions(
        self,
        gameweek: int,
        team: List[Dict[str, Any]],
        transfers: List[Dict[str, Any]],
        chip_used: Optional[str]
    ) -> None:
        """
        Log all decisions to database for learning/review.

        Args:
            gameweek: Target gameweek
            team: Final squad
            transfers: Transfers made
            chip_used: Chip used (if any)
        """
        # Log captain decision
        captain = next((p for p in team if p.get('is_captain')), None)
        if captain:
            self.db.log_decision(
                gameweek=gameweek,
                decision_type='captain',
                decision_data={
                    'player_id': captain.get('player_id', captain.get('id')),
                    'player_name': captain.get('web_name', 'Unknown')
                },
                reasoning=f"Captain selected: {captain.get('web_name')}",
                expected_value=0,  # Would need ML xP here
                agent_source='RonManager',
                confidence=0.8
            )

        # Log transfer decisions
        if transfers:
            total_expected_gain = sum(t.get('expected_gain', 0) for t in transfers)
            transfer_reasoning = f"Made {len(transfers)} transfer(s). " + '; '.join([
                t.get('reasoning', 'N/A') for t in transfers
            ])

            self.db.log_decision(
                gameweek=gameweek,
                decision_type='transfer_strategy',
                decision_data={
                    'num_transfers': len(transfers),
                    'transfers': [
                        {
                            'out': t['player_out'].get('web_name'),
                            'in': t['player_in'].get('web_name')
                        }
                        for t in transfers
                    ]
                },
                reasoning=transfer_reasoning,
                expected_value=total_expected_gain,
                agent_source='RonManager',
                confidence=0.7
            )

            # Log individual transfers
            for transfer in transfers:
                self.db.log_transfer(
                    gameweek=gameweek,
                    player_out_id=transfer['player_out'].get('player_id', transfer['player_out'].get('id')),
                    player_in_id=transfer['player_in'].get('player_id', transfer['player_in'].get('id')),
                    cost=transfer.get('cost', 0),
                    is_free=transfer.get('is_free', True),
                    reasoning=transfer.get('reasoning', '')
                )

        # Log chip decision
        chip_reasoning = f"Using {chip_used}" if chip_used else "No chip used"
        self.db.log_decision(
            gameweek=gameweek,
            decision_type='chip_usage',
            decision_data={'chip': chip_used or 'none'},
            reasoning=chip_reasoning,
            expected_value=0,
            agent_source='RonManager',
            confidence=0.6
        )

    # ========================================================================
    # TRANSFER DECISIONS
    # ========================================================================

    async def decide_transfers(
        self,
        current_team: List[Dict[str, Any]],
        gameweek: int,
        free_transfers: int = 1
    ) -> List[Dict[str, Any]]:
        """
        Decide on transfers for the gameweek.

        Uses TransferOptimizer if ML is enabled, otherwise basic logic.

        Args:
            current_team: Current 15-player squad
            gameweek: Target gameweek
            free_transfers: Number of free transfers available

        Returns:
            List of transfer recommendations (may be empty if no beneficial transfers)
        """
        if self.use_ml and self.transfer_optimizer:
            try:
                logger.info("Ron: Using TransferOptimizer for transfer decisions...")
                result = self.transfer_optimizer.optimize_transfers(
                    current_team=current_team,
                    gameweek=gameweek,
                    free_transfers_available=free_transfers
                )

                transfers = result.get('transfers', [])
                logger.info(f"Ron: TransferOptimizer recommends {len(transfers)} transfer(s)")

                if result.get('chip_recommendation'):
                    logger.info(f"Ron: Chip vs Transfer comparison: {result['chip_recommendation'].get('recommendation', 'N/A')}")

                return transfers

            except Exception as e:
                logger.error(f"Ron: TransferOptimizer failed: {e}. Falling back to basic logic.", exc_info=True)
                return self._decide_transfers_fallback(current_team, gameweek)
        else:
            logger.info("Ron: Using basic transfer logic (ML not available)")
            return self._decide_transfers_fallback(current_team, gameweek)

    def _decide_transfers_fallback(
        self,
        current_team: List[Dict[str, Any]],
        gameweek: int
    ) -> List[Dict[str, Any]]:
        """
        Basic fallback transfer logic if ML unavailable.

        Simple strategy:
        - Find weakest player by form
        - Consider upgrade if +2pts expected gain
        """
        transfers = []

        # Sort by form to find weakest
        team_by_form = sorted(current_team, key=lambda x: float(x.get('form', 0)))
        weakest = team_by_form[0] if team_by_form else None

        if weakest and float(weakest.get('form', 0)) < 2.0:
            logger.info(f"Ron: Weakest player {weakest.get('web_name')} has form {weakest.get('form')} < 2.0")

            # Look for better alternative in same position
            position = weakest.get('element_type')
            max_price = weakest.get('now_cost', 0) / 10 + 1.0

            # Query database for alternatives
            alternatives = self.db.execute_query(
                """
                SELECT * FROM players
                WHERE element_type = ?
                AND now_cost <= ?
                AND status = 'a'
                ORDER BY form DESC
                LIMIT 5
                """,
                (position, int(max_price * 10))
            )

            current_ids = {p.get('player_id', p.get('id')) for p in current_team}
            alternatives = [a for a in alternatives if a['id'] not in current_ids]

            if alternatives:
                best = alternatives[0]
                expected_gain = float(best.get('form', 0)) - float(weakest.get('form', 0))

                if expected_gain >= 2.0:
                    transfers.append({
                        'player_out': weakest,
                        'player_in': best,
                        'expected_gain': expected_gain,
                        'is_free': True,
                        'cost': 0,
                        'reasoning': f"Form upgrade: {best['web_name']} ({best.get('form')} form) replacing {weakest['web_name']} ({weakest.get('form')} form)"
                    })
                    logger.info(f"Ron: Recommending {weakest['web_name']} → {best['web_name']} (expected gain: +{expected_gain:.1f})")

        return transfers

    # ========================================================================
    # GETTERS
    # ========================================================================

    def get_current_team(self) -> Optional[List[Dict]]:
        """Get the current team."""
        return self._current_team

    def get_value_rankings(self) -> Optional[Dict]:
        """Get cached value rankings."""
        return self._value_rankings

"""
Manager Agent - Ron Clanker

The central decision-maker. Coordinates all specialist agents and makes
final autonomous decisions on team selection, transfers, and chip usage.
"""

from typing import Dict, List, Any, Optional, Tuple
import logging
from datetime import datetime

from rules.rules_engine import RulesEngine
from agents.data_collector import DataCollector
from agents.player_valuation import PlayerValuationAgent
from agents.synthesis.engine import DecisionSynthesisEngine
from ron_clanker.persona import RonClanker
from data.database import Database
from utils.gameweek import get_current_gameweek

logger = logging.getLogger(__name__)


class ManagerAgent:
    """
    Ron Clanker - The Gaffer

    Central orchestrator for all FPL decisions. Coordinates specialist agents
    and makes final autonomous choices.

    Phase 1 Capabilities:
    - Select valid team within budget
    - Make weekly transfers based on value analysis
    - Choose captain based on expected points
    - Validate all decisions against FPL rules
    - Communicate in Ron Clanker's persona
    """

    def __init__(
        self,
        database: Optional[Database] = None,
        data_collector: Optional[DataCollector] = None,
        use_ml: bool = True
    ):
        """Initialize the Manager Agent."""
        self.db = database or Database()
        self.data_collector = data_collector or DataCollector()
        self.rules_engine = RulesEngine()
        self.valuation_agent = PlayerValuationAgent()
        self.ron = RonClanker()

        # ML-powered Decision Synthesis Engine (NEW!)
        self.use_ml = use_ml
        if use_ml:
            try:
                self.synthesis_engine = DecisionSynthesisEngine(database=self.db)
                logger.info("Decision Synthesis Engine loaded - ML predictions ENABLED")
            except Exception as e:
                logger.warning(f"Could not load synthesis engine: {e}. Falling back to basic valuation.")
                self.synthesis_engine = None
                self.use_ml = False
        else:
            self.synthesis_engine = None

        self.current_team = None
        self.available_budget = 0
        self.free_transfers = 1
        self.chips_used = []

        logger.info("Ron Clanker initialized. Ready to manage.")

    # ========================================================================
    # TEAM SELECTION
    # ========================================================================

    async def select_initial_team(
        self,
        budget: int = 1000  # £100m
    ) -> Tuple[List[Dict[str, Any]], str]:
        """
        Select initial 15-player squad at start of season.

        Phase 1 Strategy:
        - Build balanced team with mix of premium and budget players
        - Prioritize value (points per million)
        - Exploit defensive contribution potential
        - Ensure valid formation and budget compliance

        Returns:
            (team, announcement)
        """
        logger.info("Ron Clanker is selecting the squad...")

        # Get all player data
        fpl_data = await self.data_collector.update_all_data()
        all_players = fpl_data['players']

        # Rank all players by value
        ranked_players = self.valuation_agent.rank_players_by_value(
            all_players,
            include_dc_boost=True
        )

        # Build squad using budget optimization
        team = self._build_optimal_squad(ranked_players, budget)

        # Validate team
        is_valid, message = self.rules_engine.validate_team(team)
        if not is_valid:
            logger.error(f"Team validation failed: {message}")
            raise ValueError(f"Invalid team: {message}")

        # Set captain (highest expected points in starting XI)
        team = self._assign_captain(team)

        # Save to database
        self.current_team = team
        self.db.set_team(1, team)  # GW1

        # Generate announcement
        reasoning = {
            'strategy': "Balanced approach. Mix of premium attackers and value defenders.",
            'defensive_contribution_focus': (
                "Prioritizing defenders and midfielders who'll earn defensive contribution points. "
                "Most managers will miss this - that's our edge."
            )
        }

        announcement = self.ron.announce_team_selection(team, 1, reasoning)

        logger.info(f"Team selected. Total cost: {sum(p['now_cost'] for p in team)/10:.1f}m")

        return team, announcement

    def _build_optimal_squad(
        self,
        ranked_players: List[Dict[str, Any]],
        budget: int
    ) -> List[Dict[str, Any]]:
        """
        Build optimal 15-player squad within budget.

        Phase 1 approach: Greedy algorithm with position constraints.
        """
        team = []
        spent = 0

        # Target allocation (total 15 players)
        position_targets = {
            1: 2,  # 2 GK
            2: 5,  # 5 DEF
            3: 5,  # 5 MID
            4: 3   # 3 FWD
        }

        position_filled = {1: 0, 2: 0, 3: 0, 4: 0}

        # Reserve budget for each position
        position_budget = {
            1: 90,   # £9.0m for 2 GKs (avg 4.5m each)
            2: 250,  # £25.0m for 5 DEFs (avg 5.0m each)
            3: 400,  # £40.0m for 5 MIDs (avg 8.0m each)
            4: 260   # £26.0m for 3 FWDs (avg 8.7m each)
        }

        # Fill each position
        for position in [4, 3, 2, 1]:  # Fill forwards first (most expensive)
            target = position_targets[position]
            pos_budget = position_budget[position]

            # Get best players for this position within budget
            position_players = [
                p for p in ranked_players
                if p['element_type'] == position and
                p['now_cost'] <= pos_budget and
                p['id'] not in [t['id'] for t in team]
            ]

            # Select top players for this position
            selected = []
            pos_spent = 0

            for player in position_players:
                if len(selected) >= target:
                    break

                player_cost = player['now_cost']

                # Check team constraint (max 3 from same team)
                team_count = sum(1 for p in team if p.get('team_id') == player.get('team_id'))
                if team_count >= 3:
                    continue

                if pos_spent + player_cost <= pos_budget:
                    selected.append(player)
                    pos_spent += player_cost

            team.extend(selected)
            spent += pos_spent
            position_filled[position] = len(selected)

        # Assign positions (1-11 starting, 12-15 bench)
        team = self._assign_positions(team)

        # Add purchase and selling prices
        for player in team:
            player['purchase_price'] = player['now_cost']
            player['selling_price'] = player['now_cost']

        return team

    def _assign_positions(self, team: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Assign positions 1-15 (1-11 starting, 12-15 bench).

        Strategy: Best 11 players start (by expected points).
        """
        # Separate by position
        by_position = {1: [], 2: [], 3: [], 4: []}
        for player in team:
            by_position[player['element_type']].append(player)

        # Sort each position by value score
        for pos in by_position:
            by_position[pos].sort(
                key=lambda x: x.get('total_value_score', 0),
                reverse=True
            )

        # Assign starting XI (3-4-3 or 3-5-2 formation)
        # GK: 1, DEF: 3, MID: 5, FWD: 2
        position_number = 1
        starting_config = {
            1: 1,  # 1 GK
            2: 3,  # 3 DEF
            3: 5,  # 5 MID
            4: 2   # 2 FWD
        }

        for pos in [1, 2, 3, 4]:
            starters = starting_config[pos]
            for i, player in enumerate(by_position[pos]):
                player['position'] = position_number
                position_number += 1

        return team

    def _assign_captain(self, team: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Assign captain and vice-captain based on expected points."""
        starting_xi = [p for p in team if p.get('position', 16) <= 11]

        # Calculate expected points for each
        expected_points = []
        for player in starting_xi:
            exp_pts = self.valuation_agent.calculate_expected_points(player, 3)
            expected_points.append((player, exp_pts))

        # Sort by expected points
        expected_points.sort(key=lambda x: x[1], reverse=True)

        # Assign captain and vice
        if expected_points:
            expected_points[0][0]['is_captain'] = True
            expected_points[0][0]['is_vice_captain'] = False
            expected_points[0][0]['multiplier'] = 2

        if len(expected_points) > 1:
            expected_points[1][0]['is_captain'] = False
            expected_points[1][0]['is_vice_captain'] = True
            expected_points[1][0]['multiplier'] = 1

        # Ensure all others are set to False
        for player in team:
            if 'is_captain' not in player:
                player['is_captain'] = False
            if 'is_vice_captain' not in player:
                player['is_vice_captain'] = False
            if 'multiplier' not in player:
                player['multiplier'] = 1

        return team

    # ========================================================================
    # TRANSFER DECISIONS
    # ========================================================================

    async def make_weekly_decision(
        self,
        gameweek: int
    ) -> Tuple[List[Dict[str, Any]], Optional[str], str]:
        """
        Make weekly team decisions.

        Decides:
        - Whether to make transfers
        - Which players to transfer
        - Captain selection
        - Chip usage

        Returns:
            (transfers, chip_used, announcement)
        """
        logger.info(f"Ron Clanker is planning for GW{gameweek}...")

        # Get current team and latest data
        current_team = self.db.get_current_team(gameweek - 1) or self.current_team
        fpl_data = await self.data_collector.update_all_data()
        all_players = fpl_data['players']

        # ===== NEW: ML-POWERED DECISION MAKING =====
        recommendations = None
        if self.use_ml and self.synthesis_engine:
            try:
                logger.info("Running Decision Synthesis Engine...")
                recommendations = self.synthesis_engine.synthesize_recommendations(gameweek)
                logger.info(f"Synthesis complete: {len(recommendations.get('top_players', []))} players ranked")
            except Exception as e:
                logger.error(f"Synthesis engine failed: {e}. Falling back to basic valuation.", exc_info=True)
                recommendations = None

        # Decide on transfers (ML-powered if available)
        if recommendations:
            transfers = self._decide_transfers_ml(
                current_team,
                recommendations,
                gameweek
            )
        else:
            # Fallback to basic valuation
            transfer_opportunities = self.valuation_agent.identify_transfer_targets(
                current_team,
                all_players
            )
            transfers = self._decide_transfers(
                transfer_opportunities,
                gameweek
            )

        # Execute transfers
        new_team = self._execute_transfers(current_team, transfers)

        # Update captain for new gameweek (ML-powered if available)
        if recommendations and recommendations.get('captain_recommendation'):
            new_team = self._assign_captain_ml(new_team, recommendations['captain_recommendation'])
        else:
            new_team = self._assign_captain(new_team)

        # Decide on chip usage (ML-powered if available)
        if recommendations and recommendations.get('chip_recommendation'):
            chip_used = self._decide_chip_usage_ml(gameweek, new_team, recommendations['chip_recommendation'])
        else:
            chip_used = self._decide_chip_usage(gameweek, new_team)

        # Save decisions
        self.db.set_team(gameweek, new_team)
        for transfer in transfers:
            self.db.log_transfer(
                gameweek,
                transfer['player_out']['id'],
                transfer['player_in']['id'],
                transfer.get('cost', 0),
                transfer.get('is_free', True),
                transfer.get('reasoning', '')
            )

        # Generate announcement (with ML insights if available)
        if transfers:
            reasoning = self._generate_transfer_reasoning(transfers, recommendations)
            announcement = self.ron.announce_transfers(transfers, gameweek, reasoning)
        else:
            reasoning = {
                'strategy': recommendations.get('strategy', {}).get('reasoning', f"Team looks solid for GW{gameweek}. No changes needed.") if recommendations else f"Team looks solid for GW{gameweek}. No changes needed.",
                'chip_used': chip_used,
                'ml_insights': recommendations.get('strategy') if recommendations else None
            }
            announcement = self.ron.announce_team_selection(new_team, gameweek, reasoning)

        return transfers, chip_used, announcement

    def _decide_transfers_ml(
        self,
        current_team: List[Dict[str, Any]],
        recommendations: Dict[str, Any],
        gameweek: int
    ) -> List[Dict[str, Any]]:
        """
        ML-POWERED: Decide transfers using synthesis recommendations.

        Considers:
        - Top value players from ML predictions
        - Template risks to cover
        - League position and competitive context
        - Multi-gameweek value
        """
        transfers = []

        # Get top recommended players by position
        top_players = recommendations.get('top_players', [])[:20]
        template_risks = recommendations.get('risks_to_cover', [])
        strategy = recommendations.get('strategy', {})

        # Identify weakest player in current team
        current_team_ids = {p['id'] for p in current_team}

        # Find players in current team
        current_team_with_predictions = []
        for player in current_team:
            player_pred = next((p for p in top_players if p.get('player_id') == player['id']), None)
            if player_pred:
                current_team_with_predictions.append({
                    **player,
                    'xp': player_pred['xp'],
                    'value_score': player_pred['value_score']
                })
            else:
                # Player not in top recommendations - likely weak
                current_team_with_predictions.append({
                    **player,
                    'xp': 0.0,
                    'value_score': 0.0
                })

        # Sort by value score to find weakest
        current_team_with_predictions.sort(key=lambda x: x['value_score'])

        # Consider transfers for weakest player
        weakest = current_team_with_predictions[0] if current_team_with_predictions else None

        if weakest and weakest['value_score'] < 0.5:
            # Find best replacement in same position
            position = weakest['element_type']
            replacements = [p for p in top_players
                           if p['position'] == position
                           and p['player_id'] not in current_team_ids
                           and p['price'] <= weakest['now_cost'] / 10 + 1.0]  # Allow 1m upgrade

            if replacements:
                best_replacement = replacements[0]
                expected_gain = best_replacement['xp'] - weakest.get('xp', 0.0)

                if expected_gain >= 2.0:  # Worth a free transfer
                    transfers.append({
                        'player_out': weakest,
                        'player_in': self._get_player_details(best_replacement['player_id']),
                        'expected_gain': expected_gain,
                        'is_free': True,
                        'cost': 0,
                        'reasoning': (
                            f"ML predicts {best_replacement['name']} will score "
                            f"{best_replacement['xp']:.1f} xP vs {weakest.get('xp', 0):.1f} for "
                            f"{weakest['web_name']}. {strategy.get('approach', 'Value upgrade')}."
                        )
                    })

        return transfers

    def _assign_captain_ml(
        self,
        team: List[Dict[str, Any]],
        captain_rec: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        ML-POWERED: Assign captain using synthesis recommendation.

        Considers:
        - ML predicted points
        - Ownership (template vs differential)
        - League position context
        """
        primary = captain_rec.get('primary', {})
        differential = captain_rec.get('differential_option', {})

        captain_id = primary.get('player_id') if primary else None
        vice_captain_id = differential.get('player_id') if differential else None

        # Find captain and vice in team
        for player in team:
            if player['id'] == captain_id:
                player['is_captain'] = True
                player['is_vice_captain'] = False
                player['multiplier'] = 2
                logger.info(f"Captain (ML): {player['web_name']} ({primary.get('xp', 0):.2f} xP)")
            elif player['id'] == vice_captain_id:
                player['is_captain'] = False
                player['is_vice_captain'] = True
                player['multiplier'] = 1
            else:
                player['is_captain'] = False
                player['is_vice_captain'] = False
                player['multiplier'] = 1

        # If no captain set (player not in team), fallback to basic method
        if not any(p.get('is_captain') for p in team):
            logger.warning("ML captain not in team, using fallback")
            return self._assign_captain(team)

        return team

    def _decide_chip_usage_ml(
        self,
        gameweek: int,
        team: List[Dict[str, Any]],
        chip_rec: Dict[str, Any]
    ) -> Optional[str]:
        """
        ML-POWERED: Decide chip usage using synthesis recommendation.

        Considers:
        - Optimal timing from chip analyzer
        - League position and competitive context
        - Expected gain vs alternatives
        """
        recommended_chip = chip_rec.get('recommended_chip')
        reasoning = chip_rec.get('reasoning', '')

        if recommended_chip and recommended_chip != 'none':
            logger.info(f"Chip recommendation: {recommended_chip} - {reasoning}")
            # For now, be conservative - still don't use chips in early phase
            # TODO: Enable chip usage when confidence is high
            return None

        return None

    def _get_player_details(self, player_id: int) -> Dict[str, Any]:
        """Fetch full player details from database."""
        player_data = self.db.execute_query(
            "SELECT * FROM players WHERE id = ?",
            (player_id,)
        )
        return player_data[0] if player_data else None

    def _decide_transfers(
        self,
        opportunities: List[Tuple[Dict, Dict, float]],
        gameweek: int
    ) -> List[Dict[str, Any]]:
        """
        Decide which transfers to make this week.

        Phase 1 logic: Conservative approach
        - Use free transfer if significant upgrade available (2+ points)
        - Only take hits for 4+ point expected gain
        """
        if not opportunities:
            return []

        transfers = []
        best_opportunity = opportunities[0]
        player_out, player_in, expected_gain = best_opportunity

        # Check if worth using free transfer
        if expected_gain >= 2.0:
            transfers.append({
                'player_out': player_out,
                'player_in': player_in,
                'expected_gain': expected_gain,
                'is_free': True,
                'cost': 0,
                'reasoning': f"Upgrading {player_out['web_name']} to {player_in['web_name']} - expect {expected_gain} extra points"
            })

        return transfers

    def _execute_transfers(
        self,
        current_team: List[Dict[str, Any]],
        transfers: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Execute transfers and return new team."""
        new_team = current_team.copy()

        for transfer in transfers:
            player_out = transfer['player_out']
            player_in = transfer['player_in']

            # Remove player out
            new_team = [p for p in new_team if p['id'] != player_out['id']]

            # Add player in with same position
            player_in['position'] = player_out['position']
            player_in['purchase_price'] = player_in['now_cost']
            player_in['selling_price'] = player_in['now_cost']
            new_team.append(player_in)

        return new_team

    def _decide_chip_usage(
        self,
        gameweek: int,
        team: List[Dict[str, Any]]
    ) -> Optional[str]:
        """
        Decide whether to use a chip this gameweek.

        Phase 1: Conservative - don't use chips yet
        """
        # Phase 1: No chip usage - save for later phases
        return None

    def _generate_transfer_reasoning(
        self,
        transfers: List[Dict[str, Any]],
        recommendations: Optional[Dict[str, Any]] = None
    ) -> str:
        """Generate Ron's reasoning for transfers."""
        reasoning_parts = []

        for transfer in transfers:
            player_out = transfer['player_out']['web_name']
            player_in = transfer['player_in']['web_name']
            gain = transfer['expected_gain']

            base_reasoning = (
                f"{player_out} hasn't delivered. {player_in} is the better option. "
                f"Expect {gain:.1f} extra points per week."
            )

            # Add ML context if available
            if recommendations and recommendations.get('strategy'):
                strategy = recommendations['strategy']
                base_reasoning += f" {strategy.get('reasoning', '')}"

            reasoning_parts.append(base_reasoning)

        return " ".join(reasoning_parts)

    # ========================================================================
    # POST-GAMEWEEK ANALYSIS
    # ========================================================================

    def review_gameweek(
        self,
        gameweek: int,
        points_scored: int,
        average_score: int
    ) -> str:
        """
        Review gameweek performance and generate Ron's analysis.

        Returns:
            Review text
        """
        highlights = []
        lowlights = []

        # Analyze performance
        if points_scored > average_score + 10:
            highlights.append("Well above average - tactics worked")
        elif points_scored < average_score - 10:
            lowlights.append("Below average - need to improve")

        # Generate review
        review = self.ron.post_gameweek_review(
            gameweek,
            points_scored,
            average_score,
            highlights,
            lowlights
        )

        return review
